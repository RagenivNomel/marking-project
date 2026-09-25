"""Stage 1 inspection plus Stage 3B/3C execution adapters for Section 2 HCL essays.

Inspection remains a read-only projection over explicit evidence. RUN_MARKING
rechecks the assignment and delegates to the production batch pipeline.
RENDER_APPROVED rechecks teacher-approved Excel and delegates to the existing
deterministic renderer; it does not approve teacher feedback or rerun grading.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from openpyxl import load_workbook

from application.models import (
    Action, AssignmentSource, Attention, AvailableAction, Inspection, Stage,
    SubmissionState,
)
from excel.schema import AUDIT_HEADERS, AUDIT_SHEET, HEADERS, SHEET
from excel.workbook import ExcelStore, read_roster, roster_text
from grading.calibration_schema import CalibrationValidator
from grading.schemas import Identity, ROOT, ValidationError, Validator
from scanning.intake import apply_identity_decisions, read_existing_split
from workflow.state import State
from workflow.storage import atomic_json, batch_lock, lock_is_active, read_json
from .task_storage import legacy_output_paths, teacher_output_paths


WORKFLOW_ID = "sec2_hcl_composition_v1"
DISPLAY_NAME = "中二高华作文批改"
MARKING_PROFILE = "luna_xhigh"
STAGES = (
    Stage("prepare", "准备作文"), Stage("confirm", "确认学生作文"),
    Stage("mark", "独立 AI 批改"), Stage("validate", "验证批改结果"),
    Stage("write_excel", "写入审核工作簿"),
    Stage("teacher_review", "等待教师审核并保存 Excel", human_gate=True),
    Stage("refresh_review", "重新读取审核结果", execution_wired=True),
    Stage("render", "生成学生体检卡"), Stage("deliver", "查看反馈输出"),
)
_VALIDATED = {"VALIDATED", "REVIEWED", "APPROVED", "RENDERED", "COMPLETE"}
_IDENTIFIED = _VALIDATED | {"IDENTIFIED", "TRANSCRIBED", "GRADED"}


def _path(value, base=None):
    path = Path(value)
    return ((base / path) if base is not None and not path.is_absolute() else path).resolve()


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _retryable_model_call_failure(directory, checkpoint):
    """Recognize a failed model call with no durable response artifact.

    A prior calibration job may have consumed its bounded attempts without
    producing a response.  That is still recoverable, but recovery must start
    a new calibration-attempt lineage rather than silently reusing the old
    one.  The pipeline decides whether the new attempt can reuse the existing
    child or needs a fresh child namespace.
    """
    if (checkpoint.get("state") != "TRANSCRIBED"
            or (Path(directory) / "raw_model_response.json").exists()):
        return False
    try:
        report = read_json(Path(directory) / "validation_report.json")
    except (OSError, ValueError, TypeError):
        return False
    return report.get("status") == "MODEL_CALL_FAILED" and report.get("model_request_attempted") is True


def _retryable_interrupted_model_call(directory, checkpoint):
    """Recognize a child checkpoint interrupted after its first-call reservation."""
    if (checkpoint.get("state") != "TRANSCRIBED"
            or checkpoint.get("live_request_attempts") != 1):
        return False
    path = Path(directory)
    if any((path / name).exists()
           for name in ("raw_model_response.json", "parsed_result.json")):
        return False
    report_path = path / "validation_report.json"
    if not report_path.exists():
        return True
    try:
        report = read_json(report_path)
    except (OSError, ValueError, TypeError):
        return False
    return report.get("status") == "MODEL_CALL_FAILED" and report.get("model_request_attempted") is True


def _retryable_interrupted_bridge(directory, checkpoint, child):
    """Recognize a parent interrupted before its calibration child was durable."""
    if checkpoint.get("state") != "TRANSCRIBED":
        return False
    if any((Path(directory) / name).exists()
           for name in ("grading_result.json", "validated_result.json", "raw_model_response.json")):
        return False
    bridge_path = Path(directory) / "real_grading_bridge.json"
    if not bridge_path.is_file() or Path(child).exists():
        return False
    try:
        bridge = read_json(bridge_path)
    except (OSError, ValueError, TypeError):
        return False
    return bridge.get("status") == "IN_PROGRESS"


def _mark_recovery_available(entry, details):
    """Collapse internal failure evidence to one actionable essay issue."""
    entry.retryable = True
    entry.safe_mark = False
    entry.attention = [a for a in entry.attention
                       if a.code not in ("UNCERTAIN_ATTEMPT", "SAVED_FAILURE",
                                         "BRIDGE_EVIDENCE_MISSING")]
    if not any(a.code == "MARKING_RETRY_AVAILABLE" for a in entry.attention):
        entry.attention.append(Attention(
            "MARKING_RETRY_AVAILABLE", "warning",
            "The previous attempt did not finish. You can retry this essay.",
            details, entry.key,
        ))


def _safe_to_start_first_attempt(directory, checkpoint):
    if (checkpoint.get("state") != "TRANSCRIBED"
            or checkpoint.get("live_request_attempts") != 0
            or (Path(directory) / "raw_model_response.json").exists()):
        return False
    report_path = Path(directory) / "validation_report.json"
    if not report_path.exists():
        return True
    try:
        report = read_json(report_path)
    except (OSError, ValueError, TypeError):
        return False
    return report.get("model_request_attempted") is False and report.get("status") == "PREFLIGHT_BLOCKED"


def _retryable_workbook_persistence(directory, checkpoint):
    """Recognize only this job's explicit unfinished workbook-write evidence."""
    if checkpoint.get("state") != "VALIDATED":
        return False
    try:
        marker = read_json(Path(directory) / "workbook_persistence.json")
        expected_workbook = _path(checkpoint.get("workbook"))
        return (
            marker.get("schema_version") == 1
            and marker.get("job_id") == checkpoint.get("job_id")
            and marker.get("identity") == checkpoint.get("identity")
            and marker.get("input_digest") == checkpoint.get("input_digest")
            and isinstance(marker.get("input_digest"), str)
            and bool(marker.get("input_digest"))
            and _path(marker.get("workbook")) == expected_workbook
            and marker.get("status") in ("PENDING", "FAILED")
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


@dataclass
class _Entry:
    """Transient workflow-specific evidence; never serialized as source of truth."""
    key: str
    identity: Identity | None = None
    confirmed: bool = False
    grading: bool = False
    record: object = None
    audit: dict | None = None
    state: str | None = None
    rendered: bool = False
    safe_mark: bool = False
    retryable: bool = False
    evidence: list = field(default_factory=list)
    attention: list = field(default_factory=list)
    source_paths: set = field(default_factory=set)

    def issue(self, code, message, details="", severity="error"):
        self.attention.append(Attention(code, severity, message, str(details), self.key))


class CompositionWorkflow:
    workflow_id = WORKFLOW_ID
    display_name = DISPLAY_NAME
    stages = STAGES

    def __init__(self, project_dir=ROOT, pipeline_factory=None, render_pipeline_factory=None):
        self.project_dir = Path(project_dir).resolve()
        self.pipeline_factory = pipeline_factory
        self.render_pipeline_factory = render_pipeline_factory

    @staticmethod
    def marking_batch_id(source: AssignmentSource) -> str:
        if source.split_pile is None:
            raise ValueError("A prepared composition folder is required")
        stable_path = str(_path(source.split_pile)).casefold()
        return "teacher_" + sha256(stable_path.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _requires_result_workbook(jobs: Path) -> bool:
        """A saved grading result must not become a fresh task if Excel is lost."""
        if not jobs.is_dir():
            return False
        try:
            for directory in jobs.iterdir():
                if not directory.is_dir():
                    continue
                if any((directory / name).exists() for name in ("grading_result.json", "validated_result.json")):
                    return True
                checkpoint_path = directory / "student_record.json"
                if checkpoint_path.is_file():
                    try:
                        state = read_json(checkpoint_path).get("state")
                    except Exception:
                        return True
                    if state == "GRADED" or state in _VALIDATED:
                        return True
        except OSError:
            return True
        return False

    def marking_source(self, source: AssignmentSource) -> AssignmentSource:
        """Resolve this task's workbook without asking the teacher for an output path."""
        if source.split_pile is None:
            return source
        batch = self.marking_batch_id(source)
        jobs = (self.project_dir / "jobs" / batch).resolve()
        current_paths = teacher_output_paths(source.split_pile)
        legacy_paths = legacy_output_paths(self.project_dir, batch)
        workbook_candidates = (current_paths.workbook, legacy_paths.workbook)
        attached_jobs = source.job_roots
        requires_workbook = self._requires_result_workbook(jobs)
        if not attached_jobs and jobs.is_dir():
            attached_jobs = (jobs,)
        saved_bindings = set()
        if jobs.is_dir():
            try:
                for directory in jobs.iterdir():
                    checkpoint_path = directory / "student_record.json"
                    if not directory.is_dir() or not checkpoint_path.is_file():
                        continue
                    try:
                        saved = read_json(checkpoint_path).get("workbook")
                    except Exception:
                        continue
                    if isinstance(saved, str) and saved.strip():
                        saved_bindings.add(_path(saved, directory))
            except OSError:
                pass

        existing = [path.resolve() for path in workbook_candidates if path.is_file()]
        conflict = len(existing) > 1
        requested = _path(source.workbook) if source.workbook is not None else None
        attached_workbook = requested
        if requested is None and source.job_roots:
            # Explicit recovery roots remain an import workflow. Do not mix
            # them with this project's automatically managed task workbook.
            attached_workbook = None
        elif requested is None or requested in workbook_candidates:
            if conflict:
                attached_workbook = current_paths.workbook
            elif current_paths.workbook.is_file():
                attached_workbook = current_paths.workbook
            elif legacy_paths.workbook.is_file():
                attached_workbook = legacy_paths.workbook
            else:
                saved = [path for path in saved_bindings if path in workbook_candidates]
                if len(saved) == 1 and requires_workbook:
                    attached_workbook = saved[0]
                elif requires_workbook:
                    # If a previous job exists but the workbook is missing,
                    # keep a deterministic missing-file reference for review.
                    attached_workbook = legacy_paths.workbook if legacy_paths.workbook in saved_bindings else current_paths.workbook
                else:
                    attached_workbook = None

        results_directory = (attached_workbook.parent if attached_workbook in workbook_candidates
                             else current_paths.results_directory)
        feedback_directory = results_directory / "Feedback Cards"
        return replace(
            source,
            workbook=attached_workbook,
            job_roots=attached_jobs,
            results_directory=results_directory,
            feedback_cards_directory=feedback_directory,
            output_location_conflict=conflict,
        )

    def inspect(self, source: AssignmentSource) -> Inspection:
        source = self.marking_source(source)
        if source.split_pile is not None and source.workbook is not None:
            batch = self.marking_batch_id(source)
            allowed = {
                teacher_output_paths(source.split_pile).workbook.resolve(),
                legacy_output_paths(self.project_dir, batch).workbook.resolve(),
            }
            if _path(source.workbook) not in allowed:
                return self._finish({}, [Attention(
                    "SOURCE_ASSOCIATION_MISMATCH", "error",
                    "所选工作簿与作文资料不属于同一任务，请分别读取。",
                    f"Selected workbook: {_path(source.workbook)}; expected for this assignment: {sorted(map(str, allowed))}",
                )], False)
        entries, issues = {}, []
        if source.output_location_conflict:
            issues.append(Attention(
                "WORKBOOK_LOCATION_CONFLICT", "error",
                "这项任务找到两个批改结果工作簿，暂时无法安全确定审核文件。",
                "Both the current Results/results.xlsx and the historical output/<batch>/results.xlsx exist.",
            ))
        try:
            validator = Validator(source.config_dir or ROOT / "config")
        except Exception as exc:
            return self._finish({}, [Attention("CONFIG_INVALID", "error", "批改配置暂时无法读取。", str(exc))], False)
        workbook = _path(source.workbook) if source.workbook is not None else None
        before = None
        if workbook is not None:
            try:
                before = _hash(workbook)
                self._workbook(workbook, validator, entries, issues)
            except Exception as exc:
                issues.append(Attention("WORKBOOK_UNREADABLE", "error", "无法读取审核工作簿，请检查文件是否可用。", str(exc)))
        self._jobs(source, workbook, validator, entries, issues)
        self._intake(source, entries, issues)
        self._cards(source, workbook, entries, issues)
        if before is not None:
            try:
                unchanged = before == _hash(workbook)
            except OSError:
                unchanged = False
            if not unchanged:
                issues.append(Attention("WORKBOOK_CHANGED", "error", "审核文件在读取期间发生变化，请保存后重新读取。"))
                for entry in entries.values():
                    entry.record = None
                    entry.rendered = False
        # Suppress actions when assignment-wide evidence is incomplete or ambiguous.
        return self._finish(entries, issues, workbook is not None)

    @staticmethod
    def _workbook(path, validator, entries, issues):
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            if (SHEET not in book.sheetnames or AUDIT_SHEET not in book.sheetnames
                    or [c.value for c in book[SHEET][1]] != HEADERS
                    or [c.value for c in book[AUDIT_SHEET][1]] != AUDIT_HEADERS):
                raise ValueError("Unexpected workflow workbook schema")
            rows = {row[0].row: row for row in book[SHEET].iter_rows(min_row=2)
                    if any(c.value is not None for c in row)}
            audits = [row for row in book[AUDIT_SHEET].iter_rows(min_row=2)
                      if any(c.value is not None for c in row)]
            job_counts = Counter(str(row[0].value) for row in audits)
            row_counts = Counter(str(row[3].value) for row in audits)
            by_row = defaultdict(list)
            for audit in audits:
                number = audit[3].value
                if type(number) is not int or number not in rows:
                    issues.append(Attention("AUDIT_ROW_INVALID", "error", "工作簿的审核记录与作文行不一致。", f"Audit row {audit[0].row}: invalid result row {number!r}"))
                else:
                    by_row[number].append(audit)
            store = ExcelStore(path, validator)
            for number, row in rows.items():
                candidates = by_row[number]
                audit = candidates[0] if len(candidates) == 1 else None
                job = audit[0].value if audit else None
                valid_job = isinstance(job, str) and bool(job.strip()) and job_counts[job] == 1
                key = job if valid_job else f"excel-row:{number}"
                entry = entries[key] = _Entry(key, evidence=[str(path) + f"#row={number}"])
                try:
                    entry.identity = Identity.from_dict(dict(zip(
                        ("class_name", "student_id", "student_name"),
                        (roster_text(c.value) for c in row[:3]),
                    )))
                    if audit is None or not valid_job or row_counts[str(number)] != 1:
                        raise ValueError("Missing or duplicate audit job/row mapping")
                    if any(c.data_type == "f" for c in audit):
                        raise ValueError("Audit requires literal values, not formulas")
                    if (roster_text(audit[1].value), roster_text(audit[2].value)) != (entry.identity.class_name, entry.identity.student_id):
                        raise ValueError("Audit class/student does not match result row")
                    if not isinstance(audit[4].value, str) or not audit[4].value.strip():
                        raise ValueError("Audit input digest is missing")
                    record = store.get(job, entry.identity)
                    if record.review_status not in ("PENDING", "APPROVED"):
                        raise ValueError("Unknown approval status")
                    if record.review_status == "APPROVED":
                        record, metadata = store.get_render_source(job, entry.identity)
                    else:
                        metadata = dict(job_id=job, excel_row=number, input_digest=audit[4].value, pipeline_status=audit[5].value)
                    entry.record, entry.audit = record, metadata
                    entry.confirmed = entry.grading = True
                except Exception as exc:
                    entry.issue("WORKBOOK_ROW_INVALID", "这份作文的审核数据需要检查，原文没有被修改。", exc)
        finally:
            book.close()

    @staticmethod
    def _find(roots, filename, issues):
        paths = set()
        for root_value in roots:
            try:
                root = _path(root_value)
                if not root.is_dir():
                    raise FileNotFoundError(f"Declared artifact directory missing: {root}")
                paths.update(p.resolve() for p in root.rglob(filename))
            except Exception as exc:
                issues.append(Attention("ARTIFACT_ROOT_UNREADABLE", "error", "部分任务资料无法读取，请检查文件夹。", str(exc)))
        return sorted(paths)

    def _jobs(self, source, workbook, validator, entries, issues):
        paths = self._find(source.job_roots, "student_record.json", issues)
        jobs = {}
        for path in paths:
            try:
                checkpoint = read_json(path)
                if not isinstance(checkpoint, dict):
                    raise ValueError("Checkpoint must be an object")
                jobs[path.parent] = checkpoint
            except Exception as exc:
                key = f"job:{path.parent}"
                entry = entries.setdefault(key, _Entry(key, evidence=[str(path)]))
                entry.issue("CHECKPOINT_INVALID", "这份作文的保存记录无法读取。", exc)
        # A calibration job is evidence for its exact production parent, not another essay.
        children = {}
        missing_children = {}
        for directory in list(jobs):
            bridge = directory / "real_grading_bridge.json"
            if bridge.is_file():
                try:
                    data = read_json(bridge)
                    child = _path(data["calibration_job"], directory)
                    if not (child / "student_record.json").is_file():
                        missing_children[directory] = child
                    elif child not in jobs:
                        # The production calibration checkpoint lives beside the
                        # batch folder. Follow only the exact path recorded in
                        # this student's bridge artifact; do not search the repo.
                        child_checkpoint = read_json(child / "student_record.json")
                        if not isinstance(child_checkpoint, dict):
                            raise ValueError("Calibration checkpoint must be an object")
                        jobs[child] = child_checkpoint
                    if child in jobs:
                        if child in children:
                            raise ValueError("Calibration job has multiple production parents")
                        children[child] = directory
                except Exception as exc:
                    issues.append(Attention("BRIDGE_INVALID", "error", "批改记录的来源关联需要检查。", f"{bridge}: {exc}"))
        seen = set()
        startup_failures = []
        for directory, checkpoint in jobs.items():
            if directory in children:
                continue
            key = checkpoint.get("job_id", directory.name)
            if not isinstance(key, str) or not key.strip():
                key = f"job:{directory}"
            entry = entries.setdefault(key, _Entry(key))
            entry.evidence.append(str(directory / "student_record.json"))
            if key in seen:
                entry.issue("DUPLICATE_JOB", "多份保存记录使用了同一作文标识，需要核对。", key)
                entry.safe_mark = False
                continue
            seen.add(key)
            self._job(directory, checkpoint, entry, workbook, validator)
            if directory in missing_children:
                missing_child = missing_children[directory]
                if _retryable_interrupted_bridge(directory, checkpoint, missing_child):
                    _mark_recovery_available(
                        entry,
                        f"The marking run stopped before a durable calibration checkpoint was saved: {missing_child}",
                    )
                else:
                    entry.issue("BRIDGE_EVIDENCE_MISSING", "部分批改来源记录缺失，需要核对。", str(missing_child))
            for child, parent in children.items():
                if parent == directory:
                    child_cp = jobs[child]
                    entry.evidence.append(str(child / "student_record.json"))
                    if child_cp.get("identity") != checkpoint.get("identity"):
                        entry.issue("BRIDGE_IDENTITY_MISMATCH", "批改来源的学生信息不一致。", str(child))
                    if checkpoint.get("source_sha256") != child_cp.get("source_sha256"):
                        entry.issue("BRIDGE_SOURCE_MISMATCH", "批改来源的作文内容标识不一致。", str(child))
                    if entry.state not in _VALIDATED and (
                            _retryable_model_call_failure(child, child_cp)
                            or _retryable_interrupted_model_call(child, child_cp)):
                        _mark_recovery_available(
                            entry,
                            f"No raw model response was saved in the calibration record: {child}",
                        )
                    elif entry.state not in _VALIDATED and _safe_to_start_first_attempt(child, child_cp):
                        entry.attention = [a for a in entry.attention
                                           if a.code not in ("UNCERTAIN_ATTEMPT", "SAVED_FAILURE")]
                        entry.safe_mark = (entry.confirmed and not entry.grading
                                           and not any(a.severity == "error" for a in entry.attention))
                        report_path = child / "validation_report.json"
                        if report_path.is_file():
                            report = read_json(report_path)
                            if report.get("status") == "PREFLIGHT_BLOCKED":
                                startup_failures.append((child, report.get("error")))
                    elif entry.state not in _VALIDATED and (child_cp.get("live_request_attempts", 0) or child_cp.get("state") == "GRADED"):
                        entry.issue("UNCERTAIN_ATTEMPT", "这份作文已有批改尝试，请先检查记录，不要直接重试。", str(child))
                        entry.safe_mark = False
        if startup_failures:
            child, error = startup_failures[0]
            issues.append(Attention(
                "MARKING_STARTUP_FAILED", "warning",
                "批改未能开始，作文仍已准备好。请查看详情或重试。",
                f"{len(startup_failures)} pre-model startup failure(s); first report: "
                f"{child / 'validation_report.json'}; error: {error}",
            ))
        for root in source.job_roots:
            lock = _path(root) / ".pipeline.lock"
            if lock_is_active(lock):
                issues.append(Attention("BATCH_LOCKED", "error", "任务可能仍在运行，请先检查，不要直接重试。", str(lock)))
        orphan_dirs = set()
        for filename in ("validated_result.json", "parsed_result.json", "grading_result.json", "raw_model_response.json", "source.pdf"):
            for artifact in self._find(source.job_roots, filename, issues):
                if artifact.parent in jobs:
                    continue
                key = artifact.parent.name if artifact.parent.name in entries else f"job:{artifact.parent}"
                entry = entries.setdefault(key, _Entry(key))
                entry.evidence.append(str(artifact))
                if artifact.parent not in orphan_dirs:
                    entry.issue("CHECKPOINT_MISSING", "已找到作文或批改资料，但缺少可核对的任务记录。", str(artifact.parent))
                    orphan_dirs.add(artifact.parent)

    @staticmethod
    def _job(directory, checkpoint, entry, workbook, validator):
        try:
            identity = Identity.from_dict(checkpoint["identity"])
            if entry.identity is not None and entry.identity != identity:
                raise ValueError("Checkpoint identity differs from workbook identity")
            entry.identity = identity
            state = State(checkpoint["state"]).value
            entry.state = state
            if workbook is not None and checkpoint.get("workbook") and _path(checkpoint["workbook"], directory) != workbook:
                raise ValueError("Checkpoint workbook path differs from selected workbook")
            if entry.audit and checkpoint.get("input_digest") != entry.audit["input_digest"]:
                raise ValueError("Checkpoint digest differs from Excel audit digest")
            entry.confirmed = entry.confirmed or state in _IDENTIFIED
            source_meta = directory / "source.json"
            if source_meta.is_file():
                data = read_json(source_meta)
                original = data.get("source_original_path")
                if original:
                    entry.source_paths.add(_path(original, directory))
            if checkpoint.get("source_original_path"):
                entry.source_paths.add(_path(checkpoint["source_original_path"], directory))
            pdf = directory / "source.pdf"
            if pdf.is_file():
                entry.source_paths.add(pdf.resolve())
                entry.evidence.append(str(pdf))
                if checkpoint.get("source_sha256") and _hash(pdf) != checkpoint["source_sha256"]:
                    raise ValueError("Saved PDF hash differs from checkpoint")
            # The persisted validated artifact is checked even when Excel is now edited.
            found_valid = False
            for filename in ("validated_result.json", "parsed_result.json", "grading_result.json"):
                artifact = directory / filename
                if not artifact.is_file():
                    continue
                entry.evidence.append(str(artifact))
                try:
                    value = read_json(artifact)
                    if filename == "parsed_result.json":
                        count = checkpoint.get("source_page_count", checkpoint.get("page_count"))
                        if type(count) is not int or count <= 0:
                            raise ValueError("Calibration page count missing from checkpoint")
                        response = CalibrationValidator(validator.limits, count).validate(value, identity)
                        value = response.to_dict()["grading"]
                    validator.validate(value, identity)
                    found_valid = True
                except Exception as exc:
                    entry.issue("GRADING_ARTIFACT_INVALID", "保存的批改结果需要检查。", f"{artifact}: {exc}")
            entry.grading = entry.grading or found_valid
            if state in _VALIDATED and not found_valid:
                entry.issue("GRADING_ARTIFACT_MISSING", "记录显示批改已完成，但保存的批改结果缺失。", str(directory))
            if state in _VALIDATED and entry.record is None:
                if (state == "VALIDATED" and found_valid
                        and _retryable_workbook_persistence(directory, checkpoint)):
                    entry.retryable = True
                    entry.issue(
                        "WORKBOOK_PERSISTENCE_RETRY_AVAILABLE",
                        "A validated result is ready to be saved. Retry will save it without grading the essay again.",
                        str(directory / "workbook_persistence.json"), severity="warning",
                    )
                else:
                    entry.issue("WORKBOOK_RESULT_MISSING", "批改结果已保存，但尚未找到有效的审核工作簿行。", str(directory))
            attempts = checkpoint.get("live_request_attempts", 0)
            if type(attempts) is not int or attempts < 0:
                raise ValueError("Invalid live_request_attempts counter")
            if state not in _VALIDATED and (attempts or state == "GRADED" or (directory / "raw_model_response.json").exists()):
                entry.issue("UNCERTAIN_ATTEMPT", "这份作文的批改尝试需要核对，请勿直接重新批改。", f"state={state}; attempts={attempts}; uncertain saved attempt")
            if checkpoint.get("last_error"):
                entry.issue("SAVED_FAILURE", "这份作文上次处理未完成，请查看原因。", checkpoint["last_error"])
            entry.safe_mark = (entry.confirmed and not entry.grading and state in {"IDENTIFIED", "TRANSCRIBED"}
                               and pdf.is_file() and not entry.attention and attempts == 0)
        except Exception as exc:
            entry.issue("CHECKPOINT_INCONSISTENT", "这份作文的保存记录与现有资料不一致。", exc)
            entry.safe_mark = False

    @staticmethod
    def _intake(source, entries, issues):
        if source.split_pile is None:
            if source.roster is not None or source.identity_decisions is not None:
                issues.append(Attention("INTAKE_SOURCE_MISSING", "error", "请同时指定作文资料文件夹。"))
            return
        try:
            pile = _path(source.split_pile)
            submissions = read_existing_split(pile)
        except Exception as exc:
            issues.append(Attention("INTAKE_INVALID", "error", "作文资料不完整或页序需要检查。", str(exc)))
            return
        decisions = {}
        if source.roster is not None and source.identity_decisions is not None:
            try:
                records = apply_identity_decisions(
                    submissions,
                    read_roster(source.roster, source.roster_sheet),
                    read_json(source.identity_decisions),
                    require_complete=False,
                )
                decisions = {r["source_pdf"]: r for r in records}
            except Exception as exc:
                issues.append(Attention("IDENTITY_DECISIONS_INVALID", "error", "学生确认记录需要检查。", str(exc)))
        for submission in submissions:
            pdf = (pile / submission.source_pdf).resolve()
            matches = [e for e in entries.values() if pdf in e.source_paths]
            if len(matches) == 1:
                entry = matches[0]
            else:
                key = f"submission:{pdf}"
                entry = entries.setdefault(key, _Entry(key))
                if matches:
                    entry.issue("SOURCE_ASSOCIATION_AMBIGUOUS", "作文来源对应多份保存记录，需要核对。", str(pdf))
            entry.evidence.append(str(pdf))
            entry.source_paths.add(pdf)
            record = decisions.get(submission.source_pdf)
            if record:
                identity = Identity.from_dict({k: record[k] for k in ("class_name", "student_id", "student_name")})
                if entry.identity is not None and identity != entry.identity:
                    entry.issue("IDENTITY_MISMATCH", "学生确认信息与保存记录不一致。", str(pdf))
                elif record["match_status"] == "STRONG_ROSTER_MATCH":
                    entry.identity, entry.confirmed = identity, True
                    if entry.state is None and not entry.grading and not entry.attention:
                        # A workbook-only row cannot be linked by student identity alone.
                        same_student = [e for e in entries.values() if e is not entry and e.identity == identity]
                        if same_student:
                            entry.issue("SUBMISSION_LINK_REQUIRED", "已有同一学生的结果，请先核对是否为同一份作文。", str(pdf))
                        else:
                            entry.safe_mark = True
                else:
                    entry.identity = identity
                    entry.confirmed = entry.safe_mark = False
                    entry.issue("IDENTITY_UNRESOLVED", "请确认这份作文对应的学生。", str(pdf), "warning")
            elif not entry.confirmed:
                entry.issue("IDENTITY_UNRESOLVED", "请确认这份作文对应的学生。", str(pdf), "warning")

    def _cards(self, source, workbook, entries, issues):
        from .card_evidence import inspect_card
        from .feedback_rendering import feedback_card_filename
        roots = tuple(dict.fromkeys((*source.receipt_roots, *source.job_roots)))
        paths = self._find(roots, "render_receipt.json", issues)
        found_for = set()
        for path in paths:
            try:
                receipt = read_json(path)
                key = receipt["source"]["job_id"]
                entry = entries.get(key)
                if entry is None:
                    # A directory name can localize an error, never establish provenance.
                    folder_key = path.parent.parent.name if path.parent.name == "output" else path.parent.name
                    candidate = entries.get(folder_key)
                    if candidate:
                        candidate.issue("RECEIPT_JOB_MISMATCH", "体检卡生成记录的作文标识不一致。", f"Receipt job mismatch: {path}: {key}")
                    else:
                        issues.append(Attention("RECEIPT_UNRESOLVED", "error", "部分体检卡无法对应到已确认的审核记录。", f"Receipt audit job mismatch: {path}: {key}"))
                    continue
                found_for.add(entry.key)
                entry.evidence.append(str(path))
                if entry.record is None or entry.record.review_status != "APPROVED" or workbook is None:
                    entry.issue("CARD_SOURCE_UNAPPROVED", "已有体检卡，但当前审核数据尚未确认有效。", str(path))
                    continue
                expected_teacher_output = None
                if source.split_pile is not None and workbook == teacher_output_paths(source.split_pile).workbook.resolve():
                    public_dir = teacher_output_paths(source.split_pile).feedback_cards_directory
                    expected_teacher_output = public_dir / feedback_card_filename(entry.record)
                okay, code, detail = inspect_card(
                    path, workbook, entry.key, entry.audit["excel_row"],
                    entry.audit["input_digest"], entry.record.to_dict(),
                    expected_teacher_output=expected_teacher_output,
                )
                if okay:
                    entry.rendered = True
                else:
                    entry.issue(code, "体检卡与当前审核资料不一致或文件缺失，请检查。", f"{path}: {detail}")
            except Exception as exc:
                issues.append(Attention("RECEIPT_INVALID", "error", "部分体检卡的生成记录无法读取。", f"{path}: {exc}"))
        pngs = set(self._find(roots, "student_card.png", issues))
        pngs.update(self._find(roots, "*-作文体检卡.png", issues))
        for png in sorted(pngs):
            if (png.parent / "render_receipt.json").is_file():
                continue
            key = png.parent.parent.name if png.parent.name == "output" else png.parent.name
            entry = entries.get(key)
            if entry:
                entry.issue("RECEIPT_MISSING", "已找到体检卡，但缺少对应生成记录。", str(png))
            else:
                issues.append(Attention("ORPHAN_CARD", "warning", "部分图片缺少可核对的生成记录。", str(png)))
        for entry in entries.values():
            # Conflicting receipts need an explicit choice; don't advertise a mixed result.
            if any(a.code.startswith(("CARD_", "RECEIPT_")) for a in entry.attention):
                entry.rendered = False
            if entry.state in {"RENDERED", "COMPLETE"} and entry.key not in found_for:
                entry.issue("RECEIPT_MISSING", "记录显示体检卡已生成，但未找到可核对的生成记录。", "Provide the associated receipt_roots; no matching receipt was found")

    @staticmethod
    def _finish(entries, issues, has_workbook):
        issues = list(dict.fromkeys(issues))
        global_error = any(a.severity == "error" for a in issues)
        submissions = []
        targets = defaultdict(list)
        for entry in entries.values():
            blocked = global_error or any(a.severity == "error" for a in entry.attention)
            review = entry.record.review_status if entry.record else None
            ready = bool(entry.record and review == "APPROVED" and not entry.rendered and not blocked)
            actions = []
            if not entry.confirmed:
                actions.append(Action.CONFIRM_SUBMISSIONS)
            if entry.safe_mark and not blocked:
                actions.append(Action.RUN_MARKING)
            elif entry.retryable and not blocked:
                actions.append(Action.RUN_MARKING)
            if review == "PENDING":
                actions.append(Action.REVIEW_EXCEL)
            if ready:
                actions.append(Action.RENDER_APPROVED)
            if entry.rendered:
                actions.append(Action.VIEW_OUTPUTS)
            if entry.attention:
                actions.append(Action.RESOLVE_ATTENTION)
            for action in actions:
                targets[action].append(entry.key)
            identity = entry.identity
            submissions.append(SubmissionState(
                submission_id=entry.key,
                student_name=identity.student_name if identity else None,
                class_name=identity.class_name if identity else None,
                student_id=identity.student_id if identity else None,
                identity_confirmed=entry.confirmed, grading_available=entry.grading,
                workbook_valid=entry.record is not None, review_status=review,
                rendered=entry.rendered, ready_to_render=ready, checkpoint_state=entry.state,
                evidence=tuple(dict.fromkeys(entry.evidence)), attention=tuple(entry.attention), next_actions=tuple(actions),
                retryable=entry.retryable,
            ))
        if has_workbook:
            targets[Action.REFRESH_REVIEW_STATUS] = [e.key for e in entries.values() if e.record is not None]
        if issues:
            targets.setdefault(Action.RESOLVE_ATTENTION, [])
        if not entries and not issues and not has_workbook:
            targets[Action.PREPARE_SUBMISSIONS] = []
        return Inspection(WORKFLOW_ID, DISPLAY_NAME, STAGES, tuple(submissions), tuple(issues), tuple(
            AvailableAction(action, tuple(targets[action]), action in (
                Action.REFRESH_REVIEW_STATUS, Action.RUN_MARKING, Action.RENDER_APPROVED
            ))
            for action in Action if action in targets
        ))

    def _feedback_source(self, source):
        """Bind rendering to this app's matching output/jobs batch only."""
        source = self.marking_source(source)
        if source.workbook is None:
            raise ValidationError("Read the approved results workbook before generating feedback")
        workbook = _path(source.workbook)
        if source.output_location_conflict:
            raise ValidationError("Two results workbooks exist for this task; resolve the workbook location before generating feedback")
        if source.split_pile is not None:
            batch_id = self.marking_batch_id(source)
            expected_workbook = ((source.results_directory or teacher_output_paths(source.split_pile).results_directory)
                                 / "results.xlsx").resolve()
            if workbook not in {
                expected_workbook,
                legacy_output_paths(self.project_dir, batch_id).workbook.resolve(),
            }:
                raise ValidationError("The selected workbook does not match this task's managed results location")
        else:
            output_root = (self.project_dir / "output").resolve()
            try:
                relative = workbook.relative_to(output_root)
            except ValueError as exc:
                raise ValidationError("Feedback output is limited to this project's own results workbook") from exc
            if len(relative.parts) != 2 or relative.parts[1].casefold() != "results.xlsx":
                raise ValidationError("The selected workbook is not in this project's task output folder")
            batch_id = relative.parts[0]
            expected_workbook = (output_root / batch_id / "results.xlsx").resolve()
        expected_jobs = (self.project_dir / "jobs" / batch_id).resolve()
        if workbook != expected_workbook:
            if source.split_pile is None or workbook != legacy_output_paths(self.project_dir, batch_id).workbook.resolve():
                raise ValidationError("The selected workbook does not match the task output location")
        if source.split_pile is not None and self.marking_batch_id(source) != batch_id:
            raise ValidationError("The selected workbook and submission folder belong to different tasks")
        feedback_dir = source.feedback_cards_directory
        if feedback_dir is None:
            feedback_dir = workbook.parent / "Feedback Cards"
        if expected_jobs.is_dir():
            # This task's deterministic Stage 3B job tree is the only receipt
            # root used for a Stage 3C write. Unrelated chosen roots cannot be
            # used to redirect card output.
            source = replace(source, workbook=workbook, job_roots=(expected_jobs,),
                             receipt_roots=(expected_jobs,),
                             results_directory=workbook.parent,
                             feedback_cards_directory=feedback_dir)
        else:
            source = replace(source, workbook=workbook, job_roots=(), receipt_roots=(),
                             results_directory=workbook.parent,
                             feedback_cards_directory=feedback_dir)
        return source, batch_id, expected_jobs

    def _feedback_pipeline(self, source, batch_id):
        if self.render_pipeline_factory is not None:
            return self.render_pipeline_factory(
                project_dir=self.project_dir, batch_id=batch_id, source=source
            )
        from .feedback_rendering import ApprovedFeedbackRenderer
        from rendering.renderer import PillowRenderer
        from workflow.pipeline import Pipeline

        publish_dir = source.feedback_cards_directory if source.split_pile is not None else None
        return Pipeline(
            project_dir=self.project_dir,
            batch_id=batch_id,
            config_dir=source.config_dir or ROOT / "config",
            renderer=ApprovedFeedbackRenderer(PillowRenderer(), publish_dir),
            allow_real=True,
            workbook_path=(source.workbook or
                           ((source.results_directory / "results.xlsx") if source.results_directory else None)),
        )

    def execute_feedback_generation(self, source: AssignmentSource, *, progress_callback=None):
        """Render only fresh, approved Excel rows through the proven renderer."""
        source, batch_id, jobs_root = self._feedback_source(source)
        preliminary = self.inspect(source)
        if preliminary.summary["blocking_errors"]:
            raise ValidationError("Resolve the task evidence warnings before generating feedback")
        preliminary_action = next((item for item in preliminary.available_actions
                                   if item.action == Action.RENDER_APPROVED), None)
        if preliminary_action is None or not preliminary_action.submission_ids:
            raise ValidationError("There are no approved essays ready for feedback generation")

        # Serialize app-level batches, then re-inspect while holding the lock.
        # A second window that acted on stale readiness cannot overwrite a card.
        with batch_lock(jobs_root / ".stage3c-render.lock"):
            source = replace(source, job_roots=(jobs_root,), receipt_roots=(jobs_root,))
            return self._execute_feedback_generation_locked(
                source, batch_id, jobs_root, progress_callback=progress_callback
            )

    def _execute_feedback_generation_locked(self, source, batch_id, jobs_root, *, progress_callback=None):
        from .feedback_rendering import feedback_card_filename_for_identity
        from workflow.pipeline import job_key

        inspection = self.inspect(source)
        if inspection.summary["blocking_errors"]:
            raise ValidationError("Resolve the task evidence warnings before generating feedback")
        action = next((item for item in inspection.available_actions
                       if item.action == Action.RENDER_APPROVED), None)
        if action is None or not action.submission_ids:
            raise ValidationError("There are no approved essays ready for feedback generation")
        by_id = {item.submission_id: item for item in inspection.submissions}
        targets = []
        for submission_id in action.submission_ids:
            item = by_id.get(submission_id)
            if (item is None or not item.ready_to_render or item.review_status != "APPROVED"
                    or not item.class_name or not item.student_id or not item.student_name):
                raise ValidationError("An eligible approved Excel row no longer matches the task")
            identity = Identity.from_dict({
                "class_name": item.class_name,
                "student_id": item.student_id,
                "student_name": item.student_name,
            })
            targets.append((submission_id, identity))

        names = [feedback_card_filename_for_identity(identity)
                 for _submission_id, identity in targets]
        if len(names) != len(set(names)):
            raise ValidationError("Two approved submissions would use the same feedback-card filename")

        pipeline = self._feedback_pipeline(source, batch_id)
        completed_ids = set()
        successes, failures = [], []
        total = len(targets)

        def report(active=""):
            if progress_callback is None:
                return
            completed = len(completed_ids)
            progress_callback({
                "operation": "render",
                "total": total,
                "completed": completed,
                "active": 1 if active else 0,
                "waiting": max(0, total - completed - len(failures) - (1 if active else 0)),
                "attention": len(failures),
                "current": active,
                "interrupted": False,
            })

        report()
        for submission_id, identity in targets:
            report(f"{identity.class_name} · {identity.student_id} · {identity.student_name}")
            job_dir = jobs_root / job_key(identity)
            output_dir = job_dir / "output"
            try:
                receipt_path = Path(pipeline.rerender(identity)).resolve()
                receipt = read_json(receipt_path)
                artifact = Path(receipt["output"]["artifact"]).resolve()
                expected_filename = feedback_card_filename_for_identity(identity)
                expected_output = (output_dir / expected_filename).resolve()
                if artifact != expected_output or not artifact.is_file():
                    raise ValidationError("The renderer did not save the expected student card")
                if source.split_pile is not None:
                    expected_teacher_output = ((source.feedback_cards_directory or
                                                (source.results_directory / "Feedback Cards")) / expected_filename).resolve()
                    teacher_output = receipt.get("teacher_output")
                    output_record = receipt.get("output") or {}
                    should_publish = (
                        not isinstance(teacher_output, dict)
                        or not isinstance(teacher_output.get("artifact"), str)
                        or _path(teacher_output.get("artifact")) != expected_teacher_output
                        or not expected_teacher_output.is_file()
                        or teacher_output.get("sha256") != output_record.get("sha256")
                        or _hash(expected_teacher_output) != output_record.get("sha256")
                    )
                    if should_publish:
                        from .feedback_rendering import publish_card_receipt
                        publish_card_receipt(receipt_path, expected_teacher_output.parent, expected_filename)
                        receipt = read_json(receipt_path)
                else:
                    expected_teacher_output = artifact

                if jobs_root.is_dir() and jobs_root not in source.job_roots:
                    source = replace(source, job_roots=(jobs_root,), receipt_roots=(jobs_root,))
                fresh = self.inspect(source)
                rendered = next((row for row in fresh.submissions
                                 if row.submission_id == submission_id and row.rendered), None)
                if rendered is None:
                    detail = next((f"{attention.code}: {attention.technical_details}"
                                   for row in fresh.submissions if row.submission_id == submission_id
                                   for attention in row.attention), "The saved card did not pass Stage 1 verification")
                    raise ValidationError(detail)
                completed_ids.add(submission_id)
                success = {"submission_id": submission_id, "identity": identity.to_dict(),
                           "path": str(expected_teacher_output), "receipt": str(receipt_path)}
                successes.append(success)
                try:
                    atomic_json(output_dir / "render_attempt.json", {
                        "status": "PASS", "identity": identity.to_dict(),
                        "workbook": str(source.workbook), "artifact": str(artifact),
                        "receipt": str(receipt_path),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as log_error:
                    # A verified receipt/PNG is the completion evidence; the
                    # optional attempt log cannot turn success into failure.
                    success["attempt_log_warning"] = str(log_error)
            except Exception as exc:
                failure = {
                    "submission_id": submission_id,
                    "identity": identity.to_dict(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "message": "This card could not be generated. The approved Excel result is unchanged; you can retry after checking the details.",
                }
                failures.append(failure)
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    atomic_json(output_dir / "render_attempt.json", {
                        "status": "FAILED", "identity": identity.to_dict(),
                        "workbook": str(source.workbook), "error_type": type(exc).__name__,
                        "error": str(exc), "failed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as log_error:
                    failure["error"] += f"; failure log could not be saved: {log_error}"
            report()

        return {"result": {
            "batch_id": batch_id,
            "requested": total,
            "generated": len(successes),
            "successes": successes,
            "failed": failures,
        }, "source": source}

    def execute_marking(self, source: AssignmentSource, *, progress_callback=None, retry_only=False,
                        cancelled=None):
        """Run the existing one-student production batch behind the app seam."""
        from grading.schemas import ValidationError
        from scanning.intake import apply_identity_decisions, read_existing_split
        if source.split_pile is None or source.roster is None or source.identity_decisions is None:
            raise ValidationError("Choose a prepared composition folder, roster and confirmed student identities first")

        source = self.marking_source(source)
        inspection = self.inspect(source)
        if inspection.summary["blocking_errors"]:
            raise ValidationError("The selected task has a blocking file or identity issue. Read the task details before marking")
        if not inspection.submissions or any(not item.identity_confirmed for item in inspection.submissions):
            raise ValidationError("Confirm the student for every submission before marking")

        batch_id = self.marking_batch_id(source)
        expected_jobs = (self.project_dir / "jobs" / batch_id).resolve()
        expected_workbook = ((source.results_directory or teacher_output_paths(source.split_pile).results_directory)
                             / "results.xlsx").resolve()
        if any(_path(root) != expected_jobs for root in source.job_roots):
            raise ValidationError("This assignment is linked to other saved marking records; read those records before starting a new run")
        if source.workbook is not None and _path(source.workbook) != expected_workbook:
            raise ValidationError("This assignment already names a different results workbook; the app will not replace it")
        execution_source = replace(source, workbook=expected_workbook, job_roots=(expected_jobs,))

        submissions = read_existing_split(source.split_pile)
        records = apply_identity_decisions(
            submissions,
            read_roster(source.roster, source.roster_sheet),
            read_json(source.identity_decisions),
            require_complete=True,
        )
        by_student = defaultdict(list)
        for item in inspection.submissions:
            if item.class_name and item.student_id:
                by_student[(item.class_name, item.student_id)].append(item)
        if any(len(items) != 1 for items in by_student.values()):
            raise ValidationError("Each student must be linked to only one submission before marking")

        retry_keys = set()
        if retry_only:
            retryable = [item for item in inspection.submissions if item.retryable]
            if not retryable:
                raise ValidationError("There is no submission with a safely retryable marking attempt")
            retry_keys = {item.submission_id for item in retryable}
            records = [record for record in records
                       if any(item.submission_id in retry_keys
                              for item in by_student.get((record["class_name"], record["student_id"]), []))]
        else:
            eligible = []
            for record in records:
                items = by_student.get((record["class_name"], record["student_id"]), [])
                if not items:
                    raise ValidationError("A confirmed submission is missing from the inspected task")
                item = items[0]
                if item.retryable:
                    # Normal Start never consumes a second model attempt.
                    continue
                if item.workbook_valid and item.review_status in ("PENDING", "APPROVED"):
                    eligible.append(record)
                elif Action.RUN_MARKING in item.next_actions:
                    eligible.append(record)
            records = eligible

        if self.pipeline_factory is None:
            from workflow.pipeline import Pipeline
            pipeline = Pipeline(
                self.project_dir, batch_id, config_dir=source.config_dir or (ROOT / "config"),
                allow_real=True, workbook_path=expected_workbook,
            )
        else:
            pipeline = self.pipeline_factory(
                self.project_dir, batch_id, source.config_dir or (ROOT / "config"),
                workbook_path=expected_workbook,
            )
        result = pipeline.run_real_batch(
            records,
            source.split_pile,
            essay_question=None,
            model_profile=MARKING_PROFILE,
            progress_callback=progress_callback,
            retry_student_ids=retry_keys,
            cancelled=cancelled,
        )
        # Bind the completed inspection to files that actually exist. A missing
        # workbook remains attached only when grading evidence requires it.
        return {"result": result, "source": self.marking_source(execution_source)}
