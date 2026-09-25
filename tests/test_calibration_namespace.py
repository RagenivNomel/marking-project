import base64
import copy
import json
from pathlib import Path
import unittest

from pypdf import PdfWriter

from grading.schemas import CRITERIA, Identity, ROOT
from grading.sol_grader import SolGrader
from tests.local_temp import local_test_directory
from workflow.calibration_pipeline import CalibrationPipeline
from workflow.pipeline import Pipeline
from workflow.storage import read_json


def calibration_output(identity):
    return {
        "reading_quality": {
            "complete_essay_legible": True,
            "uncertainties": [],
            "materially_affects_grade": False,
        },
        "grading": {
            **identity.to_dict(),
            "criteria": {
                name: {"rating": "可以更进一步", "short_comment": f"{identity.student_id}号的{name}模拟评语。"}
                for name in CRITERIA
            },
            "teacher_comment": f"{identity.student_id}号模拟总评。",
        },
        "evidence": [{"judgment": "教师总评", "page_numbers": [1], "rationale": "独立测试证据。"}],
    }


class RecordingTransport:
    def __init__(self, identity):
        self.identity = identity
        self.calls = []
        self.fail = False

    def ensure_ready(self):
        return None

    def __call__(self, payload, timeout_seconds):
        if self.fail:
            raise AssertionError("resume unexpectedly invoked grader")
        self.calls.append(copy.deepcopy(payload))
        return {
            "id": "namespace-test",
            "model": "gpt-5.6-luna",
            "status": "completed",
            "output_text": json.dumps(calibration_output(self.identity), ensure_ascii=False),
        }


class CalibrationNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory("calibration-namespace")
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.identity = Identity("26", "王晨溪", "207")
        self.source = self.root / "essay.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with self.source.open("wb") as handle:
            writer.write(handle)

    def calibration_factory(self, transport):
        config_dir = ROOT / "config"
        def factory(project_dir, model_profile=None):
            profile = read_json(config_dir / "calibration_model.json")["profiles"][model_profile]
            return CalibrationPipeline(
                project_dir,
                config_dir=config_dir,
                model_profile=model_profile,
                grader_factory=lambda: SolGrader(
                    model=profile["model"],
                    reasoning_effort=profile["reasoning_effort"],
                    transport=transport,
                ),
            )
        return factory

    def test_different_execution_namespaces_have_distinct_jobs(self):
        pipeline = CalibrationPipeline(self.root, model_profile="luna_xhigh")
        first, _output, first_checkpoint = pipeline.prepare(
            self.source, self.identity, execution_namespace="preflight"
        )
        second, _output, second_checkpoint = pipeline.prepare(
            self.source, self.identity, execution_namespace="production"
        )
        self.assertNotEqual(first, second)
        self.assertIn("calibration_preflight_", first.name)
        self.assertIn("calibration_production_", second.name)
        self.assertEqual(first_checkpoint["execution_namespace"], "preflight")
        self.assertEqual(second_checkpoint["execution_namespace"], "production")

    def test_preflight_result_is_not_reused_by_production_namespace(self):
        transport = RecordingTransport(self.identity)
        factory = self.calibration_factory(transport)
        preflight = Pipeline(self.root, "preflight", allow_real=True, real_pipeline_factory=factory)
        preflight_result = preflight.run_real_pdf(self.source, self.identity, model_profile="luna_xhigh")
        production = Pipeline(self.root, "production", allow_real=True, real_pipeline_factory=factory)
        production_result = production.run_real_pdf(self.source, self.identity, model_profile="luna_xhigh")
        self.assertEqual(preflight_result["state"], "VALIDATED")
        self.assertEqual(production_result["state"], "VALIDATED")
        self.assertEqual(len(transport.calls), 2)
        preflight_bridge = read_json(Path(preflight_result["job_dir"]) / "real_grading_bridge.json")
        production_bridge = read_json(Path(production_result["job_dir"]) / "real_grading_bridge.json")
        self.assertNotEqual(preflight_bridge["calibration_job"], production_bridge["calibration_job"])
        self.assertIn("calibration_preflight_", Path(preflight_bridge["calibration_job"]).name)
        self.assertIn("calibration_production_", Path(production_bridge["calibration_job"]).name)

    def test_same_execution_namespace_resume_does_not_reinvoke_grader(self):
        transport = RecordingTransport(self.identity)
        pipeline = Pipeline(
            self.root, "production", allow_real=True,
            real_pipeline_factory=self.calibration_factory(transport),
        )
        first = pipeline.run_real_pdf(self.source, self.identity, model_profile="luna_xhigh")
        transport.fail = True
        resumed = pipeline.run_real_pdf(self.source, self.identity, model_profile="luna_xhigh")
        self.assertEqual(first["state"], "VALIDATED")
        self.assertEqual(resumed["state"], "VALIDATED")
        self.assertEqual(len(transport.calls), 1)
        checkpoint = read_json(Path(resumed["job_dir"]) / "student_record.json")
        self.assertEqual(checkpoint["execution_namespace"], "production")


if __name__ == "__main__":
    unittest.main()
