"""Offline storage and publication checks for normal marking tasks."""
import hashlib
from pathlib import Path
import unittest

from PIL import Image

from application.workflows.card_evidence import inspect_card
from application.workflows.feedback_rendering import ApprovedFeedbackRenderer
from application import AssignmentSource
from application.workflows.task_storage import task_output_paths
from grading.schemas import ROOT
from workflow.pipeline import Pipeline
from workflow.storage import atomic_json, read_json
from tests.local_temp import local_test_directory


class _ApprovedRecord:
    def __init__(self, class_name, student_id, student_name, teacher_comment):
        self.class_name = class_name
        self.student_id = student_id
        self.student_name = student_name
        self.teacher_comment = teacher_comment
        self.review_status = "APPROVED"

    def to_dict(self):
        return {
            "class_name": self.class_name,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "teacher_comment": self.teacher_comment,
            "review_status": self.review_status,
        }


class _SmallOfflineRenderer:
    """Write a tiny PNG and the same audit shape used by the app adapter."""
    def render(self, record, output_dir, audit=None):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        audit = dict(audit or {})
        filename = audit["artifact_filename"]
        artifact = output_dir / filename
        color_digest = hashlib.sha256(record.teacher_comment.encode("utf-8")).digest()
        color = tuple(20 + byte % 200 for byte in color_digest[:3])
        Image.new("RGB", (8, 8), color).save(artifact, format="PNG")
        data = artifact.read_bytes()
        receipt_path = output_dir / "render_receipt.json"
        receipt = {
            "status": "PASS",
            "source": {
                "workbook": audit["workbook"],
                "job_id": audit["job_id"],
                "excel_row": audit["excel_row"],
                "input_digest": audit["input_digest"],
                "source_of_truth": "approved_excel_row",
            },
            "approved_excel_values": record.to_dict(),
            "output": {
                "artifact": str(artifact.resolve()),
                "sha256": hashlib.sha256(data).hexdigest(),
                "width": 8,
                "height": 8,
            },
        }
        atomic_json(receipt_path, receipt)
        return receipt_path


class TaskOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory("task-outputs")
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.project = self.root / "project"
        self.project.mkdir()
        self.task = self.root / "essay PDFs"
        self.task.mkdir()
        scan = self.task / "class scan.pdf"
        scan.write_bytes(b"offline class scan")
        self.paths = task_output_paths(AssignmentSource(continuous_scan=scan))

    def test_pipeline_writes_one_authoritative_workbook_and_keeps_backups_internal(self):
        pipeline = Pipeline(
            self.project, "offline-task", config_dir=ROOT / "config",
            allow_real=True, workbook_path=self.paths.workbook,
        )
        for _ in range(2):
            book = pipeline.excel._open()
            try:
                pipeline.excel._save(book)
            finally:
                book.close()

        self.assertEqual(pipeline.excel.path.resolve(), self.paths.workbook.resolve())
        self.assertEqual(sorted(path.resolve() for path in self.root.rglob("results.xlsx")),
                         [self.paths.workbook.resolve()])
        self.assertEqual({path.name for path in self.paths.results_directory.iterdir()}, {"results.xlsx"})
        self.assertTrue((self.project / "jobs" / "offline-task" / "workbook_backups").is_dir())

    def test_multiple_cards_share_one_clean_folder_and_rerender_replaces_only_the_matching_card(self):
        renderer = ApprovedFeedbackRenderer(_SmallOfflineRenderer(), self.paths.feedback_cards_directory)
        workbook = self.paths.workbook
        workbook.parent.mkdir(parents=True)
        workbook.write_bytes(b"authoritative workbook fixture")
        records = [
            _ApprovedRecord("207", "26", "王晨溪", "教师保存的评语 A。"),
            _ApprovedRecord("207", "27", "李华", "教师保存的评语 B。"),
        ]
        internal_outputs = []

        def render(record):
            output_dir = self.project / "jobs" / "offline-task" / f"student_{record.student_id}" / "output"
            internal_outputs.append(output_dir)
            return Path(renderer.render(record, output_dir, {
                "workbook": str(workbook.resolve()),
                "job_id": f"student_{record.student_id}",
                "excel_row": int(record.student_id),
                "input_digest": f"digest-{record.student_id}",
                "pipeline_status": "VALIDATED",
                "source_of_truth": "approved_excel_row",
            }))

        receipts = [render(record) for record in records]
        cards = sorted(self.paths.feedback_cards_directory.glob("*-作文体检卡.png"))
        self.assertEqual([path.name for path in cards], [
            "207-26-王晨溪-作文体检卡.png",
            "207-27-李华-作文体检卡.png",
        ])
        self.assertEqual({path.name for path in self.paths.results_directory.iterdir()},
                         {"results.xlsx", "Feedback Cards"})
        self.assertTrue(all((output / "render_receipt.json").is_file() for output in internal_outputs))
        self.assertFalse(list(self.paths.feedback_cards_directory.glob("*.json")))

        before_a = cards[0].read_bytes()
        before_b = cards[1].read_bytes()
        updated = _ApprovedRecord("207", "26", "王晨溪", "教师刚保存的新评语 A。")
        updated_receipt = render(updated)
        after_a = cards[0].read_bytes()
        after_b = cards[1].read_bytes()
        self.assertNotEqual(after_a, before_a)
        self.assertEqual(after_b, before_b)

        receipt_data = read_json(updated_receipt)
        self.assertEqual(receipt_data["approved_excel_values"], updated.to_dict())
        self.assertEqual(
            Path(receipt_data["teacher_output"]["artifact"]).resolve(), cards[0].resolve(),
        )
        okay, code, detail = inspect_card(
            updated_receipt, workbook, "student_26", 26, "digest-26",
            updated.to_dict(), expected_teacher_output=cards[0],
        )
        self.assertTrue(okay, (code, detail))
        stale, stale_code, _ = inspect_card(
            updated_receipt, workbook, "student_26", 26, "digest-26",
            records[0].to_dict(), expected_teacher_output=cards[0],
        )
        self.assertFalse(stale)
        self.assertEqual(stale_code, "CARD_STALE")


if __name__ == "__main__":
    unittest.main()
