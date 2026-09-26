"""Offline checks for the task-facing output path contract."""
from pathlib import Path
import os
import tempfile
import unittest

from application.workflows.task_storage import teacher_output_paths
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
