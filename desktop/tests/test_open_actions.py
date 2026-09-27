"""Offline tests for the desktop file and folder open boundary."""
from pathlib import Path
import sys
import unittest

DESKTOP_DEPS = Path(__file__).resolve().parents[2] / ".desktop-deps"
if DESKTOP_DEPS.is_dir():
    sys.path.insert(0, str(DESKTOP_DEPS))

from PySide6.QtCore import QCoreApplication, QUrl

from application.models import Action, AssignmentSource, AvailableAction, Inspection, SubmissionState
from desktop.bridge import DesktopBridge
from desktop.projection import project
from tests.local_temp import local_test_directory


class _ControllerSpy:
    def __init__(self):
        self.executions = []

    def execute(self, *args, **kwargs):
        self.executions.append((args, kwargs))
        raise AssertionError("Opening a file must not execute workflow actions")


class OpenActionTests(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.temp = local_test_directory("open-actions")
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.results = self.root / "Results" / "results.xlsx"
        self.results.parent.mkdir(parents=True)
        self.results.write_bytes(b"unchanged workbook fixture")
        self.cards = self.root / "Results" / "Feedback Cards"
        self.cards.mkdir()
        self.card = self.cards / "207-26-王晨溪-作文体检卡.png"
        self.card.write_bytes(b"offline PNG fixture")
        self.opened = []
        self.controller = _ControllerSpy()
        self.bridge = DesktopBridge(
            controller=self.controller,
            open_url=lambda url: self.opened.append(url) or True,
        )
        self.bridge.setLanguage("en")
        self.bridge._state.update({
            "resultsWorkbookPath": str(self.results),
            "feedbackCardsDirectory": str(self.cards),
        })
        self.bridge._source = AssignmentSource(workbook=self.results)
        self.bridge._inspection = object()

    def tearDown(self):
        self.bridge.shutdown()

    def test_open_results_sends_the_exact_file_and_repeated_clicks_do_not_mutate_it(self):
        before = self.results.read_bytes()

        self.assertTrue(self.bridge.openResults())
        self.assertTrue(self.bridge.openResults())

        self.assertEqual([Path(url.toLocalFile()).resolve() for url in self.opened],
                         [self.results.resolve()] * 2)
        self.assertTrue(all(url.isLocalFile() for url in self.opened))
        self.assertEqual(self.results.read_bytes(), before)
        self.assertEqual(self.controller.executions, [])
        self.assertIsNotNone(self.bridge._source)
        self.assertIsNotNone(self.bridge._inspection)

    def test_open_feedback_cards_sends_the_exact_folder(self):
        self.assertTrue(self.bridge.openFeedbackCards())

        self.assertEqual(len(self.opened), 1)
        self.assertEqual(Path(self.opened[0].toLocalFile()).resolve(), self.cards.resolve())
        self.assertTrue(Path(self.opened[0].toLocalFile()).is_dir())
        self.assertEqual(self.controller.executions, [])

    def test_missing_file_and_folder_fail_with_teacher_readable_messages(self):
        self.bridge._state["resultsWorkbookPath"] = str(self.root / "missing.xlsx")
        self.bridge._state["feedbackCardsDirectory"] = str(self.root / "missing-cards")

        self.assertFalse(self.bridge.openResults())
        self.assertIn("Results workbook could not be found", self.bridge.state["notice"])
        self.assertFalse(self.bridge.openFeedbackCards())
        self.assertIn("Feedback-card folder could not be found", self.bridge.state["notice"])
        self.assertEqual(self.opened, [])
        self.assertEqual(self.controller.executions, [])

    def test_review_and_feedback_buttons_require_real_output_availability(self):
        identity = dict(student_id="26", student_name="王晨溪", class_name="207")
        pending = Inspection(
            "fixture", "Fixture", (),
            submissions=(SubmissionState(
                "job", "王晨溪", "207", "26", True, True, True, "PENDING"
            ),),
            available_actions=(AvailableAction(Action.REVIEW_EXCEL, ("job",)),),
        )
        source = AssignmentSource(workbook=self.results)
        review_state = project(pending, source, language="en")
        self.assertTrue(review_state["resultsWorkbookAvailable"])
        self.assertTrue(review_state["teacherFlow"]["primaryActionEnabled"])
        source_missing = AssignmentSource(workbook=self.root / "absent.xlsx")
        missing_state = project(pending, source_missing, language="en")
        self.assertFalse(missing_state["resultsWorkbookAvailable"])
        self.assertFalse(missing_state["teacherFlow"]["primaryActionEnabled"])

        complete = Inspection(
            "fixture", "Fixture", (),
            submissions=(SubmissionState(
                "job", "王晨溪", "207", "26", True, True, True, "APPROVED",
                rendered=True,
            ),),
            available_actions=(AvailableAction(Action.VIEW_OUTPUTS, ("job",)),),
        )
        cards_source = AssignmentSource(
            workbook=self.results, feedback_cards_directory=self.cards,
        )
        complete_state = project(complete, cards_source, language="en")
        self.assertTrue(complete_state["feedbackCardsAvailable"])
        self.assertTrue(complete_state["teacherFlow"]["primaryActionEnabled"])

        self.card.unlink()
        no_card_state = project(complete, cards_source, language="en")
        self.assertFalse(no_card_state["feedbackCardsAvailable"])
        self.assertFalse(no_card_state["teacherFlow"]["primaryActionEnabled"])

    def test_normal_new_task_dialog_requires_only_continuous_scan_and_roster(self):
        dialog = (Path(__file__).resolve().parents[1] / "qml" / "InspectPathsDialog.qml").read_text(encoding="utf-8")

        self.assertIn('visible: dialog.developerMode; label: I18n.tr("审核工作簿")', dialog)
        self.assertIn('visible: dialog.developerMode; text: I18n.tr("选择 Excel 文件")', dialog)
        self.assertIn('visible: dialog.developerMode; label: I18n.tr("批改作业目录")', dialog)
        self.assertIn('visible: dialog.developerMode; label: I18n.tr("输出回执目录")', dialog)
        self.assertIn('continuousScanField.value.trim().length > 0 && rosterField.value.trim().length > 0', dialog)
        self.assertIn('体检卡文件夹会由应用自动管理', dialog)


if __name__ == "__main__":
    unittest.main()
