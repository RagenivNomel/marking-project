"""The teacher start page chooses a registered workflow before any task is read."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication

from application import AssignmentSource, WorkflowController
from application.workflows.registry import WORKFLOWS, get_workflow
from application.workflows.sec2_hcl_composition_v1 import CompositionWorkflow, WORKFLOW_ID
from desktop.bridge import DesktopBridge
from desktop.fake_marking import fake_marking_controller
from tests.local_temp import local_test_directory


def gui_app():
    """One offscreen GUI app, so the QML page test can share it."""
    if QCoreApplication.instance() is None:
        from PySide6.QtQuickControls2 import QQuickStyle
        QQuickStyle.setStyle("Basic")
        QGuiApplication([])
    return QCoreApplication.instance()


class RecordingController:
    """Fails the test if selecting or leaving a workflow reads or runs anything."""

    def __init__(self, workflow_id):
        self.workflow_id = workflow_id

    def __getattr__(self, name):
        raise AssertionError(f"workflow selection must not call {name}")


class RegistryTests(unittest.TestCase):
    def test_exactly_one_registered_workflow_is_sec2_composition(self):
        self.assertEqual([info.workflow_id for info in WORKFLOWS], [WORKFLOW_ID])
        self.assertIs(get_workflow(WORKFLOW_ID).workflow_class, CompositionWorkflow)
        self.assertEqual(set(WORKFLOWS[0].to_dict()),
                         {"id", "nameZh", "nameEn", "descriptionZh", "descriptionEn"})

    def test_controller_builds_registered_workflows_and_refuses_others(self):
        self.assertIsInstance(WorkflowController(WORKFLOW_ID).workflow, CompositionWorkflow)
        with self.assertRaises(ValueError):
            WorkflowController("unknown")

    def test_fake_marking_builds_the_chosen_workflow(self):
        with local_test_directory("workflow-selector-fake") as folder:
            controller = fake_marking_controller(Path(folder), WORKFLOW_ID)
            self.assertIsInstance(controller.workflow, CompositionWorkflow)
            self.assertEqual(controller.workflow.project_dir, Path(folder).resolve())
            with self.assertRaises(ValueError):
                fake_marking_controller(Path(folder), "unknown")


class BridgeSelectionTests(unittest.TestCase):
    def setUp(self):
        gui_app()
        self.built = []

        def factory(workflow_id):
            controller = RecordingController(workflow_id)
            self.built.append(controller)
            return controller

        self.bridge = DesktopBridge(controller_factory=factory)
        self.built.clear()  # the developer UI's startup controller is not a selection

    def test_fresh_bridge_starts_with_no_workflow_selected(self):
        self.assertEqual(self.bridge.selectedWorkflow, {})
        self.assertEqual([w["id"] for w in self.bridge.workflows], [WORKFLOW_ID])

    def test_selecting_builds_that_workflow_without_reading_a_task(self):
        self.bridge.selectWorkflow(WORKFLOW_ID)
        self.assertEqual(self.bridge.selectedWorkflow["id"], WORKFLOW_ID)
        self.assertEqual([c.workflow_id for c in self.built], [WORKFLOW_ID])
        self.assertIs(self.bridge._controller, self.built[0])
        self.assertIsNone(self.bridge._source)
        self.assertFalse(self.bridge.hasInspection)
        self.assertEqual(self.bridge.state["view"], "home")

    def test_unknown_workflow_and_busy_bridge_are_ignored(self):
        self.bridge.selectWorkflow("unknown")
        self.assertEqual(self.bridge.selectedWorkflow, {})
        self.bridge._busy = True
        self.bridge.selectWorkflow(WORKFLOW_ID)
        self.assertEqual(self.bridge.selectedWorkflow, {})
        self.bridge._busy = False
        self.bridge.selectWorkflow(WORKFLOW_ID)
        self.bridge._busy = True
        self.bridge.showWorkflowList()
        self.assertEqual(self.bridge.selectedWorkflow["id"], WORKFLOW_ID)
        self.assertEqual(self.built[0].workflow_id, WORKFLOW_ID)
        self.assertEqual(len(self.built), 1)

    def test_all_workflows_clears_the_session_but_keeps_saved_files(self):
        with local_test_directory("workflow-selector-session") as folder:
            saved = Path(folder) / "results.xlsx"
            saved.write_bytes(b"saved results")
            self.bridge.selectWorkflow(WORKFLOW_ID)
            # Stand-in for a task the teacher loaded and worked on.
            self.bridge._source = AssignmentSource(workbook=saved)
            self.bridge._inspection = object()
            self.bridge._real_state = {"view": "workspace"}
            self.bridge._state["view"] = "workspace"

            self.bridge.showWorkflowList()

            self.assertEqual(self.bridge.selectedWorkflow, {})
            self.assertIsNone(self.bridge._source)
            self.assertIsNone(self.bridge._inspection)
            self.assertFalse(self.bridge.hasInspection)
            self.assertEqual(self.bridge.state["view"], "home")
            self.assertEqual(saved.read_bytes(), b"saved results")

            self.bridge.selectWorkflow(WORKFLOW_ID)
            self.assertEqual(self.bridge.selectedWorkflow["id"], WORKFLOW_ID)
            self.assertEqual(len(self.built), 2)
            self.assertIsNone(self.bridge._source)

    def test_existing_explicit_controller_callers_are_unchanged(self):
        controller = RecordingController(WORKFLOW_ID)
        bridge = DesktopBridge(controller=controller)
        self.assertIs(bridge._controller, controller)
        bridge.selectWorkflow(WORKFLOW_ID)
        self.assertIs(bridge._controller, controller)


class TeacherStartPageTests(unittest.TestCase):
    def test_teacher_page_shows_the_menu_then_the_start_card(self):
        app = gui_app()
        if app is not None and not isinstance(app, QGuiApplication):
            self.skipTest("run this module on its own; another test created a non-GUI app")
        from desktop.__main__ import create_app
        _app, engine, bridge = create_app(
            ["test"], controller_factory=lambda workflow_id: RecordingController(workflow_id))
        root = engine.rootObjects()[0]

        def item(name, parent=None):
            # Repeater delegates are only reachable through the visual tree.
            for child in (parent or root.contentItem()).childItems():
                if child.objectName() == name:
                    return child
                found = item(name, child)
                if found is not None:
                    return found
            return None

        def visible(name):
            found = item(name)
            return found is not None and found.isVisible()

        QCoreApplication.processEvents()
        self.assertTrue(visible("selectWorkflow_" + WORKFLOW_ID))
        self.assertFalse(visible("homePrimaryAction"))
        self.assertTrue(visible("workflowPlaceholder"))

        bridge.selectWorkflow(WORKFLOW_ID)
        QCoreApplication.processEvents()
        self.assertTrue(visible("homePrimaryAction"))
        self.assertTrue(visible("allWorkflowsButton"))
        self.assertFalse(visible("selectWorkflow_" + WORKFLOW_ID))
        self.assertFalse(visible("workflowPlaceholder"))

        bridge.showWorkflowList()
        QCoreApplication.processEvents()
        self.assertTrue(visible("selectWorkflow_" + WORKFLOW_ID))
        self.assertFalse(visible("homePrimaryAction"))
        # Tear the QML page down now, not during interpreter shutdown.
        bridge.shutdown()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
