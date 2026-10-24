"""Weekly link and source check: the offline inventory, the polite link checker (network mocked) and the Sources
items in Verify next with their way to the daily run's inbox."""

import importlib.util
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.config import PROJECT_ROOT, get_settings
from app.models import VerifyTask
from app.services import runs, verify
from app.services import sources as src

_spec = importlib.util.spec_from_file_location("check_links", PROJECT_ROOT / "scripts" / "check_links.py")
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)

NOW = datetime(2026, 10, 25, 18, 42, tzinfo=UTC)
TAM_URL = "https://www.emergenresearch.com/industry-report/automotive-tuner-ic-market"


# ---------------------------------------------------------------- inventory


def test_links_carry_where_they_are_used():
    links = {lk.url: lk for lk in src.links()}
    tam = links[TAM_URL]
    assert tam.tier == 1 and tam.host == "www.emergenresearch.com"
    assert any(u.file == "data/business/tam.yaml" and u.entry == "tuner-ic-emergen" and u.page == "/business/tam"
               for u in tam.uses)  # fmt: skip
    assert all("{" not in u for u in links)  # template expressions are not links
    cat = [lk for lk in links.values() if any(u.file.startswith("data/catalog/") for u in lk.uses)]
    assert cat and all(lk.tier == 2 or any(not src.is_catalogue(u.file) for u in lk.uses) for lk in cat)
    report = [lk for lk in links.values() if any(u.file.startswith("app/web/templates/business/reports/")
                                                 for u in lk.uses)]  # fmt: skip
    assert report and any(u.page and u.page.startswith("/business/reports/") for lk in report for u in lk.uses)


def test_markers_find_this_weeks_examples():
    ms = src.markers()
    kinds = {(m.kind, m.page) for m in ms}
    assert ("dead_link", "/business/tam") in kinds  # the dead tuner TAM link the owner found
    assert ("from_memory", "/engineering/uwb_signal_path") in kinds  # Wheeler 1939, textbook background
    assert ("not_read", "/business/reports/auto-hv-hot-swap/background") in kinds  # ISO 6469-3 summarised, not read
    assert ("no_data", "/business/competitors/novosense") in kinds  # Novosense cash: no total
    tam = next(m for m in ms if m.kind == "dead_link")
    assert tam.entry == "tuner-ic-emergen" and "link is dead" in tam.text
    assert len({m.key for m in ms}) == len(ms)  # stable, unique keys
    groups = src.by_page()
    assert "/business/tam" in groups and sum(len(v) for v in groups.values()) == len(ms)


def test_markers_skip_catalogues_price_model_and_plain_words():
    files = {m.file for m in src.markers()}
    assert not any(src.is_catalogue(f) for f in files)
    assert not files & set(src.NO_MARKERS) and not any(f.endswith("/_format.yaml") for f in files)
    rx = dict((k, r) for k, _, r in src.MARKERS)
    est = rx["estimate"]
    for plain in ("the best supplier", "a test bench", "estimate the TAM", "our estimate page", "Estonia 4 units"):
        assert not est.search(plain), plain
    for marked in ("about 16 kA with 50 mΩ in the loop, est", "$0.75–1.5 per car (est)", "approx. −627",
                   "12–18 months, est"):  # fmt: skip
        assert est.search(marked), marked
    assert rx["not_read"].search("standards summarised, not read") and rx["not_read"].search("not re-read")
    assert not rx["not_read"].search("not readable")
    assert rx["low_confidence"].search("conf: low") and rx["not_verified"].search("verified: false")


# ---------------------------------------------------------------- link checker (network mocked)


def _link(url, tier=1):
    return src.Link(url, src.host_of(url), tier, [src.Use("data/x.yaml", 1, "e", "/p")])


class FakeClock:
    def __init__(self):
        self.t, self.slept = 0.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def _checker(handler):
    seen = []

    def record(request):
        seen.append(str(request.url))
        return handler(request)

    clock = FakeClock()
    client = httpx.Client(transport=httpx.MockTransport(record), follow_redirects=False)
    return cl.Checker(client, sleep=clock.sleep, clock=clock), seen, clock


def _ok(request):
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    return httpx.Response(200)


def test_policy_hosts_are_never_requested():
    links = [_link(u) for u in (
        "https://www.qorvo.com/products/p/QPF4006", "https://store.qorvo.com/x", "https://qorvo.com/a",
        "https://www.digikey.com/en/products/detail/x", "https://www.mouser.com/ProductDetail/x",
        "https://www.qualcomm.com/products/x", "https://www.iso.org/standard/1.html",
        "https://www.mdpi.com/2079-9292/1/1", "https://web.archive.org/web/2020/https://x.com",
        "https://www.everythingrf.com/x", "https://octopart.com/x", "https://example.com/ok")]  # fmt: skip
    checker, seen, _ = _checker(_ok)
    report = cl.run(links, {"urls": {}, "stopped": {}}, 40, checker, cl.blocked_hosts(), NOW)
    hosts = {src.host_of(u) for u in seen}
    assert hosts == {"example.com"}, seen
    assert report["skipped"]["policy"] == 10 and report["skipped"]["policy (blocked in the library's source list)"] == 1
    assert [r["status"] for r in report["checked"]] == ["ok"]
    assert seen == ["https://example.com/robots.txt", "https://example.com/ok"]  # robots.txt first


def test_robots_gap_and_stop_at_the_first_block():
    def handler(request):
        if request.url.path == "/robots.txt":
            return _ok(request)
        if request.url.host == "blocky.com":
            return httpx.Response(403)
        if request.url.path == "/gone":
            return httpx.Response(404)
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://other.org/new"})
        return httpx.Response(200)

    links = [_link(u) for u in ("https://a.com/private/x", "https://a.com/gone", "https://a.com/old",
                                "https://blocky.com/1", "https://blocky.com/2", "https://www.ti.com/lit/1",
                                "https://www.ti.com/lit/2")]  # fmt: skip
    checker, seen, clock = _checker(handler)
    state = {"urls": {}, "stopped": {}}
    report = cl.run(links, state, 40, checker, set(), NOW, clock=clock)
    st = {r["url"]: r["status"] for r in report["checked"]}
    assert st["https://a.com/private/x"] == "not checked (robots)" and "https://a.com/private/x" not in seen
    assert st["https://a.com/gone"] == "dead" and st["https://a.com/old"] == "moved"
    assert st["https://blocky.com/1"] == "blocked" and st["https://blocky.com/2"] == "not checked (host stopped)"
    assert "https://blocky.com/2" not in seen and "blocky.com" in state["stopped"]
    assert len(seen) == len(set(seen))  # each URL once
    # the gap per host: 10 s, 5 s for ti.com (robots.txt counts as a request)
    times: dict[str, list[float]] = {}
    for u, t in zip(seen, checker._times, strict=True):
        times.setdefault(src.host_of(u), []).append(t)
    for host, ts in times.items():
        gaps = [b - a for a, b in zip(ts, ts[1:], strict=False)]
        assert all(g >= (5 if host.endswith("ti.com") else 10) - 1e-9 for g in gaps), (host, gaps)
    found = cl.problems(state, {lk.url for lk in links})
    assert {p["url"]: p["status"] for p in found} == {"https://a.com/gone": "dead", "https://a.com/old": "moved"}
    # a stopped host is left alone in the next runs too
    picked, skipped = cl.pick(links, state, 40, set(), NOW)
    assert not any(lk.host == "blocky.com" for lk in picked) and skipped["host stopped earlier"] == 2


def test_rotation_oldest_first_and_cited_before_catalogue():
    links = [_link("https://a.com/1"), _link("https://a.com/2"), _link("https://b.com/1", tier=2),
             _link("https://b.com/2"), _link("https://c.com/1")]  # fmt: skip
    state = {"urls": {"https://a.com/1": {"checked": "2026-10-18T18:50:00+00:00"},
                      "https://a.com/2": {"checked": "2026-10-11T18:50:00+00:00"},
                      "https://b.com/2": {"checked": "2026-10-18T18:51:00+00:00"}}, "stopped": {}}  # fmt: skip
    picked, _ = cl.pick(links, state, 5, set(), NOW)
    assert [lk.url for lk in picked] == ["https://c.com/1", "https://b.com/1", "https://a.com/2", "https://a.com/1",
                                         "https://b.com/2"]  # fmt: skip
    assert [lk.url for lk in cl.pick(links, state, 2, set(), NOW)[0]] == ["https://c.com/1", "https://b.com/1"]


def test_never_checked_links_spread_over_hosts():
    links = [_link(f"https://a.com/{i}") for i in range(5)] + [_link("https://b.com/1"), _link("https://c.com/1")]
    picked, _ = cl.pick(links, {"urls": {}}, 3, set(), NOW)
    assert {lk.host for lk in picked} == {"a.com", "b.com", "c.com"}


# ---------------------------------------------------------------- Verify next › Sources and the inbox


@pytest.fixture
def dead_tam(tmp_path, monkeypatch):
    f = tmp_path / "link_check.yaml"
    f.write_text(f"checked: '2026-10-25'\nproblems:\n- {{url: '{TAM_URL}', status: dead, code: 404}}\n"
                 "- {url: 'https://gone.example/removed-from-site', status: dead, code: 404}\n")  # fmt: skip
    monkeypatch.setattr(src, "LINK_CHECK", f)
    return f


def _open_sources(session):
    session.expire_all()
    q = select(VerifyTask).where(VerifyTask.kind == "sources", VerifyTask.status == "open").order_by(VerifyTask.id)
    return list(session.scalars(q))


def test_sources_items_in_verify_next(client, session, dead_tam):
    html = client.get("/manage/verify").text
    tasks = _open_sources(session)
    assert len(tasks) == verify.BATCH["sources"]
    first = tasks[0]
    assert first.key == f"link:{TAM_URL}" and first.detail["page"] == "/business/tam"  # dead links first
    assert not any("gone.example" in t.key for t in tasks)  # a link no longer on the site is done
    assert len({t.detail["page"] or t.detail["file"] for t in tasks}) == len(tasks)  # one per page
    assert 'id="sources"' in html and "Checked, OK" in html and "Fix it" in html and "Remove" in html
    shown = [t for t in tasks if f'action="/manage/verify/{t.id}"' in html]
    assert len(shown) == verify.SHOW["sources"]  # the rest wait (owner: keep the queue short)
    assert 'href="/business/tam"' in html and TAM_URL in html
    assert "<title>Verify next" in html and "<title>Verify next<script>" not in html


def test_sources_answers_reach_the_inbox(client, session, dead_tam, monkeypatch):
    client.get("/manage/verify")
    tasks = _open_sources(session)
    assert client.post(f"/manage/verify/{tasks[0].id}", data={"result": "wrong"}).status_code == 400
    r = client.post(f"/manage/verify/{tasks[0].id}", data={"result": "fix", "note": "new page on emergen"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("#sources")
    client.post(f"/manage/verify/{tasks[1].id}", data={"result": "remove"})
    client.post(f"/manage/verify/{tasks[2].id}", data={"result": "ok"})
    session.expire_all()
    assert [session.get(VerifyTask, t.id).status for t in tasks[:3]] == ["fix", "remove", "ok"]
    html = client.get("/manage/verify").text
    assert "fix it" in html and "checked, OK" in html  # done list
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    text = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40}).text
    sec = text.split("## Source check answers", 1)[1].split("\n## ", 1)[0]
    assert f"fix it: Dead link {TAM_URL} · page /business/tam · data/business/tam.yaml:" in sec
    assert "new page on emergen" in sec and "remove:" in sec and "checked, OK:" in sec
    # answered items never come back; the next ones are shown
    assert all(f"link:{TAM_URL}" != t.key for t in _open_sources(session))


def test_cross_and_data_tasks_keep_their_answers(client, session):
    t = VerifyTask(kind="data", key="trends:x", title="Market trend of x", detail={"topic": "trends", "fn": "x"})
    session.add(t)
    session.commit()
    assert client.post(f"/manage/verify/{t.id}", data={"result": "remove"}).status_code == 400


def test_schedule_has_the_weekly_check():
    job = next(j for j in runs.jobs() if j["name"] == "Link and source check")
    assert job["frequency"] == "weekly" and "Sunday" in job["what"]
    doc = (PROJECT_ROOT / "docs" / "daily_update.md").read_text()
    assert "scripts/check_links.py" in doc and "Source check answers" in doc
