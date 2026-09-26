"""Teacher-facing task name, subtitle and review-screen panels (synthetic data only)."""
from pathlib import Path
import re
import unittest

from application.models import AssignmentSource, Inspection, SubmissionState
from desktop.bridge import task_title
from desktop.projection import project


SCAN_FOLDER = Path("C:/teacher/scans/pile2_test")
WORKSPACE = SCAN_FOLDER / ".continuous.essay-work-0123456789ab"


class TaskTitleTests(unittest.TestCase):
    def test_continuous_scan_shows_its_folder_not_the_internal_workspace(self):
        source = AssignmentSource(
            continuous_scan=SCAN_FOLDER / "_continuous.pdf",
            split_pile=WORKSPACE,
            workbook=SCAN_FOLDER / "Results" / "continuous-0123456789ab" / "results.xlsx",
        )
        for language in ("zh", "en"):
            self.assertEqual(task_title(source, language), "pile2_test")

    def test_sources_without_a_scan_keep_their_previous_names(self):
        self.assertEqual(task_title(AssignmentSource(workbook=Path("C:/x/results.xlsx")), "en"), "results")
        self.assertEqual(task_title(AssignmentSource(split_pile=Path("C:/x/pile1_test")), "en"), "pile1_test")
        self.assertEqual(task_title(AssignmentSource(), "zh"), "本地作文资料")


class SubtitleTests(unittest.TestCase):
    @staticmethod
    def _inspection(confirmed):
        return Inspection("fixture", "中二高华作文批改", (), submissions=tuple(
            SubmissionState(f"submission:{i}", *(("同学", "207", str(i), True) if confirmed else ()))
            for i in range(1, 12)))

    def test_unconfirmed_identities_are_not_shown_as_zero_students(self):
        for language, expected in (("en", "11 submissions · Student identities not yet confirmed"),
                                   ("zh", "11份作文 · 学生身份尚未确认")):
            subtitle = project(self._inspection(False), None, language=language)["subtitle"]
            self.assertIn(expected, subtitle)
            self.assertNotIn("0 students", subtitle)
            self.assertNotIn("0名学生", subtitle)

    def test_confirmed_identities_keep_the_student_count(self):
        self.assertIn("11 submissions / 11 students",
                      project(self._inspection(True), None, language="en")["subtitle"])


class ReviewPanelTests(unittest.TestCase):
    def test_teacher_review_step_hides_the_duplicate_next_action_panel(self):
        qml = (Path(__file__).resolve().parents[1] / "qml" / "TeacherFlowSection.qml").read_text(encoding="utf-8")
        panel = re.search(r"NextActionPanel \{(.*?)\n        \}", qml, re.S).group(1)
        visible = re.search(r"visible:(.*?)\n\s+completed:", panel, re.S).group(1)
        self.assertIn('teacherFlow.flow.step !== "review"', visible)


if __name__ == "__main__":
    unittest.main()
