"""Lead integration checks for fail-closed orchestration and reader boundaries."""
import json
import os
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from application import Action, AssignmentSource, WorkflowController
from application.workflows import sec2_hcl_composition_v1 as adapter
from excel.schema import AUDIT_SHEET
from tests import test_application_workflow as fixtures


class ApplicationIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ApplicationWorkflowTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_empty_source_and_unknown_workflow(self):
        f = self.fixture
        result = f.controller.inspect(f._source())
        self.assertEqual(result.summary["submissions"], 0)
        self.assertEqual([a.action for a in result.available_actions], [Action.PREPARE_SUBMISSIONS])
        with self.assertRaises(ValueError):
            WorkflowController("unknown")

    def test_workbook_changed_during_inspection_blocks_render(self):
        f = self.fixture
        identity = f._identity()
        f._add_workbook_row("job", identity, "APPROVED")
        with patch.object(adapter, "_hash", side_effect=["before", "after"]):
            result = f.controller.inspect(f._source(workbook=f.workbook))
        self.assertIn("WORKBOOK_CHANGED", {a.code for a in result.attention})
        self.assertFalse(result.submissions[0].ready_to_render)
        self.assertFalse(result.submissions[0].workbook_valid)
        self.assertNotIn(Action.RENDER_APPROVED, {a.action for a in result.available_actions})

    def test_multiple_audit_ids_cannot_claim_one_row(self):
        f = self.fixture
        identity = f._identity()
        _, digest = f._add_workbook_row("first", identity, "APPROVED")
        book = load_workbook(f.workbook)
        book[AUDIT_SHEET].append(["second", identity.class_name, identity.student_id, 2, digest, "VALIDATED"])
        book.save(f.workbook)
        book.close()
        result = f.controller.inspect(f._source(workbook=f.workbook))
        self.assertEqual(result.summary["submissions"], 1)
        self.assertFalse(result.submissions[0].ready_to_render)
        self.assertGreater(result.summary["blocking_errors"], 0)

    def test_lock_blocks_fresh_marking_without_deletion(self):
        f = self.fixture
        split, roster, decisions, _ = f._write_split_source(f._identity())
        f.jobs.mkdir()
        lock = f.jobs / ".pipeline.lock"
        lock.write_text(str(os.getpid()), encoding="utf-8")
        result = f.controller.inspect(f._source(job_roots=(f.jobs,), split_pile=split, roster=roster, identity_decisions=decisions))
        self.assertIn("BATCH_LOCKED", {a.code for a in result.attention})
        self.assertNotIn(Action.RUN_MARKING, {a.action for a in result.available_actions})
        self.assertEqual(lock.read_text(encoding="utf-8"), str(os.getpid()))

    def test_validated_rerun_is_never_suggested(self):
        f = self.fixture
        identity = f._identity()
        _, digest = f._add_workbook_row("finished", identity, "APPROVED")
        directory = f.jobs / "finished"
        directory.mkdir(parents=True)
        (directory / "student_record.json").write_text(json.dumps({
            "job_id": "finished", "identity": identity.to_dict(), "state": "VALIDATED",
            "mode": "REAL_PDF_BATCH", "workbook": str(f.workbook), "input_digest": digest,
        }), encoding="utf-8")
        (directory / "validated_result.json").write_text(json.dumps(f._grading_result(identity).to_dict()), encoding="utf-8")
        before = f._tree_snapshot(f.root)
        result = f._read_only_controller_call("inspect", f._source(workbook=f.workbook, job_roots=(f.jobs,)))
        self.assertEqual(before, f._tree_snapshot(f.root))
        self.assertEqual(result.summary["approved"], 1)
        self.assertEqual(result.summary["ready_to_render"], 1)
        self.assertNotIn(Action.RUN_MARKING, {a.action for a in result.available_actions})

    def test_non_png_with_matching_hash_is_not_a_card(self):
        import hashlib
        f = self.fixture
        identity = f._identity()
        store, digest = f._add_workbook_row("card", identity, "APPROVED")
        receipt, png = f._write_receipt("card", identity, store, digest)
        png.write_bytes(b"not a PNG")
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["output"]["sha256"] = hashlib.sha256(png.read_bytes()).hexdigest()
        receipt.write_text(json.dumps(data), encoding="utf-8")
        result = f.controller.inspect(f._source(workbook=f.workbook, receipt_roots=(f.receipts,)))
        self.assertFalse(result.submissions[0].rendered)
        self.assertIn("CARD_INVALID", {a.code for a in result.submissions[0].attention})

    def test_invalid_configuration_is_attention_not_prepare_permission(self):
        f = self.fixture
        result = f.controller.inspect(AssignmentSource(config_dir=f.root / "missing-config"))
        self.assertIn("CONFIG_INVALID", {a.code for a in result.attention})
        self.assertEqual([a.action for a in result.available_actions], [Action.RESOLVE_ATTENTION])

    def test_orphan_working_files_are_not_results(self):
        f = self.fixture
        directory = f.jobs / "orphan"
        directory.mkdir(parents=True)
        (directory / "grading_result.json").write_text("{}", encoding="utf-8")
        (directory / "student_record.json").write_text("{", encoding="utf-8")
        result = f.controller.inspect(f._source(job_roots=(f.jobs,)))
        self.assertEqual(result.summary["submissions"], 0)
        self.assertEqual(result.summary["blocking_errors"], 0)
        self.assertNotIn(Action.RUN_MARKING, {a.action for a in result.available_actions})

    def test_conflicting_receipts_do_not_advertise_current_output(self):
        f = self.fixture
        identity = f._identity()
        store, digest = f._add_workbook_row("card", identity, "APPROVED")
        receipt, _ = f._write_receipt("card", identity, store, digest)
        duplicate = f.receipts / "second" / "output" / "render_receipt.json"
        duplicate.parent.mkdir(parents=True)
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["approved_excel_values"]["teacher_comment"] = "过期的教师总评。"
        duplicate.write_text(json.dumps(data), encoding="utf-8")
        result = f.controller.inspect(f._source(workbook=f.workbook, receipt_roots=(f.receipts,)))
        self.assertFalse(result.submissions[0].rendered)
        self.assertNotIn(Action.VIEW_OUTPUTS, {a.action for a in result.available_actions})


if __name__ == "__main__":
    unittest.main()
