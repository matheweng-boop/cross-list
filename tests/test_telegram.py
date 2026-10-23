"""Telegram channel: only the owner's chat counts, GO is read from it, the token is never printed."""

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "telegram.py"
spec = importlib.util.spec_from_file_location("telegram", SCRIPT)
tg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tg)

UPDATES = [
    {"update_id": 1, "message": {"date": 90, "chat": {"id": 42}, "text": "old"}},
    {"update_id": 2, "message": {"date": 110, "chat": {"id": 7}, "text": "GO"}},  # someone else's chat
    {"update_id": 3, "message": {"date": 120, "chat": {"id": 42}, "text": "fix the tuner table first"}},
    {"update_id": 4, "message": {"date": 130, "chat": {"id": 42}, "text": "Go!"}},
]


def _fake(calls):
    def call(token, method, **params):
        calls.append((method, params))
        if method == "sendMessage":
            return {"ok": True, "result": {"date": 100}}
        return {"ok": True, "result": [] if "offset" in params else UPDATES}

    return call


def test_replies_only_from_the_owners_chat_and_acknowledged(monkeypatch):
    calls = []
    monkeypatch.setattr(tg.notify, "_call", _fake(calls))
    assert tg.replies("T", "42", 100) == ["fix the tuner table first", "Go!"]
    assert calls[-1] == ("getUpdates", {"offset": 5, "timeout": 0})


def test_wait_go_and_long_messages_are_split(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(tg.notify, "_call", _fake(calls))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(sys, "argv", ["telegram.py", "wait-go", "--since", "100", "--minutes", "0"])
    assert tg.main() == 0 and capsys.readouterr().out.splitlines() == ["- fix the tuner table first", "GO"]
    assert tg.send("T", "42", "x" * 4500) == 100 and sum(m == "sendMessage" for m, _ in calls) == 2


def test_missing_settings_and_errors_hide_the_token(monkeypatch, capsys):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET123")
    monkeypatch.setattr(sys, "argv", ["telegram.py", "replies"])
    assert tg.main() == 2
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def boom(token, method, **params):
        raise RuntimeError(f"failed at /botSECRET123/{method}")

    monkeypatch.setattr(tg.notify, "_call", boom)
    assert tg.main() == 3 and "SECRET123" not in capsys.readouterr().err
