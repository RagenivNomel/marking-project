"""Teacher-facing identity confirmation over the existing intake contract."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import unicodedata

from application.models import AssignmentSource, Inspection
from excel.workbook import read_roster
from app_paths import data_root
from grading.schemas import ROOT, ValidationError
from scanning.identity import confirm_identity
from scanning.intake import apply_identity_decisions, read_existing_split
from scanning.roster_matcher import ensure_suggestions, header_preview_path, read_suggestions
from workflow.storage import atomic_json, read_json


DEFAULT_ROSTER = ROOT / "中二高华作文3评改终稿.xlsx"
# Dropdown value meaning "set this essay aside". It never matches a roster key.
SKIP_KEY = "__skip__"
SKIPPED_FOLDER = "跳过的作文"


def skipped_copy_path(source: AssignmentSource, submission) -> Path:
    """Where a skipped essay is saved so the teacher can open it as its own task.

    The folder sits beside the teacher's scan; the name keeps the scan name
    and the essay number, e.g. 跳过的作文/class-scan-作文005.pdf.
    """
    pile = source.split_pile.resolve()
    if source.continuous_scan is not None:
        stem = Path(source.continuous_scan).stem
    else:
        stem = re.sub(r"\.essay-work-[0-9a-f]+$", "", pile.name).lstrip(".") or "scan"
    return pile.parent / SKIPPED_FOLDER / f"{stem}-作文{submission.sequence:03}.pdf"


def _decision_stem(pile: Path) -> str:
    stem = pile.name
    if stem.lower().endswith("_test"):
        stem = stem[:-5]
    safe = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+", "_", stem).strip("._")
    return safe or "assignment"


def managed_decision_path(source: AssignmentSource) -> Path:
    if source.identity_decisions is not None:
        return source.identity_decisions.resolve()
    if source.split_pile is None:
        raise ValidationError("A composition folder is required for identity confirmation")
    config_dir = (source.config_dir or (data_root() / "config")).resolve()
    return config_dir / f"{_decision_stem(source.split_pile)}_identity_decisions.json"


def with_decisions_dir(source: AssignmentSource, directory: Path | None) -> AssignmentSource:
    """Keep this task's confirmations in ``directory`` (fake-marking test runs)."""
    if directory is None or source.split_pile is None or source.identity_decisions is not None:
        return source
    path = Path(directory) / f"{_decision_stem(source.split_pile)}_identity_decisions.json"
    return replace(source, identity_decisions=path.resolve())


def resolve_identity_companions(source: AssignmentSource) -> AssignmentSource:
    """Attach only deterministic, project-owned roster/decision companions.

    This does not search by student name.  It follows the existing config naming
    convention (for example pile1_test -> config/pile1_identity_decisions.json)
    and the project's canonical teacher roster.
    """

    if source.split_pile is None:
        return source
    roster = source.roster
    if roster is None and DEFAULT_ROSTER.is_file():
        roster = DEFAULT_ROSTER
    decisions = source.identity_decisions
    if decisions is None:
        candidate = managed_decision_path(source)
        if candidate.is_file():
            decisions = candidate
    return replace(source, roster=roster, identity_decisions=decisions)


def _key(class_name: str, student_id: str) -> str:
    return f"{class_name}\u241f{student_id}"


def _normalized_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").replace(" ", "").strip()


def _existing_decisions(source: AssignmentSource) -> list[dict]:
    path = source.identity_decisions
    if path is None or not path.is_file():
        return []
    value = read_json(path)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValidationError("Identity decision file must contain a list")
    return value


def prepare_identity_suggestions(source: AssignmentSource, matcher) -> None:
    """Guess a roster student for each submission once, before the teacher reviews."""

    source = resolve_identity_companions(source)
    if source.split_pile is None or source.roster is None or not source.roster.is_file():
        return
    submissions = read_existing_split(source.split_pile)
    ensure_suggestions(source.split_pile, submissions, read_roster(source.roster, source.roster_sheet, source.roster_class), matcher)


def build_identity_review(source: AssignmentSource, inspection: Inspection, language: str = "zh") -> dict:
    """Build compact QML data without changing any source or decision file."""

    source = resolve_identity_companions(source)
    total = len(inspection.submissions)
    confirmed_ids = {item.submission_id for item in inspection.submissions if item.identity_confirmed}
    # Once Stage 3B creates a production job, the inspection's submission_id
    # is the stable job key rather than ``submission:<source path>``. Preserve
    # the identity confirmation by joining on the already-persisted source-PDF
    # evidence as well, so a failed or resumable job does not reopen identity
    # confirmation without changing the unfinished-work action.
    confirmed_source_evidence = {
        evidence
        for item in inspection.submissions if item.identity_confirmed
        for evidence in item.evidence
    }
    used_keys = [_key(item.class_name, item.student_id) for item in inspection.submissions
                 if item.identity_confirmed and item.class_name and item.student_id]
    if source.split_pile is None or total == 0:
        return {"visible": False, "rows": [], "roster": [], "confirmedCount": 0, "totalCount": total}
    if source.roster is None or not source.roster.is_file():
        return {
            "visible": True,
            "requiresRoster": True,
            "rows": [],
            "roster": [],
            "confirmedCount": 0,
            "totalCount": total,
            "message": "Choose the class roster to continue." if language == "en" else "请选择班级学生名册后继续。",
        }

    submissions = read_existing_split(source.split_pile)
    roster = read_roster(source.roster, source.roster_sheet, source.roster_class)
    decisions = {item["source_pdf"]: item for item in _existing_decisions(source)}
    suggestions = read_suggestions(source.split_pile)
    roster_items = [
        {
            "key": _key(item.class_name, item.student_id),
            "className": item.class_name,
            "studentId": item.student_id,
            "studentName": item.student_name,
            "label": f"{item.class_name} · {item.student_id} · {item.student_name}",
        }
        for item in sorted(roster, key=lambda item: (item.class_name, int(item.student_id) if item.student_id.isdigit() else 10**9, item.student_id))
    ]
    by_exact_name: dict[str, list[dict]] = {}
    for item in roster_items:
        by_exact_name.setdefault(_normalized_name(item["studentName"]), []).append(item)

    rows = []
    confirmed = 0
    skipped = 0
    pile = source.split_pile.resolve()
    for submission in submissions:
        if (decisions.get(submission.source_pdf) or {}).get("match_status") == "SKIPPED":
            skipped += 1
            continue
        pdf = (pile / submission.source_pdf).resolve()
        submission_id = f"submission:{pdf}"
        is_confirmed = submission_id in confirmed_ids or str(pdf) in confirmed_source_evidence
        if is_confirmed:
            confirmed += 1
            continue
        # A teacher decision wins; otherwise pre-select the model's guess.
        guess = decisions.get(submission.source_pdf) or suggestions.get(submission.source_pdf) or {}
        selected = ""
        if guess.get("class_name") is not None and guess.get("student_id") is not None:
            selected = _key(str(guess["class_name"]), str(guess["student_id"]))
        if not selected:
            candidates = by_exact_name.get(_normalized_name(pdf.stem), [])
            if len(candidates) == 1:
                selected = candidates[0]["key"]
        preview = header_preview_path(pile, submission)
        if not preview.is_file():
            # Older split folders only; new splits no longer save name previews.
            preview = (pile / "_name_previews"/ submission.name_preview).resolve() if submission.name_preview else None
        rows.append({
            "submissionId": submission_id,
            "sourcePdf": submission.source_pdf,
            "ordinal": f"{submission.sequence:03}",
            "label": (f"Submission {submission.sequence:03}" if language == "en" else f"作文 {submission.sequence:03}"),
            "sourceHint": pdf.stem,
            "selectedKey": selected,
            "previewUrl": preview.as_uri() if preview and preview.is_file() else "",
            "pages": submission.pages,
        })

    return {
        "visible": bool(rows),
        "requiresRoster": False,
        "rows": rows,
        "roster": roster_items,
        "usedKeys": used_keys,
        "confirmedCount": confirmed,
        "totalCount": len(submissions) - skipped,
        "skippedCount": skipped,
        "remainingCount": len(rows),
        "skipOption": {
            "key": SKIP_KEY,
            "label": ("Skip this essay (saved as its own PDF to open as a new task)" if language == "en"
                      else "跳过这份作文（另存为单独 PDF，可作为新任务打开）"),
        },
        "message": ("Confirm the student for each remaining submission." if language == "en"
                    else "请确认每份作文对应的学生。"),
    }


def save_identity_confirmations(source: AssignmentSource, selections: list[dict]) -> tuple[AssignmentSource, int]:
    """Persist reviewed selections atomically, using the production intake validators."""

    source = resolve_identity_companions(source)
    if source.split_pile is None or source.roster is None:
        raise ValidationError("Composition folder and class roster are required")
    submissions = read_existing_split(source.split_pile)
    roster = read_roster(source.roster, source.roster_sheet, source.roster_class)
    by_submission = {item.source_pdf: item for item in submissions}
    target = managed_decision_path(source)
    existing = {item["source_pdf"]: dict(item) for item in _existing_decisions(source)}

    seen_selection_files = set()
    for selection in selections:
        source_pdf = str(selection.get("sourcePdf") or "")
        if source_pdf in seen_selection_files or source_pdf not in by_submission:
            raise ValidationError("Identity confirmation refers to a duplicate or unknown submission")
        seen_selection_files.add(source_pdf)
        if selection.get("skip") is True:
            # Keep a visible copy beside the scan; the split file itself stays
            # in the app's working folder, untouched.
            copy = skipped_copy_path(source, by_submission[source_pdf])
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source.split_pile / source_pdf, copy)
            existing[source_pdf] = {
                "source_pdf": source_pdf,
                "match_status": "SKIPPED",
                "saved_copy": str(copy),
                "evidence": "Teacher skipped this essay in the desktop student-information workspace.",
                "human_confirmation": datetime.now(timezone.utc).isoformat(),
            }
            continue
        class_name = str(selection.get("className") or "")
        student_id = str(selection.get("studentId") or "")
        identity = confirm_identity(roster, class_name, student_id)
        existing[source_pdf] = {
            "source_pdf": source_pdf,
            "class_name": identity.class_name,
            "student_id": identity.student_id,
            "match_status": "STRONG_ROSTER_MATCH",
            "evidence": "Teacher confirmed in the desktop student-information workspace.",
            "human_confirmation": datetime.now(timezone.utc).isoformat(),
        }

    ordered = [existing[item.source_pdf] for item in submissions if item.source_pdf in existing]
    # This is the existing production validation seam.  Partial persistence is
    # allowed here; real-batch intake still calls it with require_complete=True.
    apply_identity_decisions(submissions, roster, ordered, require_complete=False)
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(target, ordered)
    return replace(source, roster=source.roster, identity_decisions=target), len(ordered)
