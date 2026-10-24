"""Distributor pricing and stock, cached per part (DigiKey for now)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Part, PriceQuote, aware
from app.sources.digikey import DigiKeyClient, DigiKeyError, Quote, RateLimited  # noqa: F401 (errors re-exported)

SOURCE = "digikey"
QUANTITIES = (1, 100, 1000)  # price columns shown and exported

_client: DigiKeyClient | None = None


def get_client() -> DigiKeyClient | None:
    """The configured DigiKey client, or None when no API key is set."""
    global _client
    s = get_settings()
    if not (s.digikey_client_id and s.digikey_client_secret):
        return None
    if _client is None or _client.client_id != s.digikey_client_id:
        _client = DigiKeyClient(s.digikey_client_id, s.digikey_client_secret, s.digikey_site, s.digikey_currency)
    return _client


def enabled() -> bool:
    return get_client() is not None


def _fresh(pq: PriceQuote, max_age: timedelta) -> bool:
    return datetime.now(UTC) - aware(pq.fetched_at) < max_age


def store(session: Session, part: Part, quote: Quote, currency: str) -> PriceQuote:
    pq = session.scalar(select(PriceQuote).where(PriceQuote.part_id == part.id, PriceQuote.source == SOURCE))
    if pq is None:
        pq = PriceQuote(part_id=part.id, source=SOURCE)
        session.add(pq)
    best = min(quote.offers, key=lambda o: o.min_qty, default=None)
    pq.found = quote.found
    pq.distributor_pn = best.distributor_pn if best else None
    pq.product_url = quote.product_url
    pq.stock = quote.stock
    pq.status = quote.status
    pq.lead_weeks = quote.lead_weeks
    pq.currency = currency
    pq.offers = [{"package": o.package, "min_qty": o.min_qty, "breaks": o.breaks} for o in quote.offers]
    pq.fetched_at = datetime.now(UTC)
    session.flush()
    return pq


def quote_for(session: Session, part: Part, fetch: bool = True, refresh: bool = False) -> PriceQuote | None:
    """Cached quote; fetched from DigiKey when missing or older than price_max_age_hours."""
    pq = session.scalar(select(PriceQuote).where(PriceQuote.part_id == part.id, PriceQuote.source == SOURCE))
    max_age = timedelta(hours=get_settings().price_max_age_hours)
    if pq is not None and not refresh and _fresh(pq, max_age):
        return pq
    client = get_client() if fetch else None
    if client is None:
        return pq
    return store(session, part, client.quote(part.mpn), client.currency)


def price_at(pq: PriceQuote | None, qty: int) -> tuple[float, str] | None:
    """Lowest unit price for buying ``qty`` pieces, in USD (a quote cached in another currency is converted at the ECB
    rate in data/business/price_model.yaml), and the packaging it comes in."""
    from app.services.price_model import usd_rate

    if pq is None or not pq.found:
        return None
    rate = usd_rate(pq.currency)
    best = None
    for offer in pq.offers or []:
        if offer["min_qty"] > qty:
            continue
        price = next((p for q, p in reversed(offer["breaks"]) if q <= qty), None)
        if price is not None and (best is None or price * rate < best[0]):
            best = (price * rate, offer["package"])
    return best


def delta_pct(ref: PriceQuote | None, cand: PriceQuote | None, qty: int) -> float | None:
    """Candidate price vs reference at ``qty``, in percent (negative = cheaper)."""
    a, b = price_at(ref, qty), price_at(cand, qty)
    if not a or not b or a[0] == 0:
        return None
    return round((b[0] - a[0]) / a[0] * 100)


def qty_label(q: int) -> str:
    return f"{q // 1000}k" if q >= 1000 else str(q)


def add_to_comparison(session: Session, comparison) -> None:
    """Append DigiKey stock and price rows (priority 0) to a part comparison."""
    from app.matching.engine import compare_param
    from app.matching.rules import ParamDef
    from app.services.compare import Cell, Row

    quotes = {p.id: quote_for(session, p) for p in comparison.parts}
    rows = [
        (ParamDef("dk_stock", "DigiKey stock", 0, "number", direction="higher"), lambda pq: pq.stock if pq else None)
    ]
    for q in QUANTITIES:
        rows.append(
            (
                ParamDef(
                    f"dk_price_{q}",
                    f"Price @{qty_label(q)} (USD)",
                    0,
                    "number",
                    direction="lower",
                ),
                lambda pq, q=q: (price_at(pq, q) or (None,))[0],
            )
        )
    for pdef, value in rows:
        values = [value(quotes[p.id]) for p in comparison.parts]
        base = value(quotes[comparison.baseline.id])
        cells = []
        for part, v in zip(comparison.parts, values, strict=True):
            status = "baseline" if part.id == comparison.baseline.id else compare_param(pdef, base, v)[0]
            shown = "–" if v is None else f"{v:,}" if pdef.key == "dk_stock" else f"{v:.3f}"
            cells.append(Cell(shown, status))
        known = [v for v in values if v is not None]
        if len(known) >= 2 and max(known) != min(known):
            target = max(known) if pdef.direction == "higher" else min(known)
            for cell, v in zip(cells, values, strict=True):
                cell.best = v == target
        comparison.rows.append(Row(pdef, cells))
