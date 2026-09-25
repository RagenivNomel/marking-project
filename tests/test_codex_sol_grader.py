import json
from io import BytesIO
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest import mock

from pypdf import PdfWriter

from grading.calibration_schema import response_json_schema
from grading.codex_sol_grader import CodexInvocationError, CodexSolGrader, render_pdf_pages, resolve_codex_executable
from grading.schemas import CRITERIA, RATINGS, Identity
from grading.sol_grader import SolGrader, SolGradingInput
from tests.local_temp import local_test_directory
from tests.test_sol_calibration import valid_output
from workflow.calibration_pipeline import CalibrationPipeline


class FakeCodexProcess:
    def __init__(self, output, *, exec_returncode=0, timeout=False):
        self.output = output
        self.exec_returncode = exec_returncode
        self.timeout = timeout
        self.calls = []
        self.exec_workspace_files = None

    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if command[1:3] == ["login", "status"]:
            return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        if command[1:4] == ["debug", "models", "--bundled"]:
            catalog = {"models": [
                {"slug": "gpt-5.6-sol", "input_modalities": ["text", "image"], "supported_reasoning_levels": [{"effort": "medium"}]},
                {"slug": "gpt-5.6-luna", "input_modalities": ["text", "image"], "supported_reasoning_levels": [{"effort": "xhigh"}]},
            ]}
            return SimpleNamespace(returncode=0, stdout=json.dumps(catalog), stderr="")
        if "exec" not in command:
            raise AssertionError(command)
        workspace = Path(kwargs["cwd"])
        self.exec_workspace_files = sorted(path.name for path in workspace.iterdir())
        if self.timeout:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        if self.exec_returncode:
            return SimpleNamespace(returncode=self.exec_returncode, stdout="", stderr="failure")
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(self.output, encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=self.output, stderr="")


def fake_renderer(pdf_bytes, workspace, dpi):
    if pdf_bytes != b"selected-pdf-only" or dpi != 200:
        raise AssertionError("Unexpected renderer input")
    paths = []
    for number in (1, 2):
        path = workspace / f"page_{number:03d}.png"
        path.write_bytes(f"page-{number}".encode("ascii"))
        paths.append(path)
    return paths


class CodexSolGraderTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory(self._testMethodName)
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.identity = Identity("SYNTHETIC-16", "合成学生", "SYNTHETIC-CLASS")
        limits = {
            "criterion_comment": {"preferred_min": 50, "preferred_max": 80, "hard_max": 90},
            "teacher_comment": {"preferred_min": 120, "preferred_max": 220, "hard_max": 300},
        }
        self.request = SolGradingInput(
            identity=self.identity,
            pdf_bytes=b"selected-pdf-only",
            pdf_sha256="test-sha256",
            essay_question=None,
            criteria=CRITERIA,
            ratings=RATINGS,
            rubric={"rubric_version": "qualitative-eight-criteria-v2"},
            text_limits=limits,
            response_schema=response_json_schema(limits),
            prompt="Only the selected student's permitted grading input.",
            prompt_version="sol-calibration-v2",
            reference_example="# 参考范例",
            reference_version="reference-example-v1",
            rubric_version="qualitative-eight-criteria-v2",
            schema_version="calibration-response-v2",
        )

    def grader(self, process):
        return CodexSolGrader(
            process_runner=process,
            page_renderer=fake_renderer,
            workspace_parent=self.root,
        )

    def test_installed_desktop_cli_is_found_without_inherited_codex_path(self):
        executable = self.root / "OpenAI" / "Codex" / "bin" / "installed" / "codex.exe"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"local test executable placeholder")
        with mock.patch("grading.codex_sol_grader.shutil.which", return_value=None), \
                mock.patch.dict("grading.codex_sol_grader.os.environ", {"LOCALAPPDATA": str(self.root)}):
            self.assertEqual(resolve_codex_executable("codex"), str(executable))
            self.assertEqual(self.grader(FakeCodexProcess("{}")).codex_executable, str(executable))

    def test_path_discovery_is_passed_as_absolute_executable_to_subprocess(self):
        executable = self.root / "codex.exe"
        executable.write_bytes(b"local test executable placeholder")
        with mock.patch("grading.codex_sol_grader.shutil.which", return_value=str(executable)):
            self.assertEqual(resolve_codex_executable("codex"), str(executable.resolve()))

    def test_successful_structured_output_uses_chatgpt_auth_and_fresh_ephemeral_exec(self):
        expected = valid_output(self.identity)
        process = FakeCodexProcess(json.dumps(expected, ensure_ascii=False))
        grader = self.grader(process)
        grader.ensure_ready()
        raw = grader.grade(self.request)
        self.assertEqual(json.loads(raw["output_text"]), expected)
        self.assertEqual(raw["provider"], "codex_cli_chatgpt")
        self.assertEqual(len(process.calls), 3)
        command, kwargs = process.calls[-1]
        for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--ask-for-approval") + 1], "never")
        self.assertLess(command.index("--ask-for-approval"), command.index("exec"))
        self.assertEqual(kwargs["input"], self.request.prompt)
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])

    def test_process_failure_is_reported_without_retry(self):
        process = FakeCodexProcess("", exec_returncode=7)
        with self.assertRaisesRegex(CodexInvocationError, "exited with code 7: failure"):
            self.grader(process).grade(self.request)
        self.assertEqual(sum("exec" in call[0] for call in process.calls), 1)

    def test_luna_xhigh_profile_uses_configured_model_and_reasoning(self):
        expected = valid_output(self.identity)
        process = FakeCodexProcess(json.dumps(expected, ensure_ascii=False))
        grader = CodexSolGrader(
            model="gpt-5.6-luna", reasoning_effort="xhigh",
            process_runner=process, page_renderer=fake_renderer, workspace_parent=self.root,
        )
        grader.ensure_ready()
        grader.grade(self.request)
        command, _ = process.calls[-1]
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-luna")
        self.assertEqual(command[command.index("--config") + 1], 'model_reasoning_effort="xhigh"')

    def test_timeout_is_reported_without_retry(self):
        process = FakeCodexProcess("", timeout=True)
        with self.assertRaisesRegex(CodexInvocationError, "timed out"):
            self.grader(process).grade(self.request)
        self.assertEqual(sum("exec" in call[0] for call in process.calls), 1)

    def test_malformed_output_is_returned_for_pipeline_json_validation(self):
        process = FakeCodexProcess("{malformed")
        raw = self.grader(process).grade(self.request)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(raw["output_text"])

    def test_workspace_contains_only_schema_and_selected_page_images(self):
        other = self.root / "other_student_secret.txt"
        other.write_text("must never enter Codex workspace", encoding="utf-8")
        process = FakeCodexProcess(json.dumps(valid_output(self.identity), ensure_ascii=False))
        grader = self.grader(process)
        grader.grade(self.request)
        self.assertEqual(process.exec_workspace_files, ["page_001.png", "page_002.png", "schema.json"])
        command, kwargs = process.calls[-1]
        workspace = Path(kwargs["cwd"]).resolve()
        attachment_paths = [Path(command[index + 1]).resolve() for index, value in enumerate(command) if value == "--image"]
        self.assertTrue(all(path.parent == workspace for path in attachment_paths))
        self.assertNotIn(str(other), " ".join(command))

    def test_approval_policy_is_a_global_flag_before_exec(self):
        command = self.grader(FakeCodexProcess("{}"))._command(
            self.root,
            self.root / "schema.json",
            self.root / "result.json",
            [self.root / "page_001.png"],
        )
        exec_index = command.index("exec")
        approval_index = command.index("--ask-for-approval")
        self.assertEqual(command[approval_index + 1], "never")
        self.assertLess(approval_index, exec_index)
        self.assertNotIn("--ask-for-approval", command[exec_index + 1:])

    def test_pdf_renderer_produces_ordered_png_pages(self):
        pdf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=300)
        writer.add_blank_page(width=200, height=300)
        writer.write(pdf)
        render_dir = self.root / "rendered"
        render_dir.mkdir()
        paths = render_pdf_pages(pdf.getvalue(), render_dir, 72)
        self.assertEqual([path.name for path in paths], ["page_001.png", "page_002.png"])
        self.assertTrue(all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in paths))

    def test_configured_backend_selects_codex_without_touching_existing_workflow_contract(self):
        pipeline = CalibrationPipeline()
        grader = pipeline._new_grader()
        self.assertIsInstance(grader, CodexSolGrader)
        self.assertEqual(grader.model, "gpt-5.6-sol")
        pipeline.model_config["backend"] = "openai_api"
        self.assertIsInstance(pipeline._new_grader(), SolGrader)

    def test_configured_luna_profile_selects_same_codex_grader(self):
        pipeline = CalibrationPipeline(model_profile="luna_xhigh")
        grader = pipeline._new_grader()
        self.assertIsInstance(grader, CodexSolGrader)
        self.assertEqual((grader.model, grader.reasoning_effort), ("gpt-5.6-luna", "xhigh"))


if __name__ == "__main__":
    unittest.main()
