"""Offline checks for the task-facing output path contract."""
from pathlib import Path
import os
import tempfile
import unittest

from application.workflows.task_storage import legacy_output_paths, teacher_output_paths
from tests.local_temp import local_test_directory
from workflow.storage import batch_lock


class TaskStoragePathTests(unittest.TestCase):
    def test_new_task_outputs_are_deterministic_under_the_essay_folder(self):
        with local_test_directory("new-task-output-paths") as temporary:
            task = Path(temporary) / "essays"
            first = teacher_output_paths(task)
            second = teacher_output_paths(task)

            self.assertEqual(first, second)
            self.assertEqual(first.results_directory, task.resolve() / "Results")
            self.assertEqual(first.workbook, task.resolve() / "Results" / "results.xlsx")
            self.assertEqual(first.feedback_cards_directory,
                             task.resolve() / "Results" / "Feedback Cards")
            self.assertFalse(first.results_directory.exists())

    def test_legacy_paths_are_described_without_moving_historical_files(self):
        with local_test_directory("legacy-task-output-paths") as temporary:
            project = Path(temporary) / "project"
            old_results = project / "output" / "teacher_123"
            old_results.mkdir(parents=True)
            old_workbook = old_results / "results.xlsx"
            old_workbook.write_bytes(b"historical workbook fixture")
            before = old_workbook.read_bytes()

            resolved = legacy_output_paths(project, "teacher_123")

            self.assertEqual(resolved.results_directory, old_results.resolve())
            self.assertEqual(resolved.workbook, old_workbook.resolve())
            self.assertEqual(resolved.feedback_cards_directory, old_results / "Feedback Cards")
            self.assertEqual(old_workbook.read_bytes(), before)
            self.assertFalse((project / "Results").exists())

    def test_stale_batch_marker_is_reclaimed_for_recovery(self):
        with local_test_directory("stale-batch-marker") as temporary:
            marker = Path(temporary) / "jobs" / ".student.pipeline.lock"
            marker.parent.mkdir(parents=True)
            marker.write_text(str(2**31 - 1), encoding="utf-8")

            with batch_lock(marker):
                self.assertEqual(marker.read_text(encoding="utf-8"), str(os.getpid()))

            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
