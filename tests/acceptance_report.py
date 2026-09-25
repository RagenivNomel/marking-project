"""Inspect saved demonstration artifacts without rerunning grading or editing Excel.

Run after the three documented demo CLI commands:
    python -m tests.acceptance_report
"""
import hashlib
import json
from openpyxl import load_workbook
from excel.schema import SHEET
from excel.workbook import read_roster
from grading.schemas import ROOT, Identity
from tests.local_fixtures import report_local_fixture_skip
from workflow.pipeline import Pipeline, job_key
from workflow.storage import atomic_json, read_json


def main():
    source = read_json(ROOT / "examples/mock_student.json")
    identity = Identity.from_dict(source["identity"])
    backup = ROOT / "backups" / "phase1_originals"
    manifest_path = backup / "manifest.json"
    roster_path = ROOT / "中二高华作文3评改终稿.xlsx"
    if report_local_fixture_skip([manifest_path, roster_path]):
        return
    entries = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not entries:
        print("SKIPPED: local regression fixture not installed")
        return
    required = [path for item in entries for path in (ROOT / item["path"], backup / item["path"])]
    for batch in ("demo", "failure-rating", "failure-length"):
        job_dir = ROOT / "jobs" / batch / job_key(identity)
        required.append(job_dir / "student_record.json")
        if batch == "demo":
            required.extend([job_dir / "output" / "mock_render.json", ROOT / "output" / batch / "results.xlsx"])
    if report_local_fixture_skip(required):
        return
    runs = {}
    for batch in ("demo", "failure-rating", "failure-length"):
        pipeline = Pipeline(ROOT, batch)
        job = pipeline.jobs_dir / job_key(identity)
        checkpoint = read_json(job / "student_record.json")
        artifact = job / "output/mock_render.json"
        runs[batch] = {"state": checkpoint["state"], "history": checkpoint["history"],
                       "last_error": checkpoint["last_error"], "excel_exists": pipeline.excel.path.exists(),
                       "render_exists": artifact.exists()}
        if batch == "demo":
            approved = pipeline.excel.get(job_key(identity), identity, approved=True)
            equal = read_json(artifact)["approved_excel_values"] == approved.to_dict()
            book = load_workbook(pipeline.excel.path)
            try:
                runs[batch]["excel_review_status"] = book[SHEET]["Y2"].value
                runs[batch]["excel_pipeline_status"] = book[SHEET]["X2"].value
            finally:
                book.close()
            runs[batch]["render_exactly_matches_approved_excel"] = equal
            assert checkpoint["state"] == "COMPLETE" and equal
            assert runs[batch]["excel_review_status"] == "APPROVED"
            assert runs[batch]["excel_pipeline_status"] == "COMPLETE"
        else:
            assert checkpoint["state"] == "GRADED"
            assert checkpoint["last_error"]["type"] == "ValidationError"
            assert not pipeline.excel.path.exists() and not artifact.exists()
    originals = []
    for entry in entries:
        unchanged = all(hashlib.sha256(path.read_bytes()).hexdigest().upper() == entry["sha256"]
                        for path in (ROOT / entry["path"], backup / entry["path"]))
        assert unchanged
        originals.append({"file": entry["path"], "original_and_backup_match": unchanged})
    report = {"scope": "Phase 1 mocks only", "runs": runs, "preserved_assets": originals,
              "teacher_roster_count": len(read_roster(ROOT / "中二高华作文3评改终稿.xlsx"))}
    atomic_json(ROOT / "output/acceptance_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
