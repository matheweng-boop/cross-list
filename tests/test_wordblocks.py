"""Block diagram from words (owner, 27 Oct 2026): the "Describe your system" box in the block editor."""

import json
import re
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ExternalSubmission, UnknownWord
from app.services import blocks, wordblocks


def chain(data: dict) -> list[str]:
    """The block functions along the links from the first frame, left to right (first link out of each frame)."""
    groups = {g["id"]: g for g in data["groups"]}
    out, cur = [], data["groups"][0]["id"]
    while cur:
        out.append([b["fn"] for b in groups[cur]["blocks"]])
        cur = next((b for a, b, _ in data["links"] if a == cur), None)
    return out


def fns(data: dict) -> set[str]:
    return {b["fn"] for g in data["groups"] for b in g["blocks"]}


def test_48v_and_mcu_builds_the_power_chain_in_order_and_connected():
    data = wordblocks.build("I have a 48 V input and an MCU")["data"]
    assert chain(data) == [["external_block"], ["tvs_esd", "reverse_polarity"], ["wide_vin_buck"], ["pol_ldo"], ["mcu"]]
    labels = [g["label"] for g in data["groups"]]
    assert labels == ["48 V input", "Input protection", "Step-down 48 V → 5 V", "LDO 5 V → 3.3 V", "Microcontroller"]
    cols = [g["col"] for g in data["groups"]]
    assert cols == sorted(cols) and len(set(cols)) == 5 and {g["row"] for g in data["groups"]} == {0}  # left to right
    assert [x[2] for x in data["links"]] == ["48 V", "", "5 V", "3.3 V"]
    # the editor's own shape: every block id unique, every function known, links between frames that exist
    ids = [b["id"] for g in data["groups"] for b in g["blocks"]]
    assert len(ids) == len(set(ids)) and fns(data) <= set(blocks.catalogue()["functions"])
    assert all(a in {g["id"] for g in data["groups"]} and b in {g["id"] for g in data["groups"]}
               for a, b, _ in data["links"])  # fmt: skip


@pytest.mark.parametrize("text, volts", [
    ("48V", [48]), ("48 V", [48]), ("a 48-volt bus", [48]), ("24V bus", [24]), ("12 V battery", [12]),
    ("5V", [5]), ("3.3V", [3.3]), ("3V3", [3.3]), ("1V8 and 3,3 V", [1.8, 3.3]), ("12 Vdc", [12]),
])  # fmt: skip
def test_voltage_formats(text, volts):
    assert [h.volts for h in wordblocks.read(text) if h.kind == "volt"] == volts


def test_power_rules_buck_for_big_steps_ldo_for_the_last_small_one():
    assert chain(wordblocks.build("12 V battery and a microcontroller")["data"]) == [
        ["battery_pack"],
        ["tvs_esd", "reverse_polarity"],
        ["pol_buck"],
        ["pol_ldo"],
        ["mcu"],
    ]
    assert chain(wordblocks.build("5V USB supply and an MCU")["data"])[:3] == [["external_block"], ["pol_ldo"], ["mcu"]]
    d = wordblocks.build("24V bus, 12V rail, 5 V, 3V3 and 1.8 V, processor")["data"]
    steps = [g["label"] for g in d["groups"] if g["blocks"][0]["fn"] in ("wide_vin_buck", "pol_buck", "pol_ldo")]
    assert steps == ["Step-down 24 V → 12 V", "Step-down 12 V → 5 V", "LDO 5 V → 3.3 V", "LDO 3.3 V → 1.8 V"]
    hv = wordblocks.build("800 V battery and an MCU")["data"]
    assert "isolated_dcdc" in fns(hv) and "hv_battery" in fns(hv)
    # no voltage: a step-down is shown and the user is told to add the voltages
    out = wordblocks.build("battery and an MCU")
    assert "wide_vin_buck" in fns(out["data"]) and any("voltage" in n for n in out["notes"])
    # every block gets the editor's parts: the function ids the parts lookup knows
    assert all(f in blocks.catalogue()["functions"] for f in fns(d) | fns(hv))


@pytest.mark.parametrize("text, fn", [
    ("MCU", "mcu"), ("microcontroller", "mcu"), ("processor", "mcu"), ("SoC", "soc"), ("CAN", "can_transceiver"),
    ("CAN FD", "can_transceiver"), ("LIN", "lin_transceiver"), ("Ethernet", "ethernet_phy"),
    ("BLDC", "three_phase_gate_driver"), ("gate driver", "three_phase_gate_driver"),
    ("current sense", "current_sensor"), ("sensor", "current_sensor"), ("GNSS", "gnss_lna"), ("GPS", "gnss_lna"),
    ("Wi-Fi", "wifi_soc"), ("wifi", "wifi_soc"),
    ("Bluetooth", "wifi_soc"), ("radio", "am_fm_tuner"), ("tuner", "am_fm_tuner"), ("USB", "usb_typec_hub"),
    ("display", "display"), ("audio amp", "audio_amp"), ("clock", "crystal_oscillator"),
    ("crystal", "crystal_oscillator"),
    ("oscillator", "crystal_oscillator"), ("flash", "flash"), ("memory", "flash"), ("relay", "relay_driver"),
    ("contactor", "relay_driver"), ("battery", "battery_pack"),
])  # fmt: skip
def test_synonyms_map_to_functions(text, fn):
    assert fn in fns(wordblocks.build(text)["data"])


def test_vocabulary_file_is_valid_and_lowercase_can_is_a_verb():
    r = wordblocks.rules()
    assert wordblocks.vocabulary_size() > 100
    known = blocks.catalogue()["functions"]
    assert all(t["fn"] in known for t in r["terms"]) and all(v in known for v in r["iso_swap"].values())
    assert all(c == "hub" or c in known for t in r["terms"] for c in t.get("chain") or [])
    assert "can_transceiver" not in fns(wordblocks.build("I can use an MCU")["data"])


def test_isolated_can_and_motor_links():
    d = wordblocks.build("isolated CAN")["data"]
    assert "isolated_can" in fns(d) and "can_transceiver" not in fns(d)
    assert chain(d) == [["mcu"], ["isolated_can"]]  # an MCU is added: the CAN transceiver talks to it
    d = wordblocks.build("an MCU with LIN and isolation")["data"]  # no isolated LIN function: an isolator before it
    assert chain(d) == [["mcu"], ["digital_isolator"], ["lin_transceiver"]]
    d = wordblocks.build("MCU and a BLDC motor")["data"]
    assert chain(d) == [["mcu"], ["three_phase_gate_driver"], ["motor"]]
    assert [g["label"] for g in d["groups"]] == ["Microcontroller", "Gate driver", "Motor"]
    d = wordblocks.build("isolated motor drive")["data"]
    assert "gate_driver" in fns(d) and "three_phase_gate_driver" not in fns(d)


def test_echo_chips_and_grey_unknown_words():
    chips = wordblocks.build("I have a 48 V input and an MCU, frobnicator")["chips"]
    hits = [(c["text"], c["label"]) for c in chips if c["kind"] == "hit"]
    assert hits == [("48 V input", "48 V input"), ("MCU", "Microcontroller")]
    assert [c["text"] for c in chips if c["kind"] == "grey"] == ["frobnicator"]
    assert "".join(c["text"] for c in chips) == "I have a 48 V input and an MCU, frobnicator"


def test_unknown_words_without_names_emails_numbers_or_text():
    text = ("Hello, I need a frobnicator for Anna at Bosch. Mail anna.k@example.com or see www.example.com/x, "
            "order 123456789 and 4242. Tesla wants SuperBus too.")  # fmt: skip
    words = wordblocks.unknown_words(text)
    assert "frobnicator" in words and "hello" in words and "4242" not in words  # bare numbers: no vocabulary
    for bad in ("anna", "bosch", "anna.k", "example", "123456789", "superbus", "tesla", "x"):
        assert bad not in words, bad
    assert all(w == w.lower() and len(w) <= 30 and " " not in w for w in words)
    assert "x" * 31 not in wordblocks.unknown_words("x" * 31)
    assert "bosch" not in wordblocks.unknown_words("Bosch builds it")  # a company name at the sentence start too


def test_owner_build_counts_unknown_words_only(client):
    text = "I have a 48 V input and an MCU and a frobnicator for Anna, anna@example.com"
    r = client.post("/blocks/words", data={"text": text})
    assert r.status_code == 200
    page = r.text
    assert 'id="bk-words-echo"' in page and "Microcontroller" in page and 'class="wgrey">frobnicator' in page
    design = json.loads(re.search(r'<script type="application/json" id="bk-design">(.*?)</script>', page, re.S)[1])
    assert design["id"] is None and len(design["data"]["groups"]) == 5 and "press Save" in design["prefill"]
    with Session(get_engine()) as s:
        rows = s.scalars(select(UnknownWord)).all()
        assert [(w.word, w.count) for w in rows] == [("frobnicator", 1)]
    client.post("/blocks/words", data={"text": "frobnicator twice"})
    with Session(get_engine()) as s:
        assert dict(wordblocks.counts_since(s, date.today())) == {"frobnicator": 2, "twice": 1}
        # retention: 12 months, then the counts go
        s.add(UnknownWord(word="ancient", day=date.today() - timedelta(days=400), count=3))
        s.commit()
        assert wordblocks.purge(s) == 1
        # the daily inbox gets the counts
        from app.services import inbox

        text_out = inbox.collect(s, date.today())
        assert "## Block builder: unknown words" in text_out and "- frobnicator: 2" in text_out
        assert "Anna" not in text_out.split("## Block builder: unknown words")[1].split("\n## ")[0]


def test_guest_can_build_but_nothing_is_collected(make_guest):
    guest, _ = make_guest("Gus Guest")
    r = guest.post("/blocks/words", data={"text": "a 24V bus, CAN and a frobnicator"})
    assert r.status_code == 200 and "CAN transceiver" in r.text
    with Session(get_engine()) as s:
        assert s.scalars(select(UnknownWord)).all() == []
        assert s.scalars(select(ExternalSubmission)).all() == []  # not held as guest input either: nothing stored


def test_editor_page_renders_the_box(client):
    page = client.get("/blocks/new").text
    assert 'id="bk-words"' in page and "Describe your system" in page and 'action="/blocks/words"' in page
    assert 'id="bk-words-build"' in page and '<details id="bk-words" class="bk-words" open>' in page
    lib = client.get("/blocks/new?template=1").text  # folded over a library diagram
    assert 'id="bk-words"' in lib and '<details id="bk-words" class="bk-words">' in lib
