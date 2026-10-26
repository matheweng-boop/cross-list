import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import create_app
from app.models import Part
from app.services import uploads as up
from app.services.seed import load_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _own_data_dir(tmp_path_factory):
    """Each test session (each worker under `pytest -n auto`) writes its caches, markers and uploads to its own data
    folder, never to var/. Tests that need an empty one still set their own."""
    from app.config import get_settings

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(get_settings(), "data_dir", tmp_path_factory.mktemp("var"))
        yield


# --- the test database (26 Oct 2026): built once per worker and copied for each test ----------------------------------
# Real data files that a fixture stands for, loaded into a template database once per worker instead of into every
# test's own database: {fixture name: (file names in data/real, unofficial)}. A test module adds its own with a PRELOAD
# dict of the same shape (its entries win); such a fixture then only marks "these files are loaded".
PRELOAD = {"real": (("ti_digital_isolators", "skyworks_si86"), None)}


def _build_db(path: Path, files: tuple[str, ...] = (), unofficial: bool | None = None) -> Path:
    """A database as create_app() leaves it (schema and synthetic parts), plus the given real data files."""
    from app.db import init_engine
    from app.main import bootstrap

    engine = init_engine(f"sqlite:///{path}")
    bootstrap(engine, True)
    if files:
        with Session(engine) as s:
            for f in files:
                load_file(s, ROOT / "data" / "real" / f"{f}.yaml", unofficial=unofficial)
            s.commit()
    engine.dispose()
    return path


@pytest.fixture(scope="session")
def _db_templates(tmp_path_factory):
    """Template databases, each built on first use and kept for the session. Under `pytest -n auto` every worker has
    its own tmp folder, so workers never share a database file."""
    folder, made = tmp_path_factory.mktemp("templates"), {}

    def get(files: tuple[str, ...] = (), unofficial: bool | None = None) -> Path:
        if (files, unofficial) not in made:
            made[files, unofficial] = _build_db(folder / f"t{len(made)}.db", files, unofficial)
        return made[files, unofficial]

    return get


def _preload(request) -> tuple[tuple[str, ...], bool | None]:
    """The real data files the test's fixtures stand for (PRELOAD), in order."""
    table = {**PRELOAD, **getattr(request.module, "PRELOAD", {})}
    hits = [table[n] for n in request.node.fixturenames if n in table]
    if not hits:
        return (), None
    assert len({u for _, u in hits}) == 1, "preloaded fixtures disagree on unofficial data"
    return tuple(dict.fromkeys(f for files, _ in hits for f in files)), hits[0][1]


@pytest.fixture
def client(request, tmp_path, _db_templates, monkeypatch):
    """The app on its own copy of a template database (synthetic parts, plus any real data files from PRELOAD). The
    start-up cache warm-up thread is off: tests fill the caches on demand, and a warm-up left running from one test
    would compete with (and read the database of) the next."""
    from app import main

    monkeypatch.setattr(main, "_warm_caches", lambda: None)
    db = tmp_path / "test.db"
    shutil.copyfile(_db_templates(*_preload(request)), db)
    app = create_app(f"sqlite:///{db}", seed_synthetic=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session(client):
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def part(session):
    def get(mpn: str) -> Part:
        return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return get


@pytest.fixture
def real(session):
    """Real TI and Skyworks digital isolators in the test database (it starts with synthetic parts only); loaded into
    the template database through PRELOAD."""


def ids(client, mpn):
    """A part's id, from where the search sends an exact part number."""
    r = client.get(f"/find?q={mpn}", follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1])


@pytest.fixture
def tmp_uploads(tmp_path, monkeypatch):
    """Uploads go to a fresh folder instead of var/."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(up, "upload_dir", lambda: d)
    return d


# --- signing in (passkeys and guests, 23 Oct 2026) --------------------------------------------------------------------
def solve_pow(client) -> dict:
    """Solve the sign-in page's proof of work the way the browser does."""
    from app.auth.session import _zero_bits

    c = client.get("/login/pow").json()
    n = 0
    while _zero_bits(hashlib.sha256(f"{c['challenge']}:{n}".encode()).digest()) < c["bits"]:
        n += 1
    return {"pow_challenge": c["challenge"], "pow_nonce": str(n)}


@pytest.fixture
def locked(client, monkeypatch):
    """The site with a password, as on Render; the client is not signed in."""
    from app.auth import gate
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "site_password", "s3cret")
    monkeypatch.setattr(s, "secret_key", "k")
    monkeypatch.setattr(s, "pow_bits", 6)
    monkeypatch.setattr(s, "rp_id", "localhost")
    monkeypatch.setattr(s, "origin", "http://localhost")
    monkeypatch.setattr(gate, "FAIL_DELAY", 0)
    return client


def sign_in_owner(c, password="s3cret"):
    return c.post("/login", data={"password": password, "next": "/", **solve_pow(c)}, follow_redirects=False)


@pytest.fixture
def owner(locked):
    """The test client signed in as the owner with the password."""
    assert sign_in_owner(locked).status_code == 303
    return locked


@pytest.fixture
def make_guest(locked):
    """make_guest(name) -> (TestClient signed in as a new guest, Account id)."""
    from app.auth.session import COOKIE, make_cookie, new_handle
    from app.models import Account

    def make(name="Anna Guest"):
        with Session(get_engine()) as s:
            acct = Account(name=name, role="guest", handle=new_handle())
            s.add(acct)
            s.commit()
            cookie, aid = make_cookie(acct), acct.id
        g = TestClient(locked.app)
        g.cookies.set(COOKIE, cookie)
        return g, aid

    return make


# --- Telegram alerts (23 Oct 2026) -----------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _no_real_telegram(monkeypatch):
    """Tests never reach Telegram, even when the machine has the bot settings."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


@pytest.fixture
def alerts(monkeypatch):
    """Alerts switched on with a fake bot; returns the list of texts sent (sent inline, not in a thread)."""
    from app.services import notify

    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "BOTTOKEN123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def call(token, method, _timeout=60, **params):
        assert method == "sendMessage" and params["chat_id"] == "42" and _timeout <= 3
        sent.append(params["text"])
        return {"ok": True, "result": {"date": 1}}

    monkeypatch.setattr(notify, "_call", call)
    monkeypatch.setattr(notify, "_start", lambda target, *args: target(*args))
    return sent


# --- browser tests (24 Oct 2026): the app on a real port, driven by Chromium -----------------------------------------
CHROMIUM = Path("/opt/pw-browsers/chromium")


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """The app served by uvicorn on a free port, in its own process with its own test database and data folder (never
    var/), as the local owner (no site password), with alerts and DigiKey off. Yields the base URL."""
    tmp = tmp_path_factory.mktemp("live")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CROSSLIST_", "TELEGRAM_"))}
    env |= {"CROSSLIST_DATABASE_URL": f"sqlite:///{tmp / 'live.db'}", "CROSSLIST_DATA_DIR": str(tmp / "var"),
            "CROSSLIST_SITE_PASSWORD": "", "CROSSLIST_SEED_SYNTHETIC": "true", "CROSSLIST_LOAD_REAL_ON_START": "false",
            "CROSSLIST_POW_BITS": "8", "CROSSLIST_RP_ID": "127.0.0.1", "CROSSLIST_ORIGIN": f"http://127.0.0.1:{port}",
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent)}  # fmt: skip
    log_path = tmp / "server.log"
    with open(log_path, "wb") as log:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "--factory", "app.main:create_app", "--host",
                                 "127.0.0.1", "--port", str(port), "--log-level", "warning"], cwd=tmp, env=env,
                                stdout=log, stderr=subprocess.STDOUT)  # fmt: skip
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(600):
                if proc.poll() is not None:
                    pytest.fail("the server did not start:\n" + log_path.read_text())
                try:
                    with urllib.request.urlopen(url + "/healthz", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("the server did not answer within 60 s")
            yield url
        finally:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="session")
def chromium():
    """One headless Chromium for the session, from the image's own copy; the browser tests skip without it (Playwright
    is never asked to download one)."""
    if not CHROMIUM.exists():
        pytest.skip(f"no Chromium at {CHROMIUM}")
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROMIUM))
        yield browser
        browser.close()
