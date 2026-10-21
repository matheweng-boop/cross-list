"""The daily update run's inbox: closed without the read-only key, everything the owner said with it."""

from app.config import get_settings
from app.models import DataReview, SiteFeedback, VolumeRequest


def test_inbox_needs_its_own_key_and_lists_what_the_owner_said(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "site_password", "s3cret")
    assert client.get("/api/inbox").status_code == 404  # no key set: closed, even though the path skips the gate
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    assert client.get("/api/inbox").status_code == 401
    assert client.get("/api/inbox", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # the rest of the site stays behind the password
    assert client.get("/manage/feedback", follow_redirects=False).status_code == 303
    session.add(SiteFeedback(text="Make the legend bigger", kind="idea", path="/portfolio", page="Products"))
    session.add(DataReview(dataset="tam", key="tuner-ic-mrfr", verdict="wrong", comment="Too high"))
    session.add(VolumeRequest(mpn="NSI8241C0-DSWR", volume=150000, customer="ACME Motors", market="HVAC"))
    session.commit()
    r = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40})
    assert r.status_code == 200
    assert "Make the legend bigger" in r.text and "tam / tuner-ic-mrfr: wrong · Too high" in r.text
    assert "ACME" not in r.text and "150000" not in r.text  # requested volumes and customers stay on the site
    bad = client.get("/api/inbox?since=yesterday", headers={"Authorization": "Bearer " + "k" * 40})
    assert bad.status_code == 400
