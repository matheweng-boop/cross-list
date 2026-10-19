from app.services import cross_notes


def test_notes_match_by_prefix_ignoring_dashes():
    notes = cross_notes.notes_for("UCC20225AQNPLRQ1", "SI8234AB-D-IM")
    assert notes and notes[0]["verdict_label"] == "Next best option"
    assert cross_notes.notes_for("UCC20225AQNPLTQ1", "Si8234AB-AM1")
    assert not cross_notes.notes_for("UCC21520", "Si8234AB-D-IM")
