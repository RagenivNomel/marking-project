"""A scan's work folder appears only once its split is complete."""
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from application import AssignmentSource
from application.workflows.sec2_hcl_composition_v1 import CompositionWorkflow
from grading.schemas import ValidationError
from tests.local_temp import local_test_directory

SPLIT = "application.workflows.sec2_hcl_composition_v1.split_continuous_anonymous"
READ = "application.workflows.sec2_hcl_composition_v1.read_existing_split"


def good_split(scan, outdir):
    outdir.mkdir(parents=True)
    shutil.copyfile(scan, outdir / "_continuous.pdf")
    (outdir / "submission_001.pdf").write_bytes(b"essay")


def interrupted_split(scan, outdir):
    outdir.mkdir(parents=True)
    shutil.copyfile(scan, outdir / "_continuous.pdf")
    raise RuntimeError("window closed during the split")


class ScanWorkspaceTests(unittest.TestCase):
    def setUp(self):
        context = local_test_directory("scan-workspace")
        self.root = Path(context.__enter__())
        self.addCleanup(context.__exit__, None, None, None)
        self.scan = self.root / "_continuous.pdf"
        self.scan.write_bytes(b"%PDF synthetic scan")
        self.workflow = CompositionWorkflow(project_dir=self.root)
        self.workdir = CompositionWorkflow._scan_workdir(self.scan)
        self.source = AssignmentSource(continuous_scan=self.scan)

    def leftovers(self):
        return sorted(p.name for p in self.root.iterdir() if p.name.startswith(self.workdir.name))

    def test_interrupted_split_leaves_nothing_and_the_next_read_works(self):
        with patch(SPLIT, side_effect=interrupted_split), patch(READ, return_value=[]):
            with self.assertRaises(RuntimeError):
                self.workflow.prepare_source(self.source)
        self.assertEqual(self.leftovers(), [])

        with patch(SPLIT, side_effect=good_split), patch(READ, return_value=[]):
            prepared = self.workflow.prepare_source(self.source)
        self.assertEqual(prepared.split_pile, self.workdir)
        self.assertEqual(self.leftovers(), [self.workdir.name])
        self.assertTrue((self.workdir / "submission_001.pdf").is_file())

    def test_a_split_that_fails_its_check_is_never_renamed_into_place(self):
        with patch(SPLIT, side_effect=good_split), \
             patch(READ, side_effect=ValidationError("manifest does not agree")):
            with self.assertRaises(ValidationError):
                self.workflow.prepare_source(self.source)
        self.assertEqual(self.leftovers(), [])

    def test_stale_partial_folder_from_a_killed_app_is_replaced(self):
        stale = self.workdir.with_name(self.workdir.name + ".partial-999-deadbeef")
        stale.mkdir()
        (stale / "_continuous.pdf").write_bytes(b"half")
        with patch(SPLIT, side_effect=good_split), patch(READ, return_value=[]):
            self.workflow.prepare_source(self.source)
        self.assertEqual(self.leftovers(), [self.workdir.name])

    def test_another_window_finishing_first_is_reused(self):
        def race(scan, outdir):
            good_split(scan, self.workdir)  # the other window renames first
            good_split(scan, outdir)

        with patch(SPLIT, side_effect=race), patch(READ, return_value=[]):
            prepared = self.workflow.prepare_source(self.source)
        self.assertEqual(prepared.split_pile, self.workdir)
        self.assertEqual(self.leftovers(), [self.workdir.name])

    def test_existing_incomplete_folder_is_reported_not_deleted(self):
        self.workdir.mkdir()
        shutil.copyfile(self.scan, self.workdir / "_continuous.pdf")
        with patch(SPLIT) as split:
            with self.assertRaises(ValidationError):
                self.workflow.prepare_source(self.source)
        split.assert_not_called()
        self.assertTrue((self.workdir / "_continuous.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
