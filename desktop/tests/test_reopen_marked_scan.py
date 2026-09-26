"""Reopening an already-marked continuous scan keeps its saved confirmations."""
import csv
import json
from pathlib import Path
import unittest
from unittest import mock

from openpyxl import Workbook
from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import QCoreApplication

from application import Action, AssignmentSource, WorkflowController
from application.workflows.sec2_hcl_composition_v1 import CompositionWorkflow
import desktop.identity_confirmation as identity_confirmation
from desktop.bridge import ReadTask
from desktop.identity_confirmation import (
    build_identity_review,
    resolve_identity_companions,
    save_identity_confirmations,
)
from grading.schemas import CRITERIA, ROOT
from tests.local_temp import local_test_directory
from workflow.calibration_pipeline import CalibrationPipeline
from workflow.pipeline import Pipeline


IDENTITIES = [("207", "01", "Alice Chen"), ("207", "02", "Ben Lim")]


class InstantGrader:
    """A valid marking result without any model call."""

    def ensure_ready(self):
        pass

    def grade(self, request):
        output = {
            "reading_quality": {"complete_essay_legible": True, "uncertainties": [],
                                "materially_affects_grade": False},
            "grading": {
                **request.identity.to_dict(),
                "criteria": {name: {"rating": "可以更进一步", "short_comment": f"围绕{name}补充具体细节。"}
                             for name in CRITERIA},
                "teacher_comment": "The composition is complete; add more specific details.",
            },
            "evidence": [{"judgment": CRITERIA[0], "page_numbers": [1], "rationale": "Test."}],
        }
        return {"provider": "test", "model": "test", "status": "completed",
                "output_text": json.dumps(output, ensure_ascii=False)}


def pipeline_factory(project_dir, batch_id, config_dir, *, workbook_path=None):
    def calibration_factory(work_dir, model_profile=None):
        return CalibrationPipeline(work_dir, config_dir=config_dir, model_profile=model_profile,
                                   grader_factory=InstantGrader)
    return Pipeline(project_dir, batch_id, config_dir=config_dir, allow_real=True,
                    real_pipeline_factory=calibration_factory, workbook_path=workbook_path)


def make_scan(root: Path) -> tuple[Path, Path]:
    """A two-essay continuous scan, its split workspace, and a class roster."""
    folder = root / "class"
    folder.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792).rotate(90)
    scan = folder / "_continuous.pdf"
    with scan.open("wb") as handle:
        writer.write(handle)
    workspace = CompositionWorkflow._scan_workdir(scan)
    workspace.mkdir()
    (workspace / "_continuous.pdf").write_bytes(scan.read_bytes())
    rows = []
    for index, page in enumerate(PdfReader(scan).pages, 1):
        essay = PdfWriter()
        essay.add_page(page)
        with (workspace / f"essay_{index:03}.pdf").open("wb") as handle:
            essay.write(handle)
        rows.append({"start_page_idx": index - 1, "pages": 1,
                     "raw_ocr_name": IDENTITIES[index - 1][2], "name_preview": ""})
    with (workspace / "_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        manifest = csv.DictWriter(handle, fieldnames=list(rows[0]))
        manifest.writeheader()
        manifest.writerows(rows)
    roster = root / "roster.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "作文诊断输入"
    sheet.append(["班号", "学生姓名", "班级"])
    for class_name, student_id, name in IDENTITIES:
        sheet.append([student_id, name, class_name])
    book.save(roster)
    book.close()
    return scan, roster


class ReopenMarkedScanTests(unittest.TestCase):
    def read(self, controller, source):
        emitted = []
        task = ReadTask(controller, source, False)
        task.signals.finished.connect(lambda result, source, error: emitted.append((result, source, error)))
        task.run()
        inspection, source, error = emitted[0]
        self.assertEqual(error, "")
        return inspection, source

    def test_reopening_a_marked_scan_does_not_duplicate_submissions(self):
        QCoreApplication.instance() or QCoreApplication([])
        with local_test_directory("reopen-marked-scan") as folder:
            root = Path(folder)
            scan, roster = make_scan(root)
            # The app's managed config folder, kept inside this test's folder.
            with mock.patch.object(identity_confirmation, "ROOT", root):
                def opened():
                    # What the teacher's open dialog sends: the scan and the roster.
                    return resolve_identity_companions(AssignmentSource(continuous_scan=scan, roster=roster))

                controller = WorkflowController(project_dir=root / "project", pipeline_factory=pipeline_factory)
                _, source = self.read(controller, opened())
                source, _ = save_identity_confirmations(source, [
                    {"sourcePdf": f"essay_{index:03}.pdf", "className": class_name, "studentId": student_id}
                    for index, (class_name, student_id, _) in enumerate(IDENTITIES, 1)])
                self.assertEqual(source.identity_decisions.parent, (root / "config").resolve())
                controller.execute(Action.RUN_MARKING, source)

                # Close the app and open the same scan again.
                controller = WorkflowController(project_dir=root / "project", pipeline_factory=pipeline_factory)
                inspection, source = self.read(controller, opened())
                self.assertEqual(len(inspection.submissions), len(IDENTITIES))
                self.assertTrue(all(item.identity_confirmed for item in inspection.submissions))
                review = build_identity_review(source, inspection)
                self.assertEqual(review["rows"], [])
                self.assertEqual(review["confirmedCount"], len(IDENTITIES))


if __name__ == "__main__":
    unittest.main()
