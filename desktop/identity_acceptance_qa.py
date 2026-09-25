"""Exercise the Stage 3A teacher identity journey on a safe pile1_test copy."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".desktop-deps"))

from application import AssignmentSource, WorkflowController
from desktop.identity_confirmation import build_identity_review, save_identity_confirmations
from desktop.projection import project
from tests.local_fixtures import report_local_fixture_skip


def _hashes(pile):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in pile.glob("*.pdf")}


def main():
    pile_source = ROOT / "pile1_test"
    roster_source = ROOT / "中二高华作文3评改终稿.xlsx"
    pdfs = sorted(pile_source.glob("*.pdf"))
    required = [pile_source, roster_source, *(pdfs or [pile_source / "__missing_local_pdf_fixture__.pdf"])]
    if report_local_fixture_skip(required):
        return

    safe_root = ROOT / f".stage3a-acceptance-{uuid.uuid4().hex}"
    safe_root.mkdir(parents=True, exist_ok=False)
    try:
        pile = safe_root / "pile1_test"
        shutil.copytree(ROOT / "pile1_test", pile)
        roster = safe_root / "roster.xlsx"
        shutil.copy2(ROOT / "中二高华作文3评改终稿.xlsx", roster)
        decisions = safe_root / "config" / "pile1_identity_decisions.json"
        source = AssignmentSource(split_pile=pile, roster=roster, identity_decisions=decisions)
        before = _hashes(pile)
        controller = WorkflowController()

        initial = controller.inspect(source)
        initial_review = build_identity_review(source, initial)
        if initial.summary["submissions"] != 11 or initial_review["totalCount"] != 11:
            raise AssertionError("safe pile did not load eleven submissions")
        if len(initial_review["rows"]) != 11 or initial_review["confirmedCount"] != 0:
            raise AssertionError("initial normal identity workspace was not unresolved")

        # First teacher pass: save a subset, then reopen the same task.
        first_three = initial_review["rows"][:3]
        partial = [
            {"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index + 1)}
            for index, row in enumerate(first_three)
        ]
        source, partial_saved = save_identity_confirmations(source, partial)
        reopened = controller.inspect(source)
        reopened_review = build_identity_review(source, reopened)
        if partial_saved != 3 or reopened_review["confirmedCount"] != 3 or len(reopened_review["rows"]) != 8:
            raise AssertionError("partial confirmation did not persist and reopen")

        # Second teacher pass: confirm the remaining rows from the actual roster.
        remaining = reopened_review["rows"]
        final_selections = list(partial)
        for index, row in enumerate(remaining, 4):
            final_selections.append({"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index)})
        source, final_saved = save_identity_confirmations(source, final_selections)
        final = controller.inspect(source)
        final_state = project(final, source, "pile1_test", "zh")
        final_review = build_identity_review(source, final)
        confirmed = sum(item.identity_confirmed for item in final.submissions)
        distinct = len({(item.class_name, item.student_id) for item in final.submissions})
        if final_saved != 11 or confirmed != 11 or distinct != 11 or final_review["visible"]:
            raise AssertionError("final confirmation did not reach ready-to-mark")
        if final_state["teacherFlow"]["step"] != "ready_to_mark":
            raise AssertionError(final_state["teacherFlow"])
        if final_state["teacherFlow"]["primaryAction"] != "RUN_MARKING" or final_state["teacherFlow"]["primaryActionEnabled"]:
            raise AssertionError("grading action was accidentally enabled")
        if before != _hashes(pile):
            raise AssertionError("source PDFs changed")

        result = {
            "journey": ["load_11_essays", "confirm_3", "reinspect_3_confirmed_8_remaining", "confirm_remaining_8", "reinspect_ready_to_mark"],
            "initial": {"submissions": initial.summary["submissions"], "confirmed": initial_review["confirmedCount"], "remaining": len(initial_review["rows"])},
            "partial": {"saved": partial_saved, "confirmed": reopened_review["confirmedCount"], "remaining": len(reopened_review["rows"])},
            "final": {"saved": final_saved, "confirmed": confirmed, "distinctStudents": distinct, "teacherFlow": final_state["teacherFlow"], "gradingCalls": 0},
            "sourcePdfsUnchanged": True,
            "developerMode": False,
        }
        target = ROOT / "design" / "stage-3a" / "identity-acceptance.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        # The safe copy is disposable; the persisted decision evidence is kept in
        # the QA JSON, while the real pile and its PDFs are never touched.
        shutil.rmtree(safe_root, ignore_errors=True)


if __name__ == "__main__":
    main()
