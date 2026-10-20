"""DigiKey Product Information API v4: price breaks and stock for a manufacturer part number.

Needs an API key (client id + secret) from developer.digikey.com, set as
CROSSLIST_DIGIKEY_CLIENT_ID / CROSSLIST_DIGIKEY_CLIENT_SECRET. Only part numbers are sent.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from app.partnumbers import normalize_pn

API = "https://api.digikey.com"


class DigiKeyError(RuntimeError):
    pass


class RateLimited(DigiKeyError):
    pass


@dataclass
class Offer:
    package: str  # e.g. "Cut Tape (CT)", "Tape & Reel (TR)"
    distributor_pn: str
    min_qty: int
    stock: int | None
    breaks: list[tuple[int, float]]  # (quantity, unit price)


@dataclass
class Quote:
    mpn: str
    found: bool
    manufacturer: str = ""
    stock: int | None = None
    status: str | None = None
    lead_weeks: str | None = None
    product_url: str | None = None
    offers: list[Offer] = field(default_factory=list)


def parse_product(product: dict) -> Quote:
    """A Quote from the API's Product object; missing fields stay None rather than guessed."""
    offers = []
    for v in product.get("ProductVariations") or []:
        breaks = [
            (int(b["BreakQuantity"]), float(b["UnitPrice"]))
            for b in v.get("StandardPricing") or []
            if b.get("BreakQuantity") and b.get("UnitPrice") is not None
        ]
        if not breaks:
            continue
        offers.append(
            Offer(
                package=(v.get("PackageType") or {}).get("Name", ""),
                distributor_pn=v.get("DigiKeyProductNumber", ""),
                min_qty=int(v.get("MinimumOrderQuantity") or breaks[0][0]),
                stock=v.get("QuantityAvailableforPackageType"),
                breaks=sorted(breaks),
            )
        )
    return Quote(
        mpn=product.get("ManufacturerProductNumber", ""),
        found=True,
        manufacturer=(product.get("Manufacturer") or {}).get("Name", ""),
        stock=product.get("QuantityAvailable"),
        status=(product.get("ProductStatus") or {}).get("Status"),
        lead_weeks=str(product["ManufacturerLeadWeeks"]) if product.get("ManufacturerLeadWeeks") else None,
        product_url=product.get("ProductUrl"),
        offers=offers,
    )


def _same_pn(a: str, b: str) -> bool:
    return normalize_pn(a) == normalize_pn(b)


class DigiKeyClient:
    def __init__(self, client_id: str, client_secret: str, site: str = "US", currency: str = "USD", opener=None):
        self.client_id, self.client_secret = client_id, client_secret
        self.site, self.currency = site, currency
        self._open = opener or urllib.request.urlopen
        self._token: str | None = None
        self._token_expires = 0.0

    def _token_header(self) -> str:
        if self._token is None or time.time() > self._token_expires - 30:
            body = urllib.parse.urlencode(
                {"client_id": self.client_id, "client_secret": self.client_secret, "grant_type": "client_credentials"}
            ).encode()
            data = self._call("POST", "/v1/oauth2/token", body, {"Content-Type": "application/x-www-form-urlencoded"})
            self._token = data["access_token"]
            self._token_expires = time.time() + int(data.get("expires_in", 600))
        return f"Bearer {self._token}"

    def _call(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
        req = urllib.request.Request(API + path, data=body, method=method, headers=headers or {})
        try:
            with self._open(req, timeout=30) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                raise RateLimited("DigiKey API rate limit reached; try again later") from e
            raise DigiKeyError(f"DigiKey API {method} {path}: HTTP {e.code}") from e

    def _api(self, method: str, path: str, payload: dict | None = None):
        headers = {
            "Authorization": self._token_header(),
            "X-DIGIKEY-Client-Id": self.client_id,
            "X-DIGIKEY-Locale-Site": self.site,
            "X-DIGIKEY-Locale-Language": "en",
            "X-DIGIKEY-Locale-Currency": self.currency,
            "Accept": "application/json",
        }
        body = None
        if payload is not None:
            body, headers["Content-Type"] = json.dumps(payload).encode(), "application/json"
        return self._call(method, path, body, headers)

    def quote(self, mpn: str) -> Quote:
        """Price and stock for an exact manufacturer part number (keyword search as fallback)."""
        data = self._api("GET", f"/products/v4/search/{urllib.parse.quote(mpn, safe='')}/productdetails")
        product = (data or {}).get("Product")
        if not product or not _same_pn(product.get("ManufacturerProductNumber", ""), mpn):
            found = self._api("POST", "/products/v4/search/keyword", {"Keywords": mpn, "Limit": 10}) or {}
            candidates = (found.get("ExactMatches") or []) + (found.get("Products") or [])
            product = next((p for p in candidates if _same_pn(p.get("ManufacturerProductNumber", ""), mpn)), None)
        return parse_product(product) if product else Quote(mpn=mpn, found=False)
