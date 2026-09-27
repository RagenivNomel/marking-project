"""The prebuilt workflows a teacher can choose from on the start page.

Each workflow owns its own implementation (grader skill, Excel result model,
card renderer). This list holds only what the start page shows and the class
that runs the workflow. To add a workflow, write its module next to
sec2_hcl_composition_v1.py and add one entry to WORKFLOWS.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import sec2_hcl_composition_v1 as sec2_hcl_composition


@dataclass(frozen=True)
class WorkflowInfo:
    workflow_id: str
    name_zh: str
    name_en: str
    description_zh: str
    description_en: str
    workflow_class: type

    def to_dict(self):
        """Plain values for the teacher start page."""
        return {
            "id": self.workflow_id,
            "nameZh": self.name_zh,
            "nameEn": self.name_en,
            "descriptionZh": self.description_zh,
            "descriptionEn": self.description_en,
        }


WORKFLOWS = (
    WorkflowInfo(
        workflow_id=sec2_hcl_composition.WORKFLOW_ID,
        name_zh=sec2_hcl_composition.DISPLAY_NAME,
        name_en="Secondary 2 Higher Chinese Composition",
        description_zh="连续扫描 PDF 和学生名册 → 核对学生 → AI 批改 → Excel 审核 → 学生体检卡",
        description_en="Continuous-scan PDF and class roster → confirm students → AI marking → Excel review → student cards",
        workflow_class=sec2_hcl_composition.CompositionWorkflow,
    ),
)


def get_workflow(workflow_id):
    for info in WORKFLOWS:
        if info.workflow_id == workflow_id:
            return info
    raise ValueError(f"Unsupported workflow: {workflow_id}")
