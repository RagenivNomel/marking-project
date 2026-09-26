"""Fake marking must pass the real validator and stay out of the real project."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from PySide6.QtCore import QCoreApplication

from application.models import AssignmentSource
from desktop.bridge import ReadTask
from desktop.identity_confirmation import managed_decision_path, with_decisions_dir
from desktop.fake_marking import FAKE_PROJECT_DIR, FakeGrader, fake_marking_controller
from grading.calibration_schema import CalibrationValidator
from grading.schemas import ROOT, Identity
from tests.local_temp import local_test_directory
from workflow.storage import read_json


class FakeMarkingTests(unittest.TestCase):
    def test_fake_result_passes_the_real_marking_validator(self):
        identity = Identity("26", "测试学生", "207")
        raw = FakeGrader().grade(SimpleNamespace(identity=identity))
        limits = read_json(ROOT / "config" / "text_limits.json")
        result = CalibrationValidator(limits, 1).validate(json.loads(raw["output_text"]), identity)
        self.assertFalse(result.reading_quality.materially_affects_grade)
        self.assertIn("测试", raw["output_text"])

    def test_fake_jobs_live_in_a_separate_test_project(self):
        self.assertNotEqual(FAKE_PROJECT_DIR.resolve(), ROOT.resolve())
        with local_test_directory("fake-marking-project") as folder:
            controller = fake_marking_controller(Path(folder))
            self.assertEqual(controller.workflow.project_dir, Path(folder).resolve())

    def test_fake_confirmations_never_share_the_real_task_file(self):
        workspace = Path("C:/teacher/fake_test_pile2/.continuous.essay-work-0123456789ab")
        fake_dir = FAKE_PROJECT_DIR / "config"
        source = with_decisions_dir(AssignmentSource(split_pile=workspace), fake_dir)
        self.assertEqual(managed_decision_path(source),
                         (fake_dir / "continuous.essay-work-0123456789ab_identity_decisions.json").resolve())
        self.assertNotEqual(managed_decision_path(source).parent, (ROOT / "config").resolve())
        # Normal mode is unchanged, and an explicit decisions file is never replaced.
        self.assertIsNone(with_decisions_dir(AssignmentSource(split_pile=workspace), None).identity_decisions)
        explicit = AssignmentSource(split_pile=workspace, identity_decisions=Path("C:/x/decisions.json"))
        self.assertEqual(with_decisions_dir(explicit, fake_dir), explicit)

    def test_read_task_applies_the_fake_decisions_folder_after_the_split(self):
        QCoreApplication.instance() or QCoreApplication([])
        workspace = Path("C:/teacher/fake_test_pile2/.continuous.essay-work-0123456789ab")

        class Controller:
            def prepare_source(self, source):
                return replace(source, split_pile=workspace)

            def inspect(self, source):
                return "inspection"

        emitted = []
        task = ReadTask(Controller(), AssignmentSource(continuous_scan=workspace.parent / "_continuous.pdf"),
                        False, decisions_dir=FAKE_PROJECT_DIR / "config")
        task.signals.finished.connect(lambda result, source, error: emitted.append((result, source, error)))
        task.run()
        result, source, error = emitted[0]
        self.assertEqual(error, "")
        self.assertEqual(source.identity_decisions.parent, (FAKE_PROJECT_DIR / "config").resolve())


if __name__ == "__main__":
    unittest.main()
