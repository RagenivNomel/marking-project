"""Focused tests for the one-page teacher-flow derivation."""

from copy import deepcopy
import unittest

from application.models import (
    Action,
    AvailableAction,
    Inspection,
    SubmissionState,
)
from desktop.fixtures import demo_state
from desktop.teacher_flow import derive_teacher_flow


class TeacherFlowTests(unittest.TestCase):
    def test_empty_projection_starts_with_choose_essays_in_both_languages(self):
        state = demo_state("empty")

        zh = derive_teacher_flow(state)
        en = derive_teacher_flow(state, "en")

        self.assertEqual(zh["step"], "choose_essays")
        self.assertEqual(zh["primaryAction"], Action.PREPARE_SUBMISSIONS.value)
        self.assertEqual(zh["primaryActionLabel"], "选择作文")
        self.assertEqual(en["stageLabel"], "Preparation")
        self.assertEqual(en["primaryActionLabel"], "Choose essays")
        self.assertTrue(zh["readOnly"])
        self.assertFalse(zh["primaryActionEnabled"])

    def test_ready_state_enables_wired_marking_action(self):
        state = {
            "language": "zh",
            "summary": {"submissions": 3, "identity_confirmed": 3},
            "rows": [],
            "attention": [],
            "actionAdvice": [
                {"action": Action.RUN_MARKING.value, "executionWired": True},
            ],
        }

        flow = derive_teacher_flow(state)

        self.assertEqual(flow["step"], "ready_to_mark")
        self.assertEqual(flow["primaryAction"], Action.RUN_MARKING.value)
        self.assertEqual(flow["primaryActionLabel"], "开始批改")
        self.assertTrue(flow["primaryActionEnabled"])
        self.assertTrue(flow["primaryActionExecutionWired"])

    def test_marking_progress_is_used_without_inventing_live_execution(self):
        flow = derive_teacher_flow(demo_state("marking"))

        self.assertEqual(flow["step"], "marking")
        self.assertEqual(flow["stageIndex"], 1)
        self.assertEqual(flow["primaryAction"], Action.RUN_MARKING.value)
        self.assertFalse(flow["primaryActionEnabled"])
        self.assertIn("演示", flow["detail"])

    def test_finished_partial_progress_becomes_resume_not_running(self):
        state = {
            "language": "en",
            "summary": {
                "submissions": 2, "identity_confirmed": 2,
                "grading_results_available": 1, "awaiting_review": 1,
                "marking_available": 1, "retryable_failures": 0,
                "rendered": 0, "ready_to_render": 0,
                "approved": 0, "submissions_needing_attention": 0,
                "blocking_errors": 0,
            },
            "progress": {
                "total": 2, "completed": 1, "active": 0,
                "waiting": 1, "attention": 0, "current": "", "running": False,
            },
            "actionAdvice": [{"action": Action.RUN_MARKING.value, "executionWired": True}],
        }
        flow = derive_teacher_flow(state, "en")

        self.assertEqual(flow["step"], "resume_marking")
        self.assertEqual(flow["primaryActionLabel"], "Resume marking")
        self.assertTrue(flow["primaryActionEnabled"])

    def test_identity_attention_precedes_marking(self):
        flow = derive_teacher_flow(demo_state("identity"))

        self.assertEqual(flow["step"], "resolve_identity")
        self.assertEqual(flow["primaryAction"], Action.CONFIRM_SUBMISSIONS.value)
        self.assertEqual(flow["primaryActionLabel"], "确认学生资料")
        self.assertEqual(flow["stage"], "preparation")

    def test_identity_gate_precedes_recovery_action(self):
        state = {
            "language": "en",
            "summary": {
                "submissions": 2,
                "identity_confirmed": 1,
                "grading_results_available": 0,
                "retryable_failures": 1,
                "submissions_needing_attention": 1,
                "rendered": 0,
            },
            "rows": [],
            "attention": [{"details": "MARKING_RETRY_AVAILABLE\nretry"}],
            "actionAdvice": [
                {"action": Action.RUN_MARKING.value, "executionWired": True},
                {"action": Action.CONFIRM_SUBMISSIONS.value, "executionWired": False},
            ],
        }

        flow = derive_teacher_flow(state, "en")

        self.assertEqual(flow["step"], "resolve_identity")
        self.assertEqual(flow["primaryAction"], Action.CONFIRM_SUBMISSIONS.value)
        self.assertTrue(flow["primaryActionEnabled"])

    def test_pending_excel_review_maps_to_review_guidance(self):
        flow = derive_teacher_flow(demo_state("handoff"))

        self.assertEqual(flow["step"], "review")
        self.assertEqual(flow["primaryAction"], Action.REVIEW_EXCEL.value)
        self.assertEqual(flow["primaryActionLabel"], "打开批改结果 Excel")
        self.assertEqual(flow["headline"], "教师审核已就绪 ✓")
        self.assertFalse(flow["primaryActionEnabled"])

    def test_review_requires_every_result_and_workbook_row_to_be_verified(self):
        state = {
            "language": "en",
            "summary": {
                "submissions": 2, "identity_confirmed": 2,
                "grading_results_available": 2, "workbook_valid": 1,
                "awaiting_review": 1, "approved": 0,
                "marking_available": 0, "rendered": 0,
            },
            "attention": [],
            "actionAdvice": [{"action": Action.REVIEW_EXCEL.value, "executionWired": False}],
        }
        flow = derive_teacher_flow(state, "en")

        self.assertEqual(flow["step"], "resolve_attention")
        self.assertNotIn("Teacher review is ready", flow["headline"])
        self.assertFalse(flow["primaryActionEnabled"])

    def test_approved_excel_maps_to_generation_readiness(self):
        state = demo_state("generate")
        for row in state["rows"]:
            row["status"] = "✓ 已审核"
            row["tone"] = "complete"
        state["summary"].update(awaiting_review=0, approved=31, ready_to_render=7)
        flow = derive_teacher_flow(state)

        self.assertEqual(flow["step"], "generate")
        self.assertEqual(flow["primaryAction"], Action.RENDER_APPROVED.value)
        self.assertIn("生成", flow["primaryActionLabel"])
        self.assertFalse(flow["primaryActionEnabled"])
        self.assertEqual(flow["stage"], "feedback")

    def test_partial_failure_surfaces_attention_and_preserves_success_count(self):
        flow = derive_teacher_flow(demo_state("attention"))

        self.assertEqual(flow["step"], "partial_failure")
        self.assertEqual(flow["primaryAction"], Action.RESOLVE_ATTENTION.value)
        self.assertEqual(flow["completedCount"], 30)
        self.assertEqual(flow["totalCount"], 31)
        self.assertEqual(flow["attentionCount"], 1)
        self.assertIn("已成功生成", flow["headline"])

    def test_completion_maps_to_output_folder(self):
        flow = derive_teacher_flow(demo_state("complete"), "en")

        self.assertEqual(flow["step"], "complete")
        self.assertEqual(flow["primaryAction"], Action.VIEW_OUTPUTS.value)
        self.assertEqual(flow["primaryActionLabel"], "Open feedback-card folder")
        self.assertEqual(flow["stageProgress"], ["complete", "complete", "complete", "current"])
        self.assertIn("folder is not available", flow["actionReason"])

    def test_feedback_render_is_enabled_only_when_stage1_wires_it(self):
        inspection = Inspection(
            "fixture",
            "Fixture",
            (),
            submissions=(
                SubmissionState(
                    "one", "Student", "207", "001", True, True, True, "APPROVED"
                ),
            ),
            available_actions=(
                AvailableAction(Action.REFRESH_REVIEW_STATUS, ("one",), True),
            ),
        )

        flow = derive_teacher_flow(inspection)

        self.assertEqual(flow["step"], "generate")
        self.assertEqual(flow["primaryAction"], Action.RENDER_APPROVED.value)
        self.assertFalse(flow["primaryActionEnabled"])

        wired = Inspection(
            "fixture", "Fixture", (),
            submissions=(SubmissionState(
                "one", "Student", "207", "001", True, True, True, "APPROVED",
                ready_to_render=True,
            ),),
            available_actions=(
                AvailableAction(Action.RENDER_APPROVED, ("one",), True),
            ),
        )
        wired_flow = derive_teacher_flow(wired)
        self.assertTrue(wired_flow["primaryActionEnabled"])
        self.assertTrue(wired_flow["primaryActionExecutionWired"])

        # Refresh remains available when a review is pending.
        pending = Inspection(
            "fixture",
            "Fixture",
            (),
            submissions=(
                SubmissionState(
                    "one", "Student", "207", "001", True, True, True, "PENDING"
                ),
            ),
            available_actions=(
                AvailableAction(Action.REVIEW_EXCEL, ("one",), False),
                AvailableAction(Action.REFRESH_REVIEW_STATUS, ("one",), True),
            ),
        )
        pending_flow = derive_teacher_flow(pending)
        self.assertEqual(pending_flow["primaryAction"], Action.REVIEW_EXCEL.value)
        self.assertFalse(pending_flow["primaryActionEnabled"])

    def test_duplicate_visible_identities_do_not_change_submission_total(self):
        state = demo_state("home")
        original = deepcopy(state)

        flow = derive_teacher_flow(state)

        self.assertEqual(flow["totalCount"], 31)
        self.assertEqual(state, original)


if __name__ == "__main__":
    unittest.main()
