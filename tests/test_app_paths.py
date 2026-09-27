import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import app_paths
from application import WorkflowController
from application.models import AssignmentSource
from desktop.identity_confirmation import managed_decision_path


class DataRootTests(unittest.TestCase):
    def test_source_checkout_keeps_the_project_folder(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(app_paths.DATA_DIR_ENV, None)
            with mock.patch.object(sys, "frozen", False, create=True):
                self.assertEqual(app_paths.data_root(), app_paths.ROOT)

    def test_installed_app_uses_the_per_user_folder(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(app_paths.DATA_DIR_ENV, None)
            with mock.patch.object(sys, "frozen", True, create=True):
                root = app_paths.data_root()
        self.assertEqual(root, app_paths.user_data_dir())
        self.assertEqual(root.name, app_paths.APP_NAME)
        self.assertNotIn(app_paths.ROOT, root.parents)

    def test_override_moves_jobs_and_identity_confirmations(self):
        target = Path.home() / "marking-app-data-test"
        with mock.patch.dict(os.environ, {app_paths.DATA_DIR_ENV: str(target)}):
            controller = WorkflowController()
            decisions = managed_decision_path(AssignmentSource(split_pile=Path("pile1_test")))
        self.assertEqual(controller.workflow.project_dir, target.resolve())
        self.assertEqual(decisions, target.resolve() / "config" / "pile1_identity_decisions.json")
        self.assertFalse(target.exists(), "resolving paths must not create folders")


class NativeToolPathTests(unittest.TestCase):
    def test_bundled_tools_lead_and_known_locations_follow(self):
        known = Path(app_paths.ROOT)  # any existing folder stands in for a well-known location
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}), \
                mock.patch.object(app_paths, "BUNDLED_BIN", app_paths.ROOT / "tests"), \
                mock.patch.object(app_paths, "_well_known_tool_dirs", return_value=[known]):
            app_paths.add_native_tools_to_path()
            entries = os.environ["PATH"].split(os.pathsep)
            app_paths.add_native_tools_to_path()
            self.assertEqual(os.environ["PATH"].split(os.pathsep), entries, "repeat calls add nothing")
        self.assertEqual(entries, [str(app_paths.ROOT / "tests"), "/usr/bin", str(known)])


if __name__ == "__main__":
    unittest.main()
