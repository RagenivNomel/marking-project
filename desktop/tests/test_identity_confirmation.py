"""Stage 3A identity workflow tests over safe copies of pile1_test evidence."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import unittest
import uuid

from application import AssignmentSource, WorkflowController
from desktop.identity_confirmation import (
    build_identity_review,
    resolve_identity_companions,
    save_identity_confirmations,
)
from grading.schemas import ROOT, ValidationError
from tests.local_fixtures import require_local_fixtures


class IdentityConfirmationTests(unittest.TestCase):
    def setUp(self):
        pile_source = ROOT / "pile1_test"
        roster_source = ROOT / "中二高华作文3评改终稿.xlsx"
        decisions_source = ROOT / "config" / "pile1_identity_decisions.json"
        pile_pdfs = list(pile_source.glob("*.pdf"))
        if not pile_pdfs:
            self.skipTest("local regression fixture not installed")
        require_local_fixtures(self, [pile_source, roster_source, decisions_source, *pile_pdfs])
        self.root = ROOT / f".stage3a-test-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.pile = self.root / "pile1_test"
        shutil.copytree(pile_source, self.pile)
        self.roster = self.root / "roster.xlsx"
        shutil.copy2(roster_source, self.roster)
        self.decisions = self.root / "config" / "pile1_identity_decisions.json"
        self.source = AssignmentSource(split_pile=self.pile, roster=self.roster, identity_decisions=self.decisions)
        self.controller = WorkflowController()
        self.before = {path: path.read_bytes() for path in self.pile.glob("*.pdf")}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _inspect(self):
        return self.controller.inspect(resolve_identity_companions(self.source))

    @staticmethod
    def _confirmed(inspection):
        return sum(item.identity_confirmed for item in inspection.submissions)

    def test_actual_pile1_companions_are_pre_resolved(self):
        source = resolve_identity_companions(AssignmentSource(split_pile=ROOT / "pile1_test"))
        inspection = self.controller.inspect(source)
        self.assertEqual(inspection.summary["submissions"], 11)
        self.assertEqual(self._confirmed(inspection), 11)
        self.assertEqual(len({(item.class_name, item.student_id) for item in inspection.submissions}), 11)
        self.assertIn("RUN_MARKING", [item.action.value for item in inspection.available_actions])

    def test_empty_decisions_show_compact_unresolved_review(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        self.assertTrue(review["visible"])
        self.assertEqual(review["confirmedCount"], 0)
        self.assertEqual(review["totalCount"], 11)
        self.assertEqual(len(review["rows"]), 11)
        self.assertEqual(len(review["roster"]), 64)
        self.assertTrue(all(row["previewUrl"] for row in review["rows"]))

    def test_partial_confirmation_persists_and_reopens(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        first = review["rows"][:3]
        selections = []
        for row, student_id in zip(first, ("1", "8", "12")):
            selections.append({"sourcePdf": row["sourcePdf"], "className": "207", "studentId": student_id})
        source, saved = save_identity_confirmations(self.source, selections)
        self.assertEqual(saved, 3)
        self.assertTrue(source.identity_decisions.is_file())
        reopened = self.controller.inspect(source)
        self.assertEqual(self._confirmed(reopened), 3)
        reopened_review = build_identity_review(source, reopened)
        self.assertEqual(reopened_review["confirmedCount"], 3)
        self.assertEqual(len(reopened_review["rows"]), 8)

    def test_production_job_ids_keep_confirmed_student_workspace_closed(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        selections = [
            {"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index + 1)}
            for index, row in enumerate(review["rows"])
        ]
        source, saved = save_identity_confirmations(self.source, selections)
        self.assertEqual(saved, 11)
        reopened = self.controller.inspect(source)
        self.assertTrue(all(item.identity_confirmed for item in reopened.submissions))

        # Production jobs replace path-based submission IDs with job IDs, but
        # retain the source PDF path in inspection evidence.
        job_inspection = replace(
            reopened,
            submissions=tuple(
                replace(item, submission_id=f"student_{index:02d}_production")
                for index, item in enumerate(reopened.submissions, 1)
            ),
        )
        job_review = build_identity_review(source, job_inspection)
        self.assertFalse(job_review["visible"])
        self.assertEqual(job_review["confirmedCount"], 11)

    def test_duplicate_assignment_is_rejected_and_source_pdfs_stay_unchanged(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        with self.assertRaises(ValidationError):
            save_identity_confirmations(self.source, [
                {"sourcePdf": review["rows"][0]["sourcePdf"], "className": "207", "studentId": "1"},
                {"sourcePdf": review["rows"][1]["sourcePdf"], "className": "207", "studentId": "1"},
            ])
        self.assertEqual(self.before, {path: path.read_bytes() for path in self.pile.glob("*.pdf")})

    def test_all_confirmations_reach_ready_to_mark_without_grading(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        selections = [
            {"sourcePdf": row["sourcePdf"], "className": "207", "studentId": str(index + 1)}
            for index, row in enumerate(review["rows"])
        ]
        source, saved = save_identity_confirmations(self.source, selections)
        self.assertEqual(saved, 11)
        final = self.controller.inspect(source)
        self.assertEqual(final.summary["submissions"], 11)
        self.assertEqual(self._confirmed(final), 11)
        self.assertEqual(len({(item.class_name, item.student_id) for item in final.submissions}), 11)
        self.assertFalse(final.summary["submissions_needing_attention"])
        self.assertEqual([item.action.value for item in final.available_actions], ["RUN_MARKING"])
        self.assertFalse(build_identity_review(source, final)["visible"])
        self.assertEqual(self.before, {path: path.read_bytes() for path in self.pile.glob("*.pdf")})

    def test_unknown_identity_and_duplicate_decision_rows_are_rejected(self):
        inspection = self._inspect()
        review = build_identity_review(self.source, inspection)
        with self.assertRaises(ValidationError):
            save_identity_confirmations(self.source, [{
                "sourcePdf": review["rows"][0]["sourcePdf"], "className": "207", "studentId": "999"
            }])


if __name__ == "__main__":
    unittest.main()
