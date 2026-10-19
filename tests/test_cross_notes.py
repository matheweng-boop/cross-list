from app.services import cross_notes


def test_notes_match_by_prefix_ignoring_dashes():
    notes = cross_notes.notes_for("UCC20225AQNPLRQ1", "SI8234AB-D-IM")
    assert notes and notes[0]["verdict_label"].startswith("Acceptable")
    assert cross_notes.notes_for("UCC20225AQNPLTQ1", "Si8234AB-AM1")
    assert not cross_notes.notes_for("UCC21520", "Si8234AB-D-IM")


def test_vendor_pin_names_are_aliases():
    from app.matching.engine import pins_compatible

    assert pins_compatible("VCCI", "VDDI") and pins_compatible("VSSA", "GNDA") and pins_compatible("OUTB", "VOB")
    assert pins_compatible("GND", "GNDI")
    assert not pins_compatible("VSSA", "VDDA") and not pins_compatible("OUTA", "OUTB")


def test_output_variants_and_distinct_next_best():
    from app.services.alternates import device_of

    assert device_of("SI86S641EB-IU") == device_of("SI86S641BC-AS1") == "SI86S641"
    assert device_of("ISO7741DBQR") == "ISO7741DBQR"
