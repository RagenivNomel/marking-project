"""Focused read-only tests for the desktop projection and Qt bridge."""

from contextlib import contextmanager, ExitStack
import hashlib
from pathlib import Path
import shutil
import sys
import time
import unittest
import uuid
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
LOCAL_DEPS = ROOT / ".desktop-deps"
if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

from PySide6.QtCore import QCoreApplication, QEventLoop

from application import AssignmentSource, WorkflowController
from application.models import Attention, Inspection, SubmissionState
from desktop.bridge import DesktopBridge
from desktop.fixtures import demo_state
from desktop.projection import DISABLED_REASON, project
from excel.workbook import ExcelStore
from grading.codex_sol_grader import CodexSolGrader
from grading.mock_grader import MockGrader
from grading.sol_grader import SolGrader
from rendering.renderer import PillowRenderer
from tests import test_application_workflow as workflow_fixtures
from workflow.calibration_pipeline import CalibrationPipeline
from workflow.pipeline import Pipeline
from workflow import calibration_pipeline as calibration_pipeline_module
from workflow import pipeline as pipeline_module
from workflow import storage as storage_module


TEST_TEMP_ROOT = ROOT / "design" / "stage-2b" / "test-temp"


class _Stage1Fixture:
    """Use the existing Stage 1 fixture builders under the stage-2b temp root."""

    def __init__(self):
        # Composition keeps unittest discovery from collecting all inherited
        # ApplicationWorkflowTests methods as part of this focused module.
        self._case = workflow_fixtures.ApplicationWorkflowTests("runTest")

    def __getattr__(self, name):
        return getattr(self._case, name)

    def setUp(self):
        case = self._case
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        case.root = TEST_TEMP_ROOT / f"bridge-{uuid.uuid4().hex}"
        case.root.mkdir()
        case.addCleanup(self._remove_temp_root)
        case.addCleanup(lambda: shutil.rmtree(case.root, ignore_errors=True))

        case.config_dir = case.root / "config"
        case.config_dir.mkdir()
        source_config = ROOT / "config"
        for config in source_config.glob("*.json"):
            shutil.copy2(config, case.config_dir / config.name)
        from grading.schemas import Validator

        case.validator = Validator(case.config_dir)
        case.workbook = case.root / "results.xlsx"
        case.jobs = case.root / "jobs"
        case.receipts = case.root / "receipts"
        case.controller = WorkflowController()

    @staticmethod
    def _remove_temp_root():
        try:
            TEST_TEMP_ROOT.rmdir()
        except OSError:
            pass

    def _source(self, *, receipt_roots=()):
        return AssignmentSource(
            workbook=self.workbook,
            receipt_roots=tuple(Path(path) for path in receipt_roots),
            config_dir=self.config_dir,
        )


@contextmanager
def _read_only_guards():
    """Fail if an inspection reaches any Stage 1 execution or persistence hook."""

    guards = (
        (ExcelStore, "_save", "inspection must not save Excel"),
        (PillowRenderer, "render", "inspection must not render"),
        (MockGrader, "grade", "inspection must not use the mock grader"),
        (CodexSolGrader, "grade", "inspection must not use Codex grading"),
        (SolGrader, "grade", "inspection must not use API grading"),
        (Pipeline, "run_mock", "inspection must not run a mock pipeline"),
        (Pipeline, "run_real_pdf", "inspection must not run real grading"),
        (Pipeline, "run_real_batch", "inspection must not run real batches"),
        (CalibrationPipeline, "prepare", "inspection must not prepare grading"),
        (CalibrationPipeline, "run", "inspection must not run calibration"),
        (storage_module, "atomic_json", "inspection must not write checkpoints"),
        (pipeline_module, "atomic_json", "inspection must not write pipeline JSON"),
        (
            calibration_pipeline_module,
            "atomic_json",
            "inspection must not write calibration JSON",
        ),
        (
            calibration_pipeline_module,
            "immutable_json",
            "inspection must not write calibration snapshots",
        ),
        (
            calibration_pipeline_module,
            "immutable_text",
            "inspection must not write calibration text snapshots",
        ),
    )
    with ExitStack() as stack:
        for target, attribute, message in guards:
            stack.enter_context(
                patch.object(target, attribute, side_effect=AssertionError(message))
            )
        yield


def _file_stamp(path):
    path = Path(path)
    stat = path.stat()
    return hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns


def _wait_for_bridge(bridge, app, timeout=10.0):
    deadline = time.monotonic() + timeout
    while bridge.busy and time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        time.sleep(0.005)
    app.processEvents(QEventLoop.AllEvents, 50)


class ProjectionTests(unittest.TestCase):
    def test_english_variant_localizes_teacher_facing_state(self):
        state = demo_state("marking", "en")

        self.assertEqual(state["language"], "en")
        self.assertEqual(state["sections"], ["Preparation", "AI Marking", "Teacher Review", "Feedback Output"])
        self.assertEqual(state["hero"]["title"], "AI is marking submissions")
        self.assertEqual({row["status"] for row in state["rows"]}, {"✓ Complete", "● In progress", "○ Waiting"})
        self.assertIn("张瑞颖", state["rows"][16]["identity"])

    def test_demo_keeps_duplicate_identity_rows_distinct(self):
        state = demo_state("home")

        self.assertEqual(state["summary"]["submissions"], 31)
        self.assertEqual(state["summary"]["identities"], 30)
        self.assertEqual(len({row["id"] for row in state["rows"]}), 31)
        duplicate_rows = [row for row in state["rows"] if "207 · 20 · 张瑞颖" in row["identity"]]
        self.assertEqual([row["id"] for row in duplicate_rows], ["demo-017", "demo-018"])

    def test_projection_preserves_mixed_approved_pending_rendered_counts(self):
        inspection = Inspection(
            "fixture",
            "Fixture",
            (),
            submissions=(
                SubmissionState(
                    "approved", "A", "207", "001", True, True, True, "APPROVED"
                ),
                SubmissionState(
                    "pending", "B", "207", "002", True, True, True, "PENDING"
                ),
                SubmissionState(
                    "rendered", "C", "207", "003", True, True, True, "APPROVED", True
                ),
            ),
        )

        state = project(inspection, title="Fixture")

        self.assertEqual(
            {
                key: state["summary"][key]
                for key in ("submissions", "approved", "awaiting_review", "rendered")
            },
            {"submissions": 3, "approved": 2, "awaiting_review": 1, "rendered": 1},
        )
        self.assertEqual(
            [row["status"] for row in state["rows"]],
            ["✓ 已审核", "○ 待审核", "✓ 已生成"],
        )

    def test_attention_mapping_preserves_exact_message(self):
        state = demo_state("attention")
        expected = (
            "教师总评超出当前版面可以容纳的长度。原有评语没有被修改，其他30张体检卡已正常生成。"
            "请回到 Excel 检查总评；如需修改，由您决定措辞。"
        )

        matches = [item for item in state["attention"] if item["message"] == expected]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["details"].splitlines()[0], "DEMO_LAYOUT_OVERFLOW")

    def test_long_attention_messages_are_not_truncated(self):
        message = "长评语·" * 2048
        details = "技术细节·" * 2048
        inspection = Inspection(
            "fixture",
            "Fixture",
            (),
            submissions=(
                SubmissionState(
                    "long", "长名字", "207", "009", True, True, True, "PENDING",
                    attention=(Attention("LONG_MESSAGE", "error", message, details, "long"),),
                ),
            ),
        )

        state = project(inspection, title="Fixture")

        self.assertEqual(state["attention"][0]["message"], message)
        self.assertEqual(state["attention"][0]["details"], f"LONG_MESSAGE\n{details}")
        self.assertEqual(state["rows"][0]["details"].splitlines()[-2:], [f"保存记录：无", f"LONG_MESSAGE: {details}"])

    def test_demo_progress_adds_up_to_total_and_labels_waiting_truthfully(self):
        state = demo_state("marking")
        progress = state["progress"]

        self.assertEqual(
            progress["completed"] + progress["active"] + progress["waiting"] + progress["attention"],
            progress["total"],
        )
        self.assertEqual(
            {row["status"] for row in state["rows"]},
            {"✓ 已完成", "● 处理中", "○ 等待中"},
        )
        self.assertIn("没有连接实时批改队列", state["hero"]["subtitle"])

    def test_real_projection_exposes_no_live_progress_and_disables_execution(self):
        inspection = Inspection("fixture", "Fixture", (), ())
        source = AssignmentSource(workbook=ROOT / "fixture.xlsx")

        state = project(inspection, source, title="Fixture")

        self.assertFalse(state["demo"])
        self.assertEqual(state["scenario"], "real")
        self.assertEqual(state["progress"], {})
        self.assertEqual(state["disabledReason"], DISABLED_REASON)
        self.assertNotIn("实时", state["notice"])
        self.assertIn(state["teacherFlow"]["step"], {"choose_essays", "ready_to_mark"})
        self.assertFalse(state["teacherFlow"]["primaryActionEnabled"])


class BridgeTests(unittest.TestCase):
    def test_language_switch_preserves_scenario_and_read_only_boundary(self):
        class NoCallController:
            def inspect(self, source):
                raise AssertionError("language switching must not inspect")

            def refresh_review_status(self, source):
                raise AssertionError("language switching must not refresh")

        bridge = DesktopBridge(controller=NoCallController())
        bridge.selectDemo("attention")
        bridge.setLanguage("en")

        self.assertEqual(bridge.language, "en")
        self.assertEqual(bridge.state["scenario"], "attention")
        self.assertEqual(bridge.state["hero"]["title"], "30 generated, 1 not generated.")
        self.assertFalse(hasattr(bridge, "execute"))
        bridge.setLanguage("zh")
        self.assertEqual(bridge.state["hero"]["title"], "30张已生成，1张未生成。")
        bridge.shutdown()

    def test_navigation_demo_and_disabled_bridge_api_do_not_call_controller_or_write(self):
        class NoCallController:
            def inspect(self, source):
                raise AssertionError("navigation/demo must not inspect")

            def refresh_review_status(self, source):
                raise AssertionError("navigation/demo must not refresh")

        bridge = DesktopBridge(controller=NoCallController())
        bridge.navigate("workspace")
        bridge.selectSection(2)
        bridge.setReducedMotion(True)
        bridge.selectDemo("marking")
        state = bridge.state
        bridge.selectDemo("real")
        bridge.selectDemo("unknown-demo")
        bridge.refresh()

        self.assertEqual(bridge.state["scenario"], "marking")
        self.assertTrue(state["reducedMotion"])
        self.assertEqual(state["progress"]["total"], 31)
        self.assertEqual(state["disabledReason"], DISABLED_REASON)
        self.assertFalse(hasattr(bridge, "execute"))
        self.assertEqual(bridge.metaObject().indexOfMethod("execute()"), -1)
        bridge.shutdown()

    def test_real_stage1_inspection_projects_mixed_fixture_read_only(self):
        fixture = _Stage1Fixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        approved_identity = fixture._identity("016", "同名学生", "207")
        pending_identity = fixture._identity("017", "同名学生", "207")
        approved_store, approved_digest = fixture._add_workbook_row(
            "approved-job", approved_identity, "APPROVED"
        )
        fixture._add_workbook_row("pending-job", pending_identity, "PENDING")
        fixture._write_receipt("approved-job", approved_identity, approved_store, approved_digest)
        source = fixture._source(receipt_roots=(fixture.receipts,))
        before = _file_stamp(fixture.workbook)

        with _read_only_guards():
            inspection = fixture.controller.inspect(source)

        self.assertEqual(_file_stamp(fixture.workbook), before)
        self.assertEqual(len(inspection.submissions), 2)
        approved = next(item for item in inspection.submissions if item.submission_id == "approved-job")
        pending = next(item for item in inspection.submissions if item.submission_id == "pending-job")
        self.assertTrue(approved.rendered)
        self.assertEqual(approved.review_status, "APPROVED")
        self.assertEqual(pending.review_status, "PENDING")
        self.assertEqual(inspection.summary["approved"], 1)
        self.assertEqual(inspection.summary["awaiting_review"], 1)
        self.assertEqual(inspection.summary["rendered"], 1)

        state = project(inspection, source, title="Fixture")
        self.assertEqual(state["progress"], {})
        self.assertIn("本地作文任务", state["notice"])

    def test_bridge_async_inspect_and_refresh_are_read_only(self):
        fixture = _Stage1Fixture()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        approved_identity = fixture._identity("016", "异步学生", "207")
        pending_identity = fixture._identity("017", "异步学生", "207")
        approved_store, approved_digest = fixture._add_workbook_row(
            "async-approved", approved_identity, "APPROVED"
        )
        pending_store, _ = fixture._add_workbook_row("async-pending", pending_identity, "PENDING")
        fixture._write_receipt("async-approved", approved_identity, approved_store, approved_digest)
        source = fixture._source(receipt_roots=(fixture.receipts,))

        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = DesktopBridge(controller=fixture.controller)
        self.addCleanup(bridge.shutdown)

        with _read_only_guards():
            before = _file_stamp(fixture.workbook)
            bridge.inspect_source(source)
            _wait_for_bridge(bridge, app)
        self.assertFalse(bridge.busy)
        self.assertEqual(_file_stamp(fixture.workbook), before)
        self.assertFalse(bridge.state["demo"])
        self.assertEqual(bridge.state["progress"], {})
        self.assertEqual(bridge.state["summary"]["awaiting_review"], 1)

        pending_store.set_status("async-pending", pending_identity, "APPROVED", "APPROVED")
        after_external_change = _file_stamp(fixture.workbook)
        with _read_only_guards():
            bridge.refresh()
            _wait_for_bridge(bridge, app)

        self.assertFalse(bridge.busy)
        self.assertEqual(_file_stamp(fixture.workbook), after_external_change)
        self.assertEqual(bridge.state["summary"]["approved"], 2)
        self.assertEqual(bridge.state["summary"]["awaiting_review"], 0)
        self.assertEqual(bridge.state["progress"], {})


if __name__ == "__main__":
    unittest.main()
