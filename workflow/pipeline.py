"""Restartable orchestration, shared by the CLI and future wrapper."""
from dataclasses import asdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Callable

from pypdf import PdfReader

from excel.workbook import ExcelStore, roster_text
from grading.grader import GradingInput
from grading.mock_grader import MockGrader
from grading.reviewer import MockReviewer
from grading.schemas import Identity, ROOT, Validator, ValidationError, exact_keys, required_text
from rendering.renderer import PillowRenderer
from scanning.identity import confirm_identity
from .state import State, transition
from .storage import atomic_json, batch_lock, exclusive_lock, read_json


MAX_CONCURRENT_GRADERS = 3


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def safe_batch_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) or value.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError("Batch ID must be a safe non-reserved name of 1-64 ASCII letters, digits, '_' or '-'")
    return value


def job_key(identity):
    number = re.sub(r"[^A-Za-z0-9]", "", identity.student_id)[:20] or "id"
    digest = fingerprint([identity.class_name, identity.student_id])[:12]
    return f"student_{number}_{digest}"


class Pipeline:
    """Serial writer per batch. Each batch owns one authoritative workbook.

    The injectable grader factory MUST return a fresh provider for each job.
    Python object boundaries are not an OS sandbox; a real model worker must
    add process/container access controls before production grading is enabled.
    """
    def __init__(self, project_dir=ROOT, batch_id="demo", *, config_dir=ROOT / "config",
                 grader_factory: Callable = MockGrader, reviewer=None, renderer=None,
                 real_pipeline_factory=None, allow_real=False, workbook_path=None):
        self.project_dir = Path(project_dir).resolve()
        self.config_dir = Path(config_dir).resolve()
        self.batch_id = safe_batch_id(batch_id)
        self.jobs_dir = self.project_dir / "jobs" / self.batch_id
        self.output_dir = (Path(workbook_path).resolve().parent if workbook_path is not None
                           else self.project_dir / "output" / self.batch_id)
        self.validator = Validator(self.config_dir)
        models = read_json(self.config_dir / "models.json")
        if not allow_real and (models.get("backend") != "mock" or models.get("real_ai_enabled") is not False):
            raise ValidationError("Phase 1 supports only the mock backend")
        self.excel = ExcelStore(
            Path(workbook_path).resolve() if workbook_path is not None else self.output_dir / "results.xlsx",
            self.validator,
            backup_dir=(self.jobs_dir / "workbook_backups" if workbook_path is not None else None),
        )
        self.grader_factory = grader_factory
        self.real_pipeline_factory = real_pipeline_factory
        self.reviewer = reviewer or MockReviewer()
        self.renderer = renderer or PillowRenderer()

    def _advance(self, job_dir, checkpoint, target):
        checkpoint["state"] = transition(State(checkpoint["state"]), target).value
        checkpoint["history"].append(target.value)
        checkpoint["last_error"] = None
        atomic_json(job_dir / "student_record.json", checkpoint)

    def run_mock(self, source: dict):
        if not isinstance(source, dict) or set(source) not in ({"identity", "essay"}, {"identity", "essay", "topic"}):
            raise ValidationError("mock student input: expected identity, essay and optional topic")
        identity = Identity.from_dict(source["identity"])
        required_text(source["essay"], "essay")
        topic = source.get("topic", "")
        if not isinstance(topic, str):
            raise ValidationError("topic: text required")
        key = job_key(identity)
        digest = fingerprint(source)
        job_dir = self.jobs_dir / key
        with batch_lock(self.jobs_dir / ".pipeline.lock"):
            job_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = job_dir / "student_record.json"
            if checkpoint_path.exists():
                checkpoint = read_json(checkpoint_path)
                if checkpoint["input_digest"] != digest or checkpoint["workbook"] != str(self.excel.path) or checkpoint["identity"] != identity.to_dict():
                    raise ValidationError("Job input or workbook changed; use a new batch ID")
                history = checkpoint["history"]
                if history != [s.value for s in State][:len(history)] or not history or history[-1] != checkpoint["state"]:
                    raise ValidationError("Invalid checkpoint state history")
            else:
                checkpoint = dict(schema_version=1, mode="MOCK", job_id=key, identity=identity.to_dict(),
                                  input_digest=digest, workbook=str(self.excel.path), state=State.NEW.value,
                                  history=[State.NEW.value], last_error=None)
                atomic_json(checkpoint_path, checkpoint)
            try:
                while State(checkpoint["state"]) != State.COMPLETE:
                    state = State(checkpoint["state"])
                    if state == State.NEW:
                        # Mock scan only; real scan PDFs enter through scanning separately.
                        atomic_json(job_dir / "source.json", {"mode": "mock-scan", **source})
                        self._advance(job_dir, checkpoint, State.SCANNED)
                    elif state == State.SCANNED:
                        confirmed = confirm_identity([identity], identity.class_name, identity.student_id)
                        atomic_json(job_dir / "identity.json", {"method": "explicit-mock-input", **confirmed.to_dict()})
                        self._advance(job_dir, checkpoint, State.IDENTIFIED)
                    elif state == State.IDENTIFIED:
                        (job_dir / "essay.md").write_text(source["essay"], encoding="utf-8")
                        atomic_json(job_dir / "essay.json", {"text": source["essay"], "method": "mock-transcription"})
                        self._advance(job_dir, checkpoint, State.TRANSCRIBED)
                    elif state == State.TRANSCRIBED:
                        request = GradingInput(identity, source["essay"])
                        atomic_json(job_dir / "grading_input.json", asdict(request))
                        raw_path = job_dir / "grading_result.json"
                        if not raw_path.exists():
                            # The provider receives data only and is discarded after this call.
                            raw_result = self.grader_factory().grade(request)
                            atomic_json(raw_path, raw_result)
                        self._advance(job_dir, checkpoint, State.GRADED)
                    elif state == State.GRADED:
                        result = self.validator.validate(read_json(job_dir / "grading_result.json"), identity)
                        atomic_json(job_dir / "validated_result.json", result.to_dict())
                        self._advance(job_dir, checkpoint, State.VALIDATED)
                    elif state == State.VALIDATED:
                        result = self.validator.validate(read_json(job_dir / "validated_result.json"), identity)
                        self.excel.ensure_draft(result, identity, key, digest, topic)
                        # Review Excel values, including any edits made after an interruption.
                        current = self.excel.get(key, identity)
                        if not self.reviewer.review(current):
                            raise ValidationError("Review did not approve this record")
                        atomic_json(job_dir / "review.json", {"reviewer": "mock", "approved": True, "record_digest": fingerprint(current.to_dict())})
                        self.excel.set_status(key, identity, State.REVIEWED.value)
                        self._advance(job_dir, checkpoint, State.REVIEWED)
                    elif state == State.REVIEWED:
                        current = self.excel.get(key, identity)
                        review = read_json(job_dir / "review.json")
                        if review["record_digest"] != fingerprint(current.to_dict()):
                            # Teacher changed a draft after review; review the new exact text.
                            if not self.reviewer.review(current):
                                raise ValidationError("Changed Excel record requires review")
                            atomic_json(job_dir / "review.json", {"reviewer": "mock", "approved": True, "record_digest": fingerprint(current.to_dict())})
                        self.excel.set_status(key, identity, State.APPROVED.value, "APPROVED")
                        self._advance(job_dir, checkpoint, State.APPROVED)
                    elif state == State.APPROVED:
                        artifact = self._render(identity, key, job_dir)
                        checkpoint["render_artifact"] = str(artifact)
                        self.excel.set_status(key, identity, State.RENDERED.value)
                        self._advance(job_dir, checkpoint, State.RENDERED)
                    elif state == State.RENDERED:
                        self.excel.get(key, identity, approved=True)
                        if not self._render_artifact_exists(job_dir):
                            raise ValidationError("Render artifact missing; run rerender")
                        self.excel.set_status(key, identity, State.COMPLETE.value)
                        self._advance(job_dir, checkpoint, State.COMPLETE)
                return {"state": checkpoint["state"], "job_id": key, "job_dir": str(job_dir),
                        "workbook": str(self.excel.path), "render": checkpoint.get("render_artifact", str(job_dir / "output" / "mock_render.json"))}
            except Exception as exc:
                # Retain the last DURABLE state if a checkpoint write itself failed.
                durable = read_json(checkpoint_path)
                durable["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
                atomic_json(checkpoint_path, durable)
                raise

    def _render(self, identity, key, job_dir, checkpoint=None):
        record, excel_audit = self.excel.get_render_source(key, identity)
        if checkpoint is not None and checkpoint.get("input_digest") != excel_audit["input_digest"]:
            raise ValidationError("Checkpoint input digest does not match approved Excel audit")
        audit = {
            "workbook": str(self.excel.path.resolve()),
            "excel_row": excel_audit["excel_row"],
            "job_id": excel_audit["job_id"],
            "input_digest": excel_audit["input_digest"],
            "pipeline_status": excel_audit["pipeline_status"],
            "source_of_truth": "approved_excel_row",
        }
        return self.renderer.render(record, job_dir / "output", audit)

    @staticmethod
    def _render_artifact_exists(job_dir):
        output_dir = job_dir / "output"
        receipt_path = output_dir / "render_receipt.json"
        if receipt_path.is_file():
            try:
                artifact = read_json(receipt_path).get("output", {}).get("artifact")
                if isinstance(artifact, str) and artifact.strip():
                    artifact_path = Path(artifact)
                    if not artifact_path.is_absolute():
                        artifact_path = output_dir / artifact_path
                    if artifact_path.is_file():
                        return True
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        return (output_dir / "mock_render.json").exists()

    def rerender(self, identity: Identity):
        """Read approved Excel values afresh; never consult cached feedback or grade.

        Existing checkpoints still protect normal restartable jobs. An imported
        production workbook may legitimately have no local checkpoint; its
        uniquely audited APPROVED Excel row then supplies the render source and
        audit identity directly.
        """
        key = job_key(identity)
        job_dir = self.jobs_dir / key
        with batch_lock(self.jobs_dir / ".pipeline.lock"):
            checkpoint_path = job_dir / "student_record.json"
            checkpoint = None
            if checkpoint_path.exists():
                checkpoint = read_json(checkpoint_path)
                if checkpoint["identity"] != identity.to_dict() or checkpoint["workbook"] != str(self.excel.path):
                    raise ValidationError("Checkpoint identity/workbook mismatch")
                if State(checkpoint["state"]) not in (
                    State.VALIDATED, State.APPROVED, State.RENDERED, State.COMPLETE
                ):
                    raise ValidationError("Job has not reached approval")
            job_dir.mkdir(parents=True, exist_ok=True)
            return self._render(identity, key, job_dir, checkpoint)

    def _calibration_namespace_for_attempt(self, key):
        """Give every unfinished prior attempt a fresh isolated child namespace."""
        bridge_path = self.jobs_dir / key / "real_grading_bridge.json"
        checkpoint_path = self.jobs_dir / key / "student_record.json"
        if not bridge_path.is_file():
            try:
                checkpoint = read_json(checkpoint_path)
                if checkpoint.get("state") not in {
                        State.GRADED.value, State.VALIDATED.value,
                        State.REVIEWED.value, State.APPROVED.value,
                        State.RENDERED.value, State.COMPLETE.value}:
                    return self.batch_id
            except (OSError, ValueError, TypeError, AttributeError):
                return self.batch_id
        try:
            lineage_path = self.jobs_dir / key / "real_grading_attempts.json"
            lineage = read_json(lineage_path) if lineage_path.is_file() else {}
            attempts = lineage.get("attempts", [])
            next_number = max((int(item.get("attempt", 0)) for item in attempts), default=1) + 1
        except (OSError, ValueError, TypeError, AttributeError):
            next_number = 2
        candidate_root = self.project_dir / "jobs"
        key_suffix = key.removeprefix("student_")
        while any(candidate_root.glob(
                f"calibration_{self.batch_id}_attempt_{next_number}_{key_suffix}_*")):
            next_number += 1
        return f"{self.batch_id}_attempt_{next_number}"

    def _record_calibration_attempt(self, job_dir, key, namespace):
        """Preserve prior calibration evidence before starting a fresh child."""
        lineage_path = Path(job_dir) / "real_grading_attempts.json"
        try:
            lineage = read_json(lineage_path) if lineage_path.is_file() else {}
        except (OSError, ValueError, TypeError):
            lineage = {}
        entries = list(lineage.get("attempts", [])) if isinstance(lineage, dict) else []
        if not entries:
            bridge_path = Path(job_dir) / "real_grading_bridge.json"
            if bridge_path.is_file():
                try:
                    bridge = read_json(bridge_path)
                    old_child = Path(bridge["calibration_job"])
                    old_checkpoint = read_json(old_child / "student_record.json")
                    report_path = old_child / "validation_report.json"
                    old_report = read_json(report_path) if report_path.is_file() else {}
                    entries.append({
                        "attempt": 1,
                        "calibration_job": str(old_child),
                        "execution_namespace": bridge.get("execution_namespace"),
                        "state": old_checkpoint.get("state"),
                        "live_request_attempts": old_checkpoint.get("live_request_attempts", 0),
                        "validation_status": old_report.get("status"),
                    })
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        number = max((int(item.get("attempt", 0)) for item in entries), default=0) + 1
        pending = {
            "attempt": number,
            "calibration_job": None,
            "execution_namespace": namespace,
            "state": "PENDING",
        }
        entries.append(pending)
        atomic_json(lineage_path, {"schema_version": 1, "job_id": key, "attempts": entries})
        return pending

    def _bind_calibration_attempt(self, job_dir, pending, calibration_job):
        lineage_path = Path(job_dir) / "real_grading_attempts.json"
        try:
            lineage = read_json(lineage_path)
            for entry in lineage.get("attempts", []):
                if entry.get("attempt") == pending.get("attempt"):
                    entry["calibration_job"] = str(calibration_job)
                    entry["state"] = "IN_PROGRESS"
                    break
            atomic_json(lineage_path, lineage)
        except (OSError, ValueError, TypeError, AttributeError):
            # The checkpoint and bridge remain authoritative if the optional
            # lineage index cannot be updated.
            return

    def _finish_calibration_attempt(self, job_dir, calibration_job, state):
        lineage_path = Path(job_dir) / "real_grading_attempts.json"
        try:
            lineage = read_json(lineage_path)
            for entry in lineage.get("attempts", []):
                if entry.get("calibration_job") == str(calibration_job):
                    entry["state"] = state
                    break
            atomic_json(lineage_path, lineage)
        except (OSError, ValueError, TypeError, AttributeError):
            return

    def run_real_pdf(self, source_pdf, identity: Identity, essay_question=None, model_profile=None,
                     *, allow_second_live_attempt=False, persist_workbook=True,
                     execution_namespace=None, fresh_attempt=False, timing_callback=None):
        """Bridge one isolated real-PDF grading job into the production workbook.

        The existing calibration pipeline remains responsible for Codex isolation,
        prompt/rubric snapshots, structured validation and its one-attempt guard.
        This method only binds its validated grading result to the batch workbook;
        real jobs stop at VALIDATED/PENDING and never auto-approve or render.
        """
        source_pdf = Path(source_pdf).resolve()
        if not source_pdf.is_file() or source_pdf.suffix.lower() != ".pdf":
            raise ValidationError("One existing PDF source is required")
        source_bytes = source_pdf.read_bytes()
        page_count = len(PdfReader(source_pdf).pages)
        if page_count < 1:
            raise ValidationError("Source PDF has no pages")
        model_catalog = read_json(self.config_dir / "calibration_model.json")
        profiles = model_catalog.get("profiles", {})
        profile = model_profile or model_catalog.get("active_profile")
        if profile not in profiles:
            raise ValidationError(f"Unknown calibration model profile: {profile}")
        digest = fingerprint({
            "identity": identity.to_dict(),
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "essay_question": essay_question,
            "model_profile": profile,
        })
        key = job_key(identity)
        job_dir = self.jobs_dir / key
        checkpoint_path = job_dir / "student_record.json"
        calibration_namespace = execution_namespace or self.batch_id
        # A distinct lock per student preserves restart safety without holding
        # sibling students behind another student's blocking model call.
        with batch_lock(self.jobs_dir / f".{key}.pipeline.lock"):
            job_dir.mkdir(parents=True, exist_ok=True)
            if checkpoint_path.exists():
                checkpoint = read_json(checkpoint_path)
                if (checkpoint.get("input_digest") != digest
                        or checkpoint.get("workbook") != str(self.excel.path)
                        or checkpoint.get("identity") != identity.to_dict()):
                    raise ValidationError("Existing real batch job belongs to different input or configuration")
            else:
                checkpoint = dict(
                    schema_version=2,
                    mode="REAL_PDF_BATCH",
                    job_id=key,
                    identity=identity.to_dict(),
                    input_digest=digest,
                    source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                    source_page_count=page_count,
                    model_profile=profile,
                    execution_namespace=self.batch_id,
                    workbook=str(self.excel.path),
                    state=State.NEW.value,
                    history=[State.NEW.value],
                    last_error=None,
                )
                atomic_json(checkpoint_path, checkpoint)
            try:
                state = State(checkpoint["state"])
                if fresh_attempt and state not in (State.NEW, State.SCANNED, State.IDENTIFIED, State.TRANSCRIBED):
                    # A prior model/validation attempt is disposable when no
                    # authoritative workbook row exists.  Reset only the
                    # parent activity cursor; the isolated child and optional
                    # attempt lineage remain available as audit evidence.
                    checkpoint["state"] = State.TRANSCRIBED.value
                    checkpoint["history"] = [
                        State.NEW.value, State.SCANNED.value,
                        State.IDENTIFIED.value, State.TRANSCRIBED.value,
                    ]
                    checkpoint["last_error"] = None
                    atomic_json(checkpoint_path, checkpoint)
                if state == State.NEW:
                    shutil.copyfile(source_pdf, job_dir / "source.pdf")
                    atomic_json(job_dir / "source.json", {
                        "mode": "real-pdf",
                        "source_original_path": str(source_pdf),
                        "source_sha256": checkpoint["source_sha256"],
                        "page_count": page_count,
                    })
                    self._advance(job_dir, checkpoint, State.SCANNED)
                if State(checkpoint["state"]) == State.SCANNED:
                    atomic_json(job_dir / "identity.json", {"method": "explicit-batch-input", **identity.to_dict()})
                    self._advance(job_dir, checkpoint, State.IDENTIFIED)
                if State(checkpoint["state"]) == State.IDENTIFIED:
                    atomic_json(job_dir / "essay.json", {
                        "method": "direct_pdf",
                        "page_count": page_count,
                        "essay_question": essay_question,
                    })
                    self._advance(job_dir, checkpoint, State.TRANSCRIBED)
                if State(checkpoint["state"]) == State.TRANSCRIBED:
                    if self.real_pipeline_factory is None:
                        from workflow.calibration_pipeline import CalibrationPipeline
                        real_pipeline = CalibrationPipeline(self.project_dir, config_dir=self.config_dir, model_profile=profile)
                    else:
                        real_pipeline = self.real_pipeline_factory(self.project_dir, model_profile=profile)
                    lineage_entry = None
                    if calibration_namespace != self.batch_id:
                        lineage_entry = self._record_calibration_attempt(
                            job_dir, key, calibration_namespace
                        )
                    # Persist the parent-to-calibration link before the external
                    # call so Stage 1 can inspect an interrupted/failed attempt.
                    calibration_job, _calibration_output, _calibration_checkpoint = real_pipeline.prepare(
                        source_pdf, identity, essay_question, execution_namespace=calibration_namespace
                    )
                    if lineage_entry is not None:
                        self._bind_calibration_attempt(job_dir, lineage_entry, calibration_job)
                    atomic_json(job_dir / "real_grading_bridge.json", {
                        "calibration_job": str(calibration_job),
                        "execution_namespace": self.batch_id,
                        "calibration_attempt_namespace": calibration_namespace,
                        "status": "IN_PROGRESS",
                    })
                    bridge_result = real_pipeline.run(
                        source_pdf, identity, essay_question,
                        allow_second_live_attempt=allow_second_live_attempt,
                        execution_namespace=calibration_namespace,
                        timing_callback=timing_callback,
                    )
                    if lineage_entry is not None:
                        self._finish_calibration_attempt(
                            job_dir,
                            bridge_result.get("job_dir", calibration_job),
                            bridge_result.get("state", "UNKNOWN"),
                        )
                    if bridge_result.get("state") not in (State.VALIDATED.value, State.GRADED.value):
                        raise ValidationError("Isolated real grader did not produce a validated grading result")
                    calibration_job = Path(bridge_result["job_dir"])
                    parsed_path = calibration_job / "parsed_result.json"
                    parsed = read_json(parsed_path)
                    if bridge_result.get("state") == State.GRADED.value or parsed.get("grading") is None:
                        atomic_json(job_dir / "reading_quality.json", parsed.get("reading_quality", {}))
                        atomic_json(job_dir / "real_grading_bridge.json", {
                            "calibration_job": str(calibration_job),
                            "execution_namespace": self.batch_id,
                            "calibration_attempt_namespace": calibration_namespace,
                            "status": "MATERIAL_READING_UNCERTAINTY",
                        })
                        return {"state": State.TRANSCRIBED.value, "job_id": key, "job_dir": str(job_dir), "workbook": None}
                    atomic_json(job_dir / "grading_result.json", parsed["grading"])
                    atomic_json(job_dir / "real_grading_bridge.json", {
                        "calibration_job": str(calibration_job),
                        "execution_namespace": self.batch_id,
                        "calibration_attempt_namespace": calibration_namespace,
                        "parsed_result": str(parsed_path),
                        "validation_report": str(calibration_job / "validation_report.json"),
                        "reading_quality": parsed.get("reading_quality", {}),
                        "evidence": parsed.get("evidence", []),
                        "question_number": parsed.get("question_number"),
                        "scores": parsed.get("scores"),
                    })
                    self._advance(job_dir, checkpoint, State.GRADED)
                if State(checkpoint["state"]) == State.GRADED:
                    result = self.validator.validate(read_json(job_dir / "grading_result.json"), identity)
                    atomic_json(job_dir / "validated_result.json", result.to_dict())
                    self._advance(job_dir, checkpoint, State.VALIDATED)
                if State(checkpoint["state"]) == State.VALIDATED:
                    result = self.validator.validate(read_json(job_dir / "validated_result.json"), identity)
                    if timing_callback is not None:
                        timing_callback("validation_finish")
                    outcome = {
                        "state": State.VALIDATED.value,
                        "job_id": key,
                        "job_dir": str(job_dir),
                        "workbook": str(self.excel.path),
                    }
                    if not persist_workbook:
                        return outcome
                    review_status = self._persist_real_result(result, identity, key, digest, essay_question or "")
                    outcome["review_status"] = review_status
                    if timing_callback is not None:
                        timing_callback("persistence_finish")
                    return outcome
                raise ValidationError(f"Real batch cannot continue from {checkpoint['state']}")
            except Exception as exc:
                durable = read_json(checkpoint_path)
                durable["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
                atomic_json(checkpoint_path, durable)
                raise

    def _persist_real_result(self, result, identity, key, digest, topic, *,
                             writer_started=None, writer_finished=None):
        """Use the authoritative ExcelStore merge path for one validated row."""
        attempt_path = self.jobs_dir / key / "workbook_persistence.json"
        attempt = {
            "schema_version": 1,
            "job_id": key,
            "identity": identity.to_dict(),
            "input_digest": digest,
            "workbook": str(self.excel.path.resolve()),
            "status": "PENDING",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        atomic_json(attempt_path, attempt)
        if writer_started is not None:
            writer_started()
        bridge_path = self.jobs_dir / key / "real_grading_bridge.json"
        bridge = read_json(bridge_path) if bridge_path.is_file() else {}
        try:
            self.excel.ensure_draft(result, identity, key, digest, topic or bridge.get("question_number") or "",
                                    teacher_scores=bridge.get("scores"))
            review_status = self.excel.get(key, identity).review_status
        except Exception as exc:
            attempt.update({
                "status": "FAILED",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                atomic_json(attempt_path, attempt)
            except Exception:
                # The receipt is diagnostic only; the workbook row and audit
                # are the authoritative commit evidence.
                pass
            raise
        finally:
            if writer_finished is not None:
                writer_finished()
        attempt.update({
            "status": "SAVED",
            "review_status": review_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        atomic_json(attempt_path, attempt)
        return review_status

    def run_real_batch(self, records, source_dir, *, limit=None, essay_question=None, model_profile=None,
                       progress_callback=None, cancelled=None):
        """Run one bounded batch; the OS lock prevents competing app windows."""
        with exclusive_lock(self.jobs_dir / ".real-batch.lock"):
            return self._run_real_batch_locked(
                records, source_dir, limit=limit, essay_question=essay_question,
                model_profile=model_profile, progress_callback=progress_callback,
                cancelled=cancelled,
            )

    def _run_real_batch_locked(self, records, source_dir, *, limit=None, essay_question=None, model_profile=None,
                               progress_callback=None, cancelled=None):
        """Grade independently, then persist validated rows in intake order."""
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValidationError("Batch limit must be a positive integer")
        source_dir = Path(source_dir).resolve()
        records = list(records)
        def ordering(item):
            sequence = item.get("sequence", item.get("start_page_idx", 0))
            try:
                sequence = int(sequence)
            except (TypeError, ValueError):
                sequence = 0
            return (sequence, str(item.get("source_pdf", "")))
        selected = sorted(records, key=ordering)
        if limit is not None:
            selected = selected[:limit]
        validated = []
        failed = []
        seen = set()
        stopped_early = False
        existing = set()
        work_items = []
        timing_guard = threading.Lock()
        timing_students = {}
        active_graders = 0
        max_active_graders = 0
        active_writers = 0
        max_active_writers = 0
        pending = {}
        buffered = {}
        next_to_submit = 0
        next_to_persist = 0
        batch_started_at = datetime.now(timezone.utc)
        batch_started = time.perf_counter()
        last_remaining_not_started = 0

        def record_timing(key, event):
            nonlocal active_graders, max_active_graders
            stamp = datetime.now(timezone.utc).isoformat()
            fields = {
                "grading_start": "grading_started_at",
                "grading_finish": "grading_finished_at",
                "validation_finish": "validation_finished_at",
                "persistence_finish": "persistence_finished_at",
            }
            with timing_guard:
                timing_students.setdefault(key, {})[fields[event]] = stamp
                if event == "grading_start":
                    active_graders += 1
                    max_active_graders = max(max_active_graders, active_graders)
                elif event == "grading_finish":
                    active_graders = max(0, active_graders - 1)

        def writer_started():
            nonlocal active_writers, max_active_writers
            with timing_guard:
                active_writers += 1
                max_active_writers = max(max_active_writers, active_writers)

        def writer_finished():
            nonlocal active_writers
            with timing_guard:
                active_writers = max(0, active_writers - 1)

        def report(active_count=0, current="", *, interrupted=False):
            nonlocal last_remaining_not_started
            completed_count = len(existing) + len(validated)
            active_count = max(0, int(active_count))
            not_started_total = len(work_items) if work_items else max(0, len(selected) - len(existing))
            remaining_not_started = max(0, not_started_total - next_to_submit)
            last_remaining_not_started = remaining_not_started
            if progress_callback is None:
                return
            payload = {
                "total": len(selected),
                "completed": completed_count,
                "active": max(0, min(active_count, len(selected) - completed_count - len(failed))),
                "waiting": max(0, len(selected) - completed_count - len(failed) - active_count),
                "finishing": active_count if stopped_early else 0,
                "remaining_not_started": remaining_not_started,
                "attention": len(failed),
                "current": current or "",
                "interrupted": bool(interrupted or stopped_early),
            }
            progress_callback(payload)

        # Reconstruct durable completions before showing progress. A completion
        # requires the authoritative workbook row, audit identity, digest, and
        # committed status. Approved rows count as complete too.
        for record in selected:
            identity = Identity.from_dict({key: record[key] for key in ("student_id", "student_name", "class_name")})
            identity_key = (identity.class_name, identity.student_id)
            if identity_key in seen:
                raise ValidationError(f"Duplicate selected student: {identity_key}")
            seen.add(identity_key)
            source_pdf = source_dir / str(record["source_pdf"])
            if self._real_result_is_durable(source_pdf, identity, essay_question, model_profile):
                existing.add(job_key(identity))
        report()

        for record in selected:
            identity = Identity.from_dict({key: record[key] for key in ("student_id", "student_name", "class_name")})
            source_pdf = source_dir / str(record["source_pdf"])
            key = job_key(identity)
            if key in existing:
                continue
            work_items.append({
                "index": len(work_items), "record": record, "identity": identity,
                "source_pdf": source_pdf, "job_id": key,
            })

        def grade_one(item):
            key = item["job_id"]
            calibration_namespace = self._calibration_namespace_for_attempt(key)
            return self.run_real_pdf(
                item["source_pdf"], item["identity"], essay_question, model_profile,
                persist_workbook=False,
                execution_namespace=calibration_namespace,
                fresh_attempt=(calibration_namespace != self.batch_id),
                timing_callback=lambda event: record_timing(key, event),
            )

        def display(item):
            identity = item["identity"]
            return f"{identity.class_name} · {identity.student_id} · {identity.student_name}"

        timing_started_at = batch_started_at.isoformat()

        def submit_available(executor):
            nonlocal next_to_submit, stopped_early
            while next_to_submit < len(work_items) and len(pending) < MAX_CONCURRENT_GRADERS:
                if cancelled is not None and cancelled():
                    stopped_early = True
                    break
                item = work_items[next_to_submit]
                future = executor.submit(grade_one, item)
                pending[future] = item
                next_to_submit += 1

        if cancelled is not None and cancelled() and work_items:
            stopped_early = True

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_GRADERS, thread_name_prefix="student-grader") as executor:
            submit_available(executor)
            def current_work():
                if pending:
                    return display(next(iter(pending.values())))
                if buffered:
                    return display(buffered[min(buffered)][0])
                return ""

            report(len(pending), current_work(), interrupted=stopped_early)
            while pending:
                done, _not_done = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    item = pending.pop(future)
                    try:
                        buffered[item["index"]] = (item, future.result(), None)
                    except Exception as exc:
                        buffered[item["index"]] = (item, None, exc)

                # A returned validated result is still in progress until the
                # ordered workbook write succeeds.
                report(len(pending) + len(buffered), current_work(), interrupted=stopped_early)

                while next_to_persist in buffered:
                    item, result, error = buffered.pop(next_to_persist)
                    next_to_persist += 1
                    identity = item["identity"]
                    if error is not None:
                        failed.append({"identity": identity.to_dict(), "source_pdf": str(item["source_pdf"]),
                                       "error": {"type": type(error).__name__, "message": str(error)}})
                    elif result.get("state") != State.VALIDATED.value:
                        failed.append({"identity": identity.to_dict(), "source_pdf": str(item["source_pdf"]),
                                       "state": result.get("state"), "error": "grading was not validated"})
                    else:
                        try:
                            job_dir = Path(result["job_dir"])
                            checkpoint = read_json(job_dir / "student_record.json")
                            grading = self.validator.validate(
                                read_json(job_dir / "validated_result.json"), identity
                            )
                            record_timing(item["job_id"], "validation_finish")
                            review_status = self._persist_real_result(
                                grading, identity, item["job_id"], checkpoint["input_digest"],
                                essay_question or "", writer_started=writer_started,
                                writer_finished=writer_finished,
                            )
                            record_timing(item["job_id"], "persistence_finish")
                            validated.append({"identity": identity.to_dict(), **result,
                                              "review_status": review_status})
                        except Exception as exc:
                            failed.append({"identity": identity.to_dict(), "source_pdf": str(item["source_pdf"]),
                                           "error": {"type": type(exc).__name__, "message": str(exc)}})

                if cancelled is not None and cancelled() and next_to_submit < len(work_items):
                    stopped_early = True
                outstanding = len(pending) + len(buffered)
                report(outstanding, current_work(), interrupted=stopped_early)
                if not stopped_early:
                    submit_available(executor)
                    report(len(pending) + len(buffered), current_work(), interrupted=stopped_early)

        batch_finished_at = datetime.now(timezone.utc)
        elapsed_seconds = max(0.0, time.perf_counter() - batch_started)
        with timing_guard:
            timing_snapshot = {
                "schema_version": 1,
                "batch_id": self.batch_id,
                "workbook": str(self.excel.path.resolve()),
                "batch_started_at": timing_started_at,
                "batch_finished_at": batch_finished_at.isoformat(),
                "elapsed_seconds": round(elapsed_seconds, 3),
                "max_simultaneous_graders": max_active_graders,
                "max_simultaneous_workbook_writers": max_active_writers,
                "students": timing_students,
            }
        timing_warning = None
        try:
            atomic_json(self.jobs_dir / "parallel_timing.json", timing_snapshot)
        except Exception as exc:
            timing_warning = f"{type(exc).__name__}: {exc}"

        outcome = {
            "batch_id": self.batch_id,
            "selected": len(selected),
            "validated": validated,
            "failed": failed,
            "workbook": str(self.excel.path) if validated or existing else None,
            "model_profile": model_profile,
            "already_complete": len(existing),
            "interrupted": stopped_early,
            "remaining_not_started": last_remaining_not_started,
        }
        if timing_warning is not None:
            outcome["timing_evidence_warning"] = timing_warning
        report(0, "", interrupted=stopped_early)
        return outcome

    def _real_result_is_durable(self, source_pdf, identity, essay_question, model_profile):
        """Return DONE only for a valid authoritative workbook/audit commit."""
        key = job_key(identity)
        if not self.excel.path.is_file():
            return False
        try:
            book = self.excel._open()
            try:
                row, audit = self.excel._row(book, key)
                if row is None or audit is None:
                    return False
                if audit[0].value != key:
                    return False
                if (roster_text(audit[1].value), roster_text(audit[2].value)) != (
                        identity.class_name, identity.student_id):
                    return False
                if audit[3].value != row[0].row:
                    return False
                digest = audit[4].value
                if not isinstance(digest, str) or not digest.strip():
                    return False
                if audit[5].value not in {"VALIDATED", "REVIEWED", "APPROVED", "RENDERED", "COMPLETE"}:
                    return False
                record = self.excel._decode(row, identity)
            finally:
                book.close()
            return record.review_status in ("PENDING", "APPROVED")
        except Exception:
            return False
