"""Model-free marking for quick end-to-end tests of the teacher UI.

Launched only by launch-desktop-fake.cmd (``--fake-marking``). The real
pipeline, validation, workbook and feedback cards all run as usual; only the
marking model call is replaced by an instant, clearly labelled fake result.
Job files go to a separate test project folder so fake results never count
as finished marking for a real task.
"""
from __future__ import annotations

import json
from pathlib import Path

from grading.schemas import CRITERIA, ROOT


FAKE_PROJECT_DIR = ROOT / "test-runs" / "fake-marking"


class FakeGrader:
    """Returns a valid, obviously fake marking result without any model call."""

    def ensure_ready(self):
        pass

    def grade(self, request) -> dict:
        output = {
            "reading_quality": {
                "complete_essay_legible": True,
                "uncertainties": [],
                "materially_affects_grade": False,
            },
            "grading": {
                **request.identity.to_dict(),
                "criteria": {
                    name: {"rating": "可以更进一步", "short_comment": f"【测试】{name}：这是测试模式的假评语，没有调用模型。"}
                    for name in CRITERIA
                },
                "teacher_comment": "【测试模式】这不是真实批改。本评语由测试程序生成，用于检查整个流程能否顺利完成，没有调用任何模型。",
            },
            "evidence": [{"judgment": CRITERIA[0], "page_numbers": [1], "rationale": "【测试】测试模式：没有真实阅读作文。"}],
        }
        return {"provider": "fake", "model": "fake", "status": "completed",
                "output_text": json.dumps(output, ensure_ascii=False)}


def fake_marking_controller(project_dir: Path = FAKE_PROJECT_DIR,
                            workflow_id: str = "sec2_hcl_composition_v1"):
    from application import WorkflowController
    from workflow.calibration_pipeline import CalibrationPipeline
    from workflow.pipeline import Pipeline

    def pipeline_factory(project_dir, batch_id, config_dir, *, workbook_path=None):
        def calibration_factory(work_dir, model_profile=None):
            return CalibrationPipeline(work_dir, config_dir=config_dir, model_profile=model_profile,
                                       grader_factory=FakeGrader)
        return Pipeline(project_dir, batch_id, config_dir=config_dir, allow_real=True,
                        real_pipeline_factory=calibration_factory, workbook_path=workbook_path)

    Path(project_dir).mkdir(parents=True, exist_ok=True)
    return WorkflowController(workflow_id, project_dir=project_dir, pipeline_factory=pipeline_factory)
