"""Editable instructions reach the provider while prepared jobs remain stable."""
from pathlib import Path
import unittest

from pypdf import PdfWriter

from grading.schemas import Identity, ValidationError
from grading.sol_grader import SolGrader
from tests.local_temp import local_test_directory
from tests.test_calibration_namespace import RecordingTransport
from workflow.calibration_pipeline import CalibrationPipeline, sha256_file
from workflow.storage import read_json


class MarkerSkillTests(unittest.TestCase):
    def setUp(self):
        temp = local_test_directory("marker-skill")
        self.root = Path(temp.__enter__())
        self.addCleanup(temp.__exit__, None, None, None)
        self.identity = Identity("26", "测试学生", "207")
        self.source = self.root / "essay.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with self.source.open("wb") as stream:
            writer.write(stream)
        self.skill = self.root / "SKILL.md"
        self.skill.write_text("Use style A for this test.\n", encoding="utf-8")
        self.transport = RecordingTransport(self.identity)
        self.pipeline = CalibrationPipeline(
            self.root, marker_skill_path=self.skill,
            grader_factory=lambda: SolGrader(transport=self.transport),
        )

    def test_edit_affects_new_job_but_resume_sends_original_instructions(self):
        job, _, _ = self.pipeline.prepare(self.source, self.identity, execution_namespace="original")
        self.skill.write_text("Use style B for this test.\n", encoding="utf-8")
        self.pipeline.run(self.source, self.identity, execution_namespace="original")
        first_prompt = self.transport.calls[0]["input"][0]["content"][0]["text"]
        self.assertIn("Use style A", first_prompt)
        self.assertNotIn("Use style B", first_prompt)
        self.pipeline.run(self.source, self.identity, execution_namespace="revised")
        second_prompt = self.transport.calls[1]["input"][0]["content"][0]["text"]
        self.assertIn("Use style B", second_prompt)
        self.assertNotIn("Use style A", second_prompt)
        manifest = read_json(job / "grading_input_manifest.json")
        self.assertEqual(manifest["snapshot_sha256"]["marker_SKILL.md"], sha256_file(job / "marker_SKILL.md"))

    def test_changed_saved_skill_is_rejected_before_provider_call(self):
        job, _, _ = self.pipeline.prepare(self.source, self.identity)
        (job / "marker_SKILL.md").write_text("Modified snapshot", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "snapshot hash mismatch"):
            self.pipeline.run(self.source, self.identity)
        self.assertEqual(self.transport.calls, [])

    def test_empty_skill_is_rejected_before_provider_call(self):
        self.skill.write_text("\n  ", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "must not be empty"):
            self.pipeline.run(self.source, self.identity)
        self.assertEqual(self.transport.calls, [])


if __name__ == "__main__":
    unittest.main()
