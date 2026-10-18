from app.services import notes_search


def test_search_finds_app_note_passages():
    hits = notes_search.search("replace optocoupler")
    assert hits and hits[0].ref == "AN729"
    assert "<mark>" in hits[0].snippet and "#page=" in hits[0].url


def test_search_includes_engineering_notes():
    assert any(
        h.source == "Cross List note" and h.url == "/engineering/cmti_kv_us" for h in notes_search.search("CMTI")
    )


def test_question_words_are_ignored_and_any_word_fallback():
    assert notes_search.search("what is creepage?")
    assert notes_search.search("creepage zzzqqq")  # no page has both words: falls back to any word
    assert notes_search.search("") == []


def test_snippet_is_escaped():
    for h in notes_search.search("<script> isolation"):
        assert "<script" not in h.snippet


def test_notes_page(client):
    html = client.get("/notes?q=creepage").text
    assert "AN1456" in html or "AN583" in html
    assert "Search notes" in client.get("/notes").text
