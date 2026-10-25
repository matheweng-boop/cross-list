"""Biweekly TAM check, combined topics and report-figure links (owner, 25 Oct 2026)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from app import yamlio
from app.models import DataReview
from app.services import inbox, tam, tam_links

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_tam as ct  # noqa: E402

TODAY = datetime(2026, 10, 25, tzinfo=UTC)
TUNER = {"id": "x", "value": "$2.31 B", "year": 2024, "product": "Automotive tuner ICs"}


# ---- the check classifies pages (no network) -------------------------------------------------------------------------
def test_classify_fixtures():
    ok = "The Automotive Tuner IC Market Size was valued at USD 2.31 Billion in 2024 and is projected to reach " \
         "USD 4.04 Billion by 2035."  # fmt: skip
    assert ct.classify(TUNER, ok, TODAY)["status"] == "verified"
    table = "Automotive tuner IC market. 2024 Market Size $ 2.31 Billion 2025 Market Size $ 2.43 Billion 2035 Market " \
            "Size $ 4.04 Billion"  # fmt: skip
    r = ct.classify(TUNER, table, TODAY)
    assert r["status"] == "changed" and r["new_value"] == "$2.43 B" and r["new_year"] == 2025
    other = "The automotive tuner IC market was valued at USD 1.10 billion in 2024 and will reach 2 billion by 2033."
    assert ct.classify(TUNER, other, TODAY)["status"] == "disqualified"
    euro = "The automotive tuner IC market was valued at EUR 2.31 billion in 2024."
    assert ct.classify(TUNER, euro, TODAY)["status"] == "disqualified"
    assert ct.classify(TUNER, "Subscribe to read the automotive tuner report.", TODAY)["status"] == "unverifiable"
    assert ct.classify(TUNER, "Cookie settings", TODAY)["status"] == "unverifiable"
    assert len(ct.classify(TUNER, ok * 5, TODAY).get("evidence", "")) <= 200


def _client(pages: dict[str, tuple[int, str]], seen: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        code, body = pages.get(str(request.url), (404, ""))
        return httpx.Response(code, text=body, headers={"content-type": "text/html"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_run_never_requests_policy_hosts_and_classifies(tmp_path):
    entries = [
        {"id": "a", "product": "Automotive tuner ICs", "value": "$2.31 B", "year": 2024,
         "source": {"url": "https://research.example.com/tuner"}},
        {"id": "b", "product": "RF front ends", "value": "$1 B", "year": 2024, "source": {"url": "https://www.qorvo.com/x"}},
        {"id": "c", "product": "RF front ends", "value": "$1 B", "year": 2024, "source": {"url": "https://www.mouser.com/x"}},
        {"id": "d", "product": "Timing", "value": "$400–500 M", "year": 2024,
         "source": {"url": "https://fintool.com/app/research/x"}},
        {"id": "e", "product": "Wi-Fi modules", "value": "$3.7 B", "year": 2025, "source": {"url": ""}},
        {"id": "f", "product": "Anything", "value": "$1 B", "year": 2024, "source": {"url": "https://blocked.example.org/y"}},
        {"id": "g", "product": "Automotive tuner ICs", "value": "$1.42 B", "year": 2024,
         "source": {"url": "https://gone.example.com/z"}},
    ]  # fmt: skip
    pages = {"https://research.example.com/robots.txt": (404, ""),
             "https://research.example.com/tuner": (200, "<p>The automotive tuner IC market was valued at USD 2.31 "
                                                         "billion in 2024.</p><script>x=1</script>"),
             "https://gone.example.com/robots.txt": (404, "")}  # fmt: skip
    seen: list[str] = []
    with _client(pages, seen) as client:
        checker = ct.PageChecker(client, sleep=lambda s: None)
        res = ct.run(entries, {}, 25, checker, {"blocked.example.org"}, TODAY)
    assert not any(h in u for u in seen for h in ("qorvo.com", "mouser.com", "fintool.com", "blocked.example.org"))
    assert res["a"]["status"] == "verified" and "2.31" in res["a"]["evidence"]
    assert res["b"]["status"] == res["c"]["status"] == res["f"]["status"] == "unverifiable"
    assert res["d"]["status"] == "disqualified" and "summary site" in res["d"]["why"]
    assert res["e"]["status"] == "unverifiable" and res["e"]["why"] == "no link was recorded"
    assert res["g"]["status"] == "unverifiable" and "page gone" in res["g"]["why"]
    assert seen[0].endswith("/robots.txt")  # robots.txt first
    out = tmp_path / "tam_checks.yaml"
    data = ct.write_checks(res, "2026-10-25", out)
    assert yamlio.load(out.read_text())["checks"]["a"]["status"] == "verified" and data["checked"] == "2026-10-25"


def test_rotation_and_limit():
    entries = [{"id": i} for i in ("a", "b", "c")]
    assert [e["id"] for e in ct.pick(entries, {"a": "2026-10-11", "b": "2026-09-27"}, 2)] == ["c", "b"]


# ---- results in the market size --------------------------------------------------------------------------------------
def _checks(tmp_path, monkeypatch, checks: dict):
    p = tmp_path / "tam_checks.yaml"
    p.write_text(yaml.safe_dump({"checked": "2026-10-25", "checks": checks}))
    monkeypatch.setattr(tam, "CHECKS_FILE", p)


def test_disqualified_leaves_by_function_and_owner_agree_overrides_with_flag(session, tmp_path, monkeypatch):
    _checks(tmp_path, monkeypatch, {"current-sensor-mm": {"status": "disqualified", "date": "2026-10-25",
                                                          "why": "the page gives $2.0 B for 2026"}})  # fmt: skip
    assert "current_sensor" not in tam.by_function(session)
    assert tam.check_summary()["disqualified"] == 1
    session.add(DataReview(dataset="tam", key="current-sensor-mm", verdict="correct"))
    session.commit()
    assert tam.by_function(session)["current_sensor"]["usd"] == 3350000000
    flagged = [e["key"] for e in tam.flags(session)]
    assert flagged == ["current-sensor-mm"]


def test_tuner_topic_combines_three_members_into_one_band(session, tmp_path, monkeypatch):
    _checks(tmp_path, monkeypatch, {})
    (t,) = [x for x in tam.topics(session) if x["id"] == "auto-radio-tuner-ics"]
    assert t["is_combined"] and t["n"] == 3
    used = {e["key"] for e in t["used"]}
    assert used == {"tuner-ic-mrfr", "tuner-ic-datahorizzon", "digital-radio-tuner-marketintelo"}
    assert [x["key"] for x in t["excluded"]] == ["tuner-ic-emergen"]  # owner disagreed (recorded 22 Oct)
    assert (t["low"], t["high"], t["year"]) == (890000000, 2310000000, 2024)
    assert (t["cagr_low"], t["cagr_high"]) == (5.2, 6.2)
    size = tam.by_function(session)["am_fm_tuner"]
    assert size["topic"] == "auto-radio-tuner-ics" and size["band"] == "$0.89–2.31 B (2024)"
    assert size["usd"] == (890000000 + 2310000000) / 2
    # the committed record matches what the site computes
    rec = next(x for x in tam.topic_defs() if x["id"] == "auto-radio-tuner-ics")
    assert (rec["low"], rec["high"], rec["year"], rec["n"]) == (t["low"], t["high"], t["year"], t["n"])


def test_disagreed_member_is_excluded_from_the_band(session, tmp_path, monkeypatch):
    _checks(tmp_path, monkeypatch, {})
    session.add(DataReview(dataset="tam", key="tuner-ic-mrfr", verdict="wrong", comment="too high"))
    session.commit()
    (t,) = [x for x in tam.topics(session) if x["id"] == "auto-radio-tuner-ics"]
    assert "tuner-ic-mrfr" in {x["key"] for x in t["excluded"]} and t["high"] == 890000000
    assert t["is_combined"]  # DataHorizzon and MarketIntelo are still reviewed


def test_topic_needs_two_reviewed_members(session, tmp_path, monkeypatch):
    _checks(tmp_path, monkeypatch, {})
    rows = tam.estimates(session)
    t = tam.combine({"id": "t", "fn": "am_fm_tuner", "members": ["tuner-ic-mrfr", "tuner-ic-datahorizzon"]}, rows)
    assert not t["is_combined"]  # nothing reviewed in this database, nothing recorded
    _checks(tmp_path, monkeypatch, {"tuner-ic-mrfr": {"status": "verified"}, "tuner-ic-datahorizzon": {"status":
                                    "verified"}})  # fmt: skip
    assert tam.combine({"id": "t", "fn": "am_fm_tuner", "members": ["tuner-ic-mrfr", "tuner-ic-datahorizzon"]},
                       tam.estimates(session))["is_combined"]  # fmt: skip


# ---- report and case figures -----------------------------------------------------------------------------------------
def test_link_comparison_flags_a_mismatch_into_the_inbox(session, tmp_path, monkeypatch):
    _checks(tmp_path, monkeypatch, {})
    p = tmp_path / "tam_links.yaml"
    p.write_text(yaml.safe_dump({"links": [
        {"id": "auto-wifi7-fem.market_now.7", "slug": "auto-wifi7-fem", "where": "case: market_now[7]",
         "text": "$3.7–3.9 B (2025)", "low": 3.7e9, "high": 3.9e9, "year": 2025, "fn": "wifi_fem",
         "keys": ["auto-wifi-modules"]},
        {"id": "auto-uwb-cpd.market_now.4", "slug": "auto-uwb-cpd", "where": "case: market_now[4]",
         "text": "$2.5 B (2024)", "low": 2.5e9, "high": 2.5e9, "year": 2024, "fn": "radar_transceiver",
         "keys": ["cpd-system-ksm"]}]}, allow_unicode=True))  # fmt: skip
    monkeypatch.setattr(tam_links, "LINKS_FILE", p)
    res = {c["id"]: c for c in tam_links.compare(session)}
    assert res["auto-wifi7-fem.market_now.7"]["status"] == "matches"
    assert res["auto-uwb-cpd.market_now.4"]["status"] == "differs"
    text = inbox.collect(session, TODAY.date())
    section = text.split("## TAM changes for reports")[1]
    assert "auto-uwb-cpd.market_now.4" in section and "$1.50 B (2024)" in section and "auto-wifi7-fem" not in section
    # a key left out (owner disagree) is a to-do too
    session.add(DataReview(dataset="tam", key="auto-wifi-modules", verdict="wrong"))
    session.commit()
    assert {c["id"]: c for c in tam_links.compare(session)}["auto-wifi7-fem.market_now.7"]["status"] == "differs"


def test_every_link_points_at_known_keys_and_quoted_text():
    keys = {e["key"] for e in tam.researched()}
    for lk in tam_links.links():
        assert set(lk["keys"]) <= keys, lk["id"]
        if lk["where"].startswith("case: market_now["):
            case = yamlio.load((ROOT / "data/business/cases" / f"{lk['slug']}.yaml").read_text())
            i = int(lk["where"].split("[")[1].rstrip("]"))
            assert lk["text"].split(" (")[0].lstrip("≈") in case["market_now"][i]["value"], lk["id"]


def test_schedule_has_the_biweekly_tam_verification():
    jobs = yamlio.load((ROOT / "data/manage/schedule.yaml").read_text())["jobs"]
    job = next(j for j in jobs if j["name"] == "TAM verification")
    assert job["frequency"] == "biweekly" and "second Sunday" in job["what"]
    assert "scripts/check_tam.py" in (ROOT / "docs/daily_update.md").read_text()


# ---- pages -----------------------------------------------------------------------------------------------------------
def test_tam_page_shows_summary_chips_and_one_tuner_row(client):
    r = client.get("/business/tam")
    assert r.status_code == 200
    assert "Last check" in r.text and "verified" in r.text
    assert r.text.count('id="topic-auto-radio-tuner-ics"') == 1 and "Low <b>$0.89 B</b> – High <b>$2.31 B</b>" in r.text
    assert 'value="tuner-ic-mrfr"' not in r.text  # a member is no longer a separate review item
    assert 'id="t-tuner-ic-mrfr"' in r.text  # ... but stays visible inside the topic
    single = next(e["key"] for e in tam.researched() if e["fn"] != "am_fm_tuner" and e["key"] not in tam.applied())
    assert f'value="{single}"' in r.text  # a single estimate stays separate, for review
    assert "Applied in:" in r.text


def test_case_and_report_pages_show_figure_notes_to_the_owner_only(owner, make_guest):
    r = owner.get("/business/reports/auto-wifi7-fem")
    assert r.status_code == 200 and "Market figure checked" in r.text
    bg = owner.get("/business/reports/iso-current-sense-charging/background")
    assert bg.status_code == 200 and "Market figures on this page" in bg.text
    guest, _ = make_guest()
    g = guest.get("/business/reports/auto-wifi7-fem")
    assert g.status_code == 200 and "Market figure checked" not in g.text
