from app.jobs.refresh import CsvSource, run
from app.models import ChangeEvent, LifecycleStatus


def test_csv_refresh_records_changes(session, part, tmp_path):
    csv_path = tmp_path / "pcn.csv"
    csv_path.write_text(
        "manufacturer,mpn,status,release_date,revision,revision_date,source\n"
        "SynAlpha,SA7741,nrnd,,C,2026-09-30,PCN-2026-17\n"
        "SynBeta,SB8441,active,,,,\n"  # unchanged
    )
    summary = run(session, [CsvSource([csv_path])])
    assert summary["checked"] == 2 and summary["changed"] == 1
    p = part("SA7741")
    session.refresh(p)
    assert p.lifecycle_status == LifecycleStatus.nrnd and p.datasheet_revision == "C"
    kinds = sorted(e.kind for e in session.query(ChangeEvent).filter_by(part_id=p.id))
    assert kinds == ["lifecycle", "revision"]
    # running again finds nothing new
    assert run(session, [CsvSource([csv_path])])["changed"] == 0


def test_lifecycle_page_lists_changes(client, session, tmp_path):
    csv_path = tmp_path / "pcn.csv"
    csv_path.write_text(
        "manufacturer,mpn,status,release_date,revision,revision_date,source\nSynGamma,SC141,obsolete,,,,PDN-1\n"
    )
    run(session, [CsvSource([csv_path])])
    html = client.get("/lifecycle").text
    assert "PDN-1" in html and "SC141" in html
