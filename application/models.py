"""Application projections, not persisted assessment data or backend checkpoints."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Action(str, Enum):
    PREPARE_SUBMISSIONS = "PREPARE_SUBMISSIONS"
    CONFIRM_SUBMISSIONS = "CONFIRM_SUBMISSIONS"
    RUN_MARKING = "RUN_MARKING"
    REVIEW_EXCEL = "REVIEW_EXCEL"
    REFRESH_REVIEW_STATUS = "REFRESH_REVIEW_STATUS"
    RENDER_APPROVED = "RENDER_APPROVED"
    VIEW_OUTPUTS = "VIEW_OUTPUTS"
    RESOLVE_ATTENTION = "RESOLVE_ATTENTION"


@dataclass(frozen=True)
class Stage:
    key: str
    label: str
    human_gate: bool = False
    execution_wired: bool = False


@dataclass(frozen=True)
class AssignmentSource:
    """Explicit existing artifact locations. No directory creation or discovery outside these roots.

    job_roots may include a production batch and its associated calibration jobs.
    receipt_roots identify card job/output directories, not the whole repository.
    A source may be a raw continuous scan or an already-prepared split pile.
    The split pile is app-owned when it is derived from continuous_scan.
    """
    workbook: Path | None = None
    job_roots: tuple[Path, ...] = ()
    receipt_roots: tuple[Path, ...] = ()
    continuous_scan: Path | None = None
    split_pile: Path | None = None
    roster: Path | None = None
    identity_decisions: Path | None = None
    # The roster sheet is found by its headings unless named here. roster_class
    # is the class for every student when the roster has no 班级 column.
    roster_sheet: str | None = None
    roster_class: str | None = None
    config_dir: Path | None = None
    # Derived locations for app-managed outputs. These are populated by the
    # workflow adapter and are never teacher-selected inputs.
    results_directory: Path | None = None
    feedback_cards_directory: Path | None = None


@dataclass(frozen=True)
class Attention:
    code: str
    severity: str
    message: str
    technical_details: str = ""
    submission_id: str | None = None


@dataclass(frozen=True)
class SubmissionState:
    submission_id: str
    student_name: str | None = None
    class_name: str | None = None
    student_id: str | None = None
    identity_confirmed: bool = False
    grading_available: bool = False
    workbook_valid: bool = False
    review_status: str | None = None
    rendered: bool = False
    ready_to_render: bool = False
    evidence: tuple[str, ...] = ()
    attention: tuple[Attention, ...] = ()
    next_actions: tuple[Action, ...] = ()


@dataclass(frozen=True)
class AvailableAction:
    action: Action
    submission_ids: tuple[str, ...] = ()
    execution_wired: bool = False


@dataclass(frozen=True)
class Inspection:
    workflow_id: str
    display_name: str
    stages: tuple[Stage, ...]
    submissions: tuple[SubmissionState, ...] = ()
    attention: tuple[Attention, ...] = ()
    available_actions: tuple[AvailableAction, ...] = ()

    @property
    def summary(self) -> dict[str, int]:
        items = self.submissions
        issues = self.attention + tuple(a for s in items for a in s.attention)
        # Only a matching workbook result plus audit row is DONE.
        committed = sum(s.workbook_valid for s in items)
        return {
            "submissions": len(items),
            "grading_results_available": committed,
            "committed_results": committed,
            "committed_results_available": committed,
            "approved": sum(s.workbook_valid and s.review_status == "APPROVED" for s in items),
            "awaiting_review": sum(s.workbook_valid and s.review_status == "PENDING" for s in items),
            "rendered": sum(s.rendered for s in items),
            "ready_to_render": sum(s.ready_to_render for s in items),
            "submissions_needing_attention": sum(bool(s.attention) for s in items),
            "blocking_errors": sum(a.severity == "error" for a in issues),
            "marking_available": sum(
                Action.RUN_MARKING in s.next_actions for s in items
            ),
        }
