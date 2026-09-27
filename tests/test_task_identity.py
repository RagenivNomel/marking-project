"""A task is identified by the bytes of its continuous scan, never its path.

Each uploaded scan owns its own jobs folder and results workbook, so adding
a scan beside another, or replacing a scan's bytes at the same path, cannot
share saved grading state with a different scan.
"""
import shutil
from pathlib import Path
import unittest

from application import AssignmentSource, WorkflowController
from application.workflows.task_storage import task_id, task_output_paths
from grading.schemas import ROOT
from tests.local_temp import local_test_directory


class TaskIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory("task-identity")
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.folder = self.root / "Class 2A"
        self.folder.mkdir()
        self.workflow = WorkflowController(project_dir=self.root).workflow

    def scan(self, name, content):
        path = self.folder / name
        path.write_bytes(content)
        return AssignmentSource(continuous_scan=path, config_dir=ROOT / "config")

    def test_two_scans_in_one_folder_are_separate_tasks(self):
        first = self.scan("essay-3.pdf", b"first class scan")
        second = self.scan("essay-4.pdf", b"second class scan")

        self.assertNotEqual(task_id(first), task_id(second))
        first_paths, second_paths = task_output_paths(first), task_output_paths(second)
        self.assertNotEqual(first_paths.workbook, second_paths.workbook)
        self.assertNotEqual(first_paths.feedback_cards_directory, second_paths.feedback_cards_directory)
        for paths in (first_paths, second_paths):
            self.assertEqual(paths.results_directory.parent, self.folder.resolve() / "Results")
            self.assertEqual(paths.workbook, paths.results_directory / "results.xlsx")
            self.assertEqual(paths.feedback_cards_directory, paths.results_directory / "Feedback Cards")
        self.assertTrue(first_paths.results_directory.name.startswith("essay-3-"))
        self.assertTrue(second_paths.results_directory.name.startswith("essay-4-"))

    def test_replacing_scan_bytes_at_the_same_path_starts_a_new_task(self):
        original = self.scan("essay.pdf", b"original scan")
        old_task, old_paths = task_id(original), task_output_paths(original)
        old_paths.results_directory.mkdir(parents=True)
        old_paths.workbook.write_bytes(b"teacher workbook for the original scan")
        (self.root / "jobs" / old_task).mkdir(parents=True)

        replaced = self.scan("essay.pdf", b"rescanned with a page fixed")
        new_task, new_paths = task_id(replaced), task_output_paths(replaced)

        self.assertNotEqual(new_task, old_task)
        self.assertNotEqual(new_paths.workbook, old_paths.workbook)
        bound = self.workflow.marking_source(replace_split(replaced, self.folder))
        self.assertIsNone(bound.workbook)
        self.assertEqual(bound.job_roots, ())
        self.assertEqual(bound.results_directory, new_paths.results_directory)
        self.assertEqual(old_paths.workbook.read_bytes(), b"teacher workbook for the original scan")

    def test_scan_and_its_split_workspace_are_the_same_task(self):
        source = self.scan("essay.pdf", b"one class scan")
        workspace = self.root / "workspace"
        workspace.mkdir()
        shutil.copyfile(source.continuous_scan, workspace / "_continuous.pdf")
        imported = AssignmentSource(split_pile=workspace, config_dir=ROOT / "config")

        self.assertEqual(task_id(source), task_id(imported))
        self.assertEqual(self.workflow.marking_batch_id(source), task_id(source))
        self.assertEqual(self.workflow.marking_batch_id(replace_split(source, workspace)), task_id(source))

    def test_moving_a_scan_keeps_its_task(self):
        source = self.scan("essay.pdf", b"moved class scan")
        moved_folder = self.root / "Archive"
        moved_folder.mkdir()
        moved = AssignmentSource(continuous_scan=shutil.copyfile(source.continuous_scan, moved_folder / "renamed.pdf"))
        self.assertEqual(task_id(moved), task_id(source))

    def test_split_pile_without_a_scan_is_reported_not_crashed(self):
        pile = self.root / "incomplete-pile"
        pile.mkdir()
        inspection = WorkflowController(project_dir=self.root).inspect(
            AssignmentSource(split_pile=pile, config_dir=ROOT / "config"))
        self.assertIn("INTAKE_INVALID", {item.code for item in inspection.attention})


def replace_split(source, split_pile):
    from dataclasses import replace
    return replace(source, split_pile=split_pile)


if __name__ == "__main__":
    unittest.main()
