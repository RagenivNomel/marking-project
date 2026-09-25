"""Deterministic teacher-facing output paths for one composition task."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskOutputPaths:
    results_directory: Path
    workbook: Path
    feedback_cards_directory: Path


def teacher_output_paths(task_root: Path) -> TaskOutputPaths:
    """Place one task's teacher outputs beside its selected essay folder."""
    results = Path(task_root).expanduser().resolve() / "Results"
    return TaskOutputPaths(
        results_directory=results,
        workbook=results / "results.xlsx",
        feedback_cards_directory=results / "Feedback Cards",
    )


def legacy_output_paths(project_dir: Path, batch_id: str) -> TaskOutputPaths:
    """Describe the pre-product-completion layout without moving its files."""
    results = Path(project_dir).expanduser().resolve() / "output" / batch_id
    return TaskOutputPaths(
        results_directory=results,
        workbook=results / "results.xlsx",
        feedback_cards_directory=results / "Feedback Cards",
    )
