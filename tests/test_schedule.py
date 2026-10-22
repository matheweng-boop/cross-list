"""Data management > Schedule: every job has a known frequency, tonight's run is in order, live counts show."""

from app.services import runs as schedule


def test_jobs_and_tonight():
    assert schedule.jobs() and all(j["frequency"] in schedule.FREQUENCIES for j in schedule.jobs())
    steps = [j["tonight"] for j in schedule.tonight()]
    assert steps == sorted(steps) == list(range(1, len(steps) + 1))
    # the numbered open questions only (none may be open), never the settled list
    assert isinstance(schedule.open_questions(), list)
    assert not any(q.startswith("Tuner market") for q in schedule.open_questions())  # settled 22 Oct 2026


def test_page(client):
    page = client.get("/manage/schedule").text
    assert "Tonight's run" in page and "Pull your comments" in page and "pinout datasheets left" in page
    assert "Every two weeks" in page and "Nothing runs every two weeks yet" in page
    assert 'href="/manage/schedule"' in page
