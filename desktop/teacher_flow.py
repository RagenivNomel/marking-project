"""Derive the ordinary teacher journey from an existing desktop projection.

The desktop bridge already exposes a read-only projection of Stage 1 evidence.
This module turns that projection into one current step and one primary action
for a normal teacher-facing workspace.  It deliberately does not call a
controller, open a file, or change the supplied state.

Both :class:`application.models.Inspection` and the mapping returned by
``desktop.projection.project`` are accepted.  Accepting both keeps this small
adapter useful before and after the QML-facing projection is assembled.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from application.models import Action, Inspection


STAGE_KEYS = ("preparation", "marking", "review", "feedback")
STAGE_LABELS = {
    "zh": ("作文准备", "批改", "教师审核", "生成反馈"),
    "en": ("Preparation", "Marking", "Teacher Review", "Feedback Output"),
}


def _language(language: str | None) -> str:
    return "en" if language == "en" else "zh"


def _number(value: Any, default: int = 0) -> int:
    """Read a non-negative count without trusting arbitrary projection data."""

    if isinstance(value, bool):
        return int(value)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, value)


def _committed_results(summary: Mapping[str, Any]) -> int:
    """Return authoritative DONE rows, with compatibility fallbacks."""

    if "committed_results" in summary:
        return _number(summary.get("committed_results"))
    if "workbook_valid" in summary:
        return _number(summary.get("workbook_valid"))
    return _number(summary.get("grading_results_available"))


def _action_name(value: Any) -> str:
    if isinstance(value, Action):
        return value.value
    return str(value or "")


def _inspection_view(inspection: Inspection) -> dict[str, Any]:
    """Build the small evidence view needed by :func:`derive_teacher_flow`."""

    summary = dict(inspection.summary)
    summary["identity_confirmed"] = sum(
        item.identity_confirmed for item in inspection.submissions
    )
    summary["identities"] = len(
        {
            (item.class_name, item.student_id)
            for item in inspection.submissions
            if item.class_name and item.student_id
        }
    )
    summary["workbook_valid"] = sum(
        item.workbook_valid for item in inspection.submissions
    )
    summary["unconfirmed"] = sum(
        not item.identity_confirmed for item in inspection.submissions
    )
    attention = [
        {"details": f"{item.code}\n{item.technical_details}", "message": item.message}
        for item in inspection.attention
    ]
    for submission in inspection.submissions:
        for item in submission.attention:
            attention.append({
                "details": f"{item.code}\n{item.technical_details}",
                "message": item.message,
            })
    rows = [
        {"tone": "attention" if item.attention else "", "status": item.review_status or ""}
        for item in inspection.submissions
    ]
    actions = [
        {
            "action": available.action.value,
            "submissionIds": list(available.submission_ids),
            "executionWired": bool(available.execution_wired),
        }
        for available in inspection.available_actions
    ]
    return {
        "summary": summary,
        "attention": attention,
        "rows": rows,
        "actionAdvice": actions,
        "progress": {},
        "language": "zh",
        "demo": False,
    }


def _evidence_view(state: Mapping[str, Any] | Inspection) -> dict[str, Any]:
    if isinstance(state, Inspection):
        return _inspection_view(state)
    if not isinstance(state, Mapping):
        raise TypeError("teacher flow requires a projection mapping or Inspection")
    # Shallow copies are enough: this function only reads nested values.
    summary = dict(state.get("summary") or {})
    view = dict(state)
    view["summary"] = summary
    view["attention"] = list(state.get("attention") or ())
    view["rows"] = list(state.get("rows") or ())
    view["actionAdvice"] = list(state.get("actionAdvice") or ())
    view["progress"] = dict(state.get("progress") or {})
    return view


def _action_advice(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    advice: dict[str, dict[str, Any]] = {}
    for item in state.get("actionAdvice", ()):
        if not isinstance(item, Mapping):
            continue
        action = _action_name(item.get("action"))
        if action:
            advice[action] = dict(item)
    return advice


def _attention_items(state: Mapping[str, Any]) -> list[Any]:
    items = list(state.get("attention") or ())
    # A projection normally promotes row issues to state['attention'].  Keep
    # this fallback for small hand-built projections and future adapters.
    if not items:
        items = [row for row in state.get("rows", ()) if isinstance(row, Mapping) and row.get("tone") == "attention"]
    return items


def _attention_codes(items: list[Any]) -> set[str]:
    codes: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        details = str(item.get("details") or "")
        code = details.splitlines()[0].strip() if details else ""
        if code:
            codes.add(code)
    return codes


def _has_progress(state: Mapping[str, Any]) -> bool:
    progress = state.get("progress") or {}
    if not isinstance(progress, Mapping) or not progress:
        return False
    total = _number(progress.get("total"))
    completed = _number(progress.get("completed"))
    active = _number(progress.get("active"))
    waiting = _number(progress.get("waiting"))
    attention = _number(progress.get("attention"))
    if progress.get("running") is True:
        return total > 0 and completed + active + waiting + attention <= total
    return total > 0 and completed + active + waiting + attention <= total and active > 0


@dataclass(frozen=True)
class TeacherFlow:
    """The one-page teacher presentation derived from saved evidence.

    ``primary_action_enabled`` is true only for the safe, read-only refresh
    action when the projection explicitly marks it as wired.  This preserves
    Stage 2B.1's non-production boundary even when a state says that marking,
    Excel opening, or card generation would be the next conceptual step.
    """

    step: str
    stage: str
    stage_index: int
    stage_label: str
    headline: str
    detail: str
    tone: str
    primary_action: str | None
    primary_action_label: str
    primary_action_enabled: bool
    primary_action_execution_wired: bool
    read_only: bool
    attention_count: int
    completed_count: int
    total_count: int
    stage_progress: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a QML-friendly mapping while retaining Pythonic aliases."""

        progress = list(self.stage_progress)
        return {
            "step": self.step,
            "stage": self.stage,
            "stageIndex": self.stage_index,
            "stageLabel": self.stage_label,
            "headline": self.headline,
            "detail": self.detail,
            "tone": self.tone,
            "primaryAction": self.primary_action,
            "primaryActionLabel": self.primary_action_label,
            "primaryActionEnabled": self.primary_action_enabled,
            "primaryActionExecutionWired": self.primary_action_execution_wired,
            "readOnly": self.read_only,
            "attentionCount": self.attention_count,
            "completedCount": self.completed_count,
            "totalCount": self.total_count,
            "stageProgress": progress,
            # Snake-case aliases make the pure-Python contract convenient for
            # tests and non-QML callers without changing the QML shape.
            "primary_action": self.primary_action,
            "primary_action_label": self.primary_action_label,
            "primary_action_enabled": self.primary_action_enabled,
        }


def _labels(language: str, action: str | None, step: str, count: int, total: int) -> tuple[str, str]:
    en = language == "en"
    if step == "choose_essays":
        return (("Choose essays", "Select the essays for this task") if en else ("选择作文", "请选择这次要批改的作文"))
    if step == "resolve_identity":
        return (("Confirm student information", "Confirm the student for each remaining submission")
                if en else ("确认学生资料", "请确认每份作文对应的学生。"))
    if step == "resolve_attention":
        if action == Action.CONFIRM_SUBMISSIONS.value:
            return ((f"Handle {count} issue{'s' if count != 1 else ''} first", "Confirm the student information, then continue")
                    if en else (f"先处理{count}个问题", "请确认学生资料，完成后继续"))
        return (("Review task details", "The saved work remains available; check the task details")
                if en else ("查看任务详情", "已保存的结果仍然保留；请先查看任务详情"))
    if step == "ready_to_mark":
        return (("Start marking", f"{total} essays are ready to be marked")
                if en else ("开始批改", f"{total}份作文已准备好，可以开始批改"))
    if step == "marking_start_failed":
        return (("Continue marking", "Only unfinished essays will be processed")
                if en else ("继续批改", "只会处理尚未完成的作文"))
    if step == "resume_marking":
        saved = max(0, total - count)
        return (("Continue marking", f"{saved} saved · {count} essay{'s' if count != 1 else ''} remain")
                if en else ("继续批改", f"{saved}份已保存 · 还有{count}份作文待批改"))
    if step == "marking":
        return (("Marking in progress", "The saved demo progress is shown for inspection; no live queue is connected")
                if en else ("批改进行中", "当前显示的是演示进度；尚未连接实时批改队列"))
    if step == "review":
        if action == Action.REFRESH_REVIEW_STATUS.value:
            return (("Re-read and check Excel", "Save the reviewed workbook, then read it again")
                    if en else ("重新读取并检查 Excel", "请保存审核后的工作簿，然后重新读取检查"))
        if action == Action.REVIEW_EXCEL.value:
            return (("Open marking results in Excel", f"{count} saved result{'s are' if count != 1 else ' is'} ready for review")
                    if en else ("打开批改结果 Excel", f"{count}份已保存结果可以开始审核"))
        return (("Open marking results in Excel", f"{count} essay{'s' if count != 1 else ''} still await teacher review")
                if en else ("打开批改结果 Excel", f"还有{count}份作文等待教师审核"))
    if step == "generate":
        return ((f"Generate {count} feedback card{'s' if count != 1 else ''}", f"{count} approved essay{'s' if count != 1 else ''} are ready")
                if en else (f"生成{count}张作文体检卡", f"{count}份作文已审核，可以生成体检卡"))
    if step == "partial_failure":
        if action == Action.RUN_MARKING.value:
            return (("Continue marking", "Only unfinished essays will be processed")
                    if en else ("继续批改", "只会处理尚未完成的作文"))
        return (("Review task details", f"{count} item{'s' if count != 1 else ''} need attention")
                if en else ("查看任务详情", f"还有{count}份需要处理"))
    if step == "complete":
        return (("Open feedback-card folder", f"{total} feedback card{'s' if total != 1 else ''} are ready")
                if en else ("打开体检卡文件夹", f"{total}张作文体检卡已生成"))
    return (("Continue", "Review the saved evidence") if en else ("继续", "请查看已保存的资料"))


def _choose_action(step: str, count: int, state: Mapping[str, Any], advice: Mapping[str, Mapping[str, Any]]) -> str | None:
    if step == "choose_essays":
        return Action.PREPARE_SUBMISSIONS.value
    if step == "resolve_identity":
        return Action.CONFIRM_SUBMISSIONS.value
    if step == "resolve_attention":
        codes = _attention_codes(_attention_items(state))
        summary = state.get("summary") or {}
        if (_number(summary.get("unconfirmed")) > 0
                or _number(summary.get("submissions")) > _number(summary.get("identity_confirmed"))):
            return Action.CONFIRM_SUBMISSIONS.value
        if any(code.startswith(("IDENTITY_", "SUBMISSION_LINK")) for code in codes):
            return Action.CONFIRM_SUBMISSIONS.value
        if Action.CONFIRM_SUBMISSIONS.value in advice and not codes:
            return Action.CONFIRM_SUBMISSIONS.value
        return Action.RESOLVE_ATTENTION.value
    if step in {"ready_to_mark", "resume_marking", "marking", "marking_start_failed"}:
        return Action.RUN_MARKING.value
    if step == "review":
        summary = state.get("summary") or {}
        if _number(summary.get("awaiting_review")) > 0:
            return Action.REVIEW_EXCEL.value
        if Action.REFRESH_REVIEW_STATUS.value in advice:
            return Action.REFRESH_REVIEW_STATUS.value
        return Action.REVIEW_EXCEL.value
    if step == "generate":
        return Action.RENDER_APPROVED.value
    if step == "partial_failure":
        if _number((state.get("summary") or {}).get("marking_available")) > 0:
            return Action.RUN_MARKING.value
        return Action.RESOLVE_ATTENTION.value
    if step == "complete":
        return Action.VIEW_OUTPUTS.value
    return None


def derive_teacher_flow(
    state: Mapping[str, Any] | Inspection,
    language: str | None = None,
) -> dict[str, Any]:
    """Map saved state evidence to one normal step and primary action.

    The returned dictionary is presentation data only. Consequential actions
    are enabled only when Stage 1 advertises their matching execution path.
    """

    view = _evidence_view(state)
    language = _language(language or view.get("language"))
    summary = view.get("summary") or {}
    total = _number(summary.get("submissions"))
    rendered = _number(summary.get("rendered"))
    approved = _number(summary.get("approved"))
    awaiting = _number(summary.get("awaiting_review"))
    ready = _number(summary.get("ready_to_render"))
    confirmed = _number(summary.get("identity_confirmed"))
    unconfirmed = _number(summary.get("unconfirmed"), max(0, total - confirmed))
    committed = _committed_results(summary)
    graded = committed
    workbook_valid = _number(summary.get("workbook_valid"), committed)
    review_complete = total > 0 and graded == total and workbook_valid == total
    marking_available = _number(summary.get("marking_available"))
    attention_items = _attention_items(view)
    # Identity confirmation is represented by the summary in some fixtures
    # and by warning items in real inspections. Count both forms as an
    # actionable interruption, without merging submissions by visible name.
    attention = max(
        len(attention_items),
        _number(summary.get("submissions_needing_attention")),
        unconfirmed,
        (_number((view.get("progress") or {}).get("attention"))
         if (view.get("progress") or {}).get("running") is True else 0),
    )
    advice = _action_advice(view)
    attention_codes = _attention_codes(attention_items)

    if total == 0 and not attention_items:
        step = "choose_essays"
        stage_index = 0
        tone = "neutral"
    elif rendered >= total > 0 and attention == 0:
        step = "complete"
        stage_index = 3
        tone = "complete"
    elif rendered > 0 and attention > 0:
        step = "partial_failure"
        stage_index = 3
        tone = "attention"
    elif unconfirmed > 0:
        # Marking must not outrun the identity gate. The action is advertised
        # only after every selected submission is confirmed.
        step = "resolve_identity"
        stage_index = 0
        tone = "pending"
    elif (attention_codes == {"MARKING_STARTUP_FAILED"}
          and unconfirmed == 0 and marking_available > 0):
        step = "marking_start_failed"
        stage_index = 1
        tone = "attention"
    elif unconfirmed > 0 or attention > 0:
        step = "resolve_attention"
        stage_index = 0 if rendered == 0 and approved == 0 else 3
        tone = "attention"
    elif _has_progress(view):
        step = "marking"
        stage_index = 1
        tone = "active"
    elif marking_available > 0 and committed > 0:
        step = "resume_marking"
        stage_index = 1
        tone = "active"
    elif awaiting > 0 and review_complete:
        step = "review"
        stage_index = 2
        tone = "pending"
    elif awaiting > 0:
        # Workbook rows alone do not prove that the assignment is complete.
        step = "resolve_attention"
        stage_index = 2
        tone = "attention"
        attention = max(attention, 1)
    elif ready > 0 or (approved > rendered and approved > 0):
        step = "generate"
        stage_index = 3
        tone = "complete"
    elif total > 0 and rendered == 0:
        step = "ready_to_mark"
        stage_index = 1
        tone = "pending"
    else:
        step = "review"
        stage_index = 2
        tone = "pending"

    action = _choose_action(step, attention, view, advice)
    # Identity-only preparation is one decision per unresolved submission.
    # Keep the count aligned with the confirmation workspace instead of
    # including the aggregate source warning that accompanies those rows.
    if step == "resolve_identity":
        attention = unconfirmed
    if step == "generate":
        action_count = ready or max(0, approved - rendered)
    elif step == "resume_marking":
        action_count = marking_available
    elif step == "marking_start_failed":
        action_count = marking_available
    elif step in {"review", "resolve_identity", "resolve_attention", "partial_failure"}:
        action_count = awaiting if step == "review" else attention
    else:
        action_count = total
    action_label, detail = _labels(language, action, step, action_count, total)
    if step == "complete":
        detail = (f"{total} marked · {approved} approved · {rendered} feedback cards generated"
                  if language == "en" else f"{total}份作文已批改 · {approved}份已审核 · {rendered}张体检卡已生成")
    action_entry = advice.get(action or "", {})
    identity_confirmation = step == "resolve_identity" and action == Action.CONFIRM_SUBMISSIONS.value
    action_wired = bool(action_entry.get("executionWired")) or identity_confirmation
    if action == Action.REVIEW_EXCEL.value:
        action_enabled = bool(view.get("resultsWorkbookAvailable"))
    elif action == Action.VIEW_OUTPUTS.value:
        action_enabled = bool(view.get("feedbackCardsAvailable"))
    else:
        action_enabled = ((action in (Action.REFRESH_REVIEW_STATUS.value, Action.RUN_MARKING.value,
                                      Action.RENDER_APPROVED.value) and action_wired)
                          or identity_confirmation)

    if step == "choose_essays":
        headline = "Choose essays" if language == "en" else "选择作文"
    elif step == "resolve_identity":
        headline = (f"{unconfirmed} submission{'s' if unconfirmed != 1 else ''} need student confirmation"
                    if language == "en" else f"{unconfirmed}份作文需要确认学生资料")
    elif step == "resolve_attention":
        headline = (f"{attention} item{'s' if attention != 1 else ''} need attention"
                    if language == "en" else f"有{attention}份需要处理")
    elif step == "ready_to_mark":
        headline = ("The essays are ready ✓" if language == "en" else "作文已经准备好 ✓")
        identities = _number(summary.get("identities"), confirmed)
        detail = (f"{total} submissions · {identities} students\nAll required student information has been confirmed."
                  if language == "en" else f"{total}份作文 · {identities}名学生\n所有需要确认的学生资料已经处理。")
    elif step == "marking":
        headline = ("Marking submissions" if language == "en" else "正在批改作文")
    elif step == "marking_start_failed":
        headline = ("Marking could not start" if language == "en" else "批改未能开始")
        detail = (("Your essays are still ready. Saved results remain safe. Check the details or continue.")
                  if language == "en" else "作文仍已准备好，已保存的结果也会保留。请查看详情后继续。")
    elif step == "resume_marking":
        saved = committed
        remaining = max(0, total - saved)
        headline = (f"{saved} of {total} saved · {remaining} still to mark" if language == "en"
                    else f"已保存{saved}/{total}份 · 还有{remaining}份待批改")
    elif step == "review":
        headline = ("Teacher review is ready ✓" if language == "en" else "教师审核已就绪 ✓")
        detail = (f"{awaiting} saved result{'s are' if awaiting != 1 else ' is'} in the workbook and ready for teacher review."
                  if language == "en" else f"批改结果工作簿已保存，{awaiting}份作文可以开始教师审核。")
    elif step == "generate":
        headline = (f"{action_count} feedback card{'s' if action_count != 1 else ''} can be generated"
                    if language == "en" else f"{action_count}份作文可以生成体检卡")
    elif step == "partial_failure":
        headline = (f"{rendered} / {total} generated successfully"
                    if language == "en" else f"{rendered} / {total} 已成功生成")
    else:
        headline = "All complete ✓" if language == "en" else "全部完成 ✓"

    statuses = ["complete" if index < stage_index else "current" if index == stage_index else "upcoming"
                for index in range(4)]
    result = TeacherFlow(
        step=step,
        stage=STAGE_KEYS[stage_index],
        stage_index=stage_index,
        stage_label=STAGE_LABELS[language][stage_index],
        headline=headline,
        detail=detail,
        tone=tone,
        primary_action=action,
        primary_action_label=action_label,
        primary_action_enabled=action_enabled,
        primary_action_execution_wired=action_wired,
        read_only=not (identity_confirmation or action in (
            Action.RUN_MARKING.value, Action.RENDER_APPROVED.value
        ) and action_enabled),
        attention_count=attention,
        completed_count=(committed
                         if step in ("marking", "resume_marking", "marking_start_failed") else rendered),
        total_count=total,
        stage_progress=tuple(statuses),
    ).to_dict()
    if action == Action.VIEW_OUTPUTS.value:
        result["actionReason"] = (
            "The feedback-card folder is not available yet."
            if language == "en" else "体检卡文件夹目前不可用。"
        ) if not view.get("feedbackCardsAvailable") else ""
    elif action == Action.REVIEW_EXCEL.value and not view.get("resultsWorkbookAvailable"):
        result["actionReason"] = (
            "The results workbook could not be found."
            if language == "en" else "找不到批改结果工作簿。"
        )
    return result


# A short alias is useful to callers that already use ``derive`` for pure
# projection helpers, while the descriptive name remains the public API.
derive = derive_teacher_flow


__all__ = ["TeacherFlow", "derive", "derive_teacher_flow"]
