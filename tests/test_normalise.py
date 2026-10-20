"""One vocabulary, one set of labels, one vendor name and one description style across pages."""

from datetime import date, datetime

from app.services import lifecycle, products, text, vendors, vocab
from app.web import labels, nav


def test_function_aliases_resolve_to_one_label():
    assert vocab.canonical("rf_pa") == "power_amplifier"
    assert vocab.fn_label("rf_filter") == vocab.fn_label("filter_saw_baw")
    assert vocab.fn_label("not_a_function") == "not a function"  # never snake_case on a page


def test_catv_amplifier_and_power_transistor_are_own_functions_that_fill_sockets():
    assert vocab.canonical("catv_amplifier") == "catv_amplifier"
    assert vocab.fills("catv_amplifier") == ["catv_amplifier", "rf_gain_block"]
    assert vocab.fills("rf_power_transistor") == ["rf_power_transistor", "power_amplifier"]
    assert vocab.fills("rf_pa", ["rf_filter"]) == ["power_amplifier", "filter_saw_baw"]


def test_plural_labels():
    assert vocab.fn_label("diplexer", plural=True) == "Diplexers / multiplexers"
    assert vocab.fn_label("rf_switch", plural=True) == "RF switches"


def test_family_title():
    assert vocab.family_title("gate_driver") != "gate driver"


def test_browse_classifies_by_function_first():
    # Qorvo files many LNAs only under "Amplifiers > Amplifiers"; a VCO under "Oscillators"
    assert products.classify("Amplifiers", "Amplifiers", "lna") == ("rf_amplifiers", "lna")
    assert products.classify("Oscillators", "VCO", "rf_vco")[1] == "rf_synthesizer"
    assert products.classify("Amplifiers", "CATV")[1] == "catv_amplifier"  # no function: catalogue category
    assert products.classify("Passives", "")[1] == "rf_passive"


def test_lifecycle_classes():
    assert lifecycle.status_class("Contact sales (ND)") == "nrnd"
    assert lifecycle.status_class("Non-catalog model") == "unknown"
    assert lifecycle.CLASS_LABELS["unknown"] == "Not stated"


def test_units_and_dates():
    assert labels.unit("100 kV/us, 5 kVRMS, 50 ohm, 2.4GHz") == "100 kV/µs, 5 kVrms, 50 Ω, 2.4 GHz"
    assert labels.unit("SKY13317-373LF") == "SKY13317-373LF"  # part numbers are left alone
    assert labels.fmt_date(date(2026, 10, 20)) == "20 Oct 2026"
    assert labels.fmt_date(datetime(2026, 10, 20, 14, 5), "stamp") == "20 Oct 2026 14:05"
    assert labels.fmt_date(None) == ""


def test_vendor_names():
    assert vendors.display("Texas Instruments") == "TI"
    assert vendors.display("Rohm") == "ROHM"
    assert vendors.display("Some Startup") == "Some Startup"
    assert vendors.group("pSemi") == "Murata"
    assert vendors.group("Lark") == "Trans-Tech"


def test_clean_description():
    c = text.clean_description
    assert c("ISO6441: Quad-channel isolator with 200kV/us CMTI", "ISO6441") == (
        "Quad-channel isolator with 200 kV/µs CMTI"
    )
    assert c("6-Bit, X-Band Core Chip (MACOM category: core chips)") == "6-Bit, X-Band Core Chip"
    assert c("The AG203-63 is a general-purpose buffer amplifier.", "AG203-63") == "General-purpose buffer amplifier"
    assert c("<p>Driver &plusmn;5 A&nbsp;</p>") == "Driver ±5 A"
    assert c("AutoSmart™ PAM for") == "AutoSmart PAM"
    assert c("Integrated PA, 4.5 - 6.5 GHz") == "Integrated PA, 4.5–6.5 GHz"


def test_search_key_ignores_spacing_and_dashes():
    assert text.search_key("2.4 GHz") in text.search_key("LNA, 2.4GHz, 0.1–6 GHz")
    assert text.search_key("0.1-6") in text.search_key("LNA, 2.4GHz, 0.1–6 GHz")


def test_short_description():
    sd = text.short_description
    params = {"configuration": "SP4T", "freq_range_ghz": [0.1, 6]}
    want = "RF switch · SP4T · 0.1–6 GHz · QFN-16 3x3 · AEC-Q100"
    assert sd("rf_switch", "QFN-16 3x3", "automotive", params=params) == want
    specs = {"Frequency Min (MHz)": "700", "Frequency Max (MHz)": "3800", "Gain Typ. (dB)": "18.5"}
    assert sd("lna", "", None, specs=specs) == "LNA · 0.7–3.8 GHz · 18.5 dB gain"
    assert sd(None) == ""  # nothing known: nothing shown, never "n/a"


def test_page_titles_follow_the_menus():
    assert nav.page_title("/rules") == "Cross rules – Data management – BizDev"
    assert nav.page_title("/business/markets").startswith("Markets & customers – Opportunities")
    assert nav.page_title("/parts/1", "SI8641BD-IS").startswith("SI8641BD-IS – ")
