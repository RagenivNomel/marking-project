"""Restartable orchestration, shared by the CLI and future wrapper."""
from dataclasses import asdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
import traceback
from typing import Callable

from excel.schema import AUDIT_SHEET, SHEET
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
# Diagnostic record of discarded unfinished attempts; never read by recovery.
DISCARD_LOG = "discarded_attempts.log"


def _marking_trace(message):
    if os.environ.get("MUMS_MARKING_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[marking] {message}", file=sys.stderr, flush=True)


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

    def _discard_working_state(self, key, reason=None):
        """Delete one essay's app-generated working files.

        Only ``jobs/<task>/<essay>/`` is touched, and its ``output/`` folder of
        feedback-card evidence is kept. The workbook, source scans and identity
        decisions live elsewhere and are never recovery scope. When a reason is
        given the discard is logged; the log is diagnostic and never read back.
        """
        essay_dir = self.jobs_dir / key
        if not essay_dir.is_dir():
            return []
        discarded = []
        for child in sorted(essay_dir.iterdir()):
            if child.name == "output":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
            discarded.append(child.name)
        if discarded and reason:
            _marking_trace(f"discarded student={key} reason={reason} files={discarded}")
            try:
                with (self.jobs_dir / DISCARD_LOG).open("a", encoding="utf-8") as log:
                    log.write(f"{datetime.now(timezone.utc).isoformat()}\t{key}\t{reason}\t{','.join(discarded)}\n")
            except OSError:
                pass
        return discarded

    def _grade_essay(self, source_pdf, identity, essay_question, profile, timing_callback=None):
        """Mark one essay from scratch in a fresh working folder.

        Every grader file (prompt snapshots, model response, per-call checks)
        stays inside ``work/``, so discarding the essay folder removes the
        whole attempt. Returns the validated result and the grader's suggested
        question number and section scores; nothing is saved here.
        """
        work_dir = self.jobs_dir / job_key(identity) / "work"
        work_dir.mkdir(parents=True)
        if self.real_pipeline_factory is None:
            from workflow.calibration_pipeline import CalibrationPipeline
            grader = CalibrationPipeline(work_dir, config_dir=self.config_dir, model_profile=profile)
        else:
            grader = self.real_pipeline_factory(work_dir, model_profile=profile)
        outcome = grader.run(source_pdf, identity, essay_question, timing_callback=timing_callback)
        if outcome.get("state") == State.GRADED.value:
            raise ValidationError("The essay could not be read clearly enough to mark; check the scan")
        if outcome.get("state") != State.VALIDATED.value:
            raise ValidationError("The grader did not produce a validated result")
        parsed = read_json(Path(outcome["job_dir"]) / "parsed_result.json")
        suggested = {"question_number": parsed.get("question_number"), "scores": parsed.get("scores")}
        return self.validator.validate(parsed["grading"], identity), suggested

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
        """Grade independently, then save each result row in intake order.

        An essay is done only when the workbook holds its valid result and
        audit rows. Every other essay is marked from scratch after its old
        working files are discarded; nothing is resumed mid-attempt.
        """
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValidationError("Batch limit must be a positive integer")
        model_catalog = read_json(self.config_dir / "calibration_model.json")
        profile = model_profile or model_catalog.get("active_profile")
        if profile not in model_catalog.get("profiles", {}):
            raise ValidationError(f"Unknown calibration model profile: {profile}")
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
        _marking_trace(f"batch={self.batch_id} selected={len(selected)} source={source_dir}")
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

        # Done essays come only from the workbook. Their leftover working
        # files, if any, are cleared; every other essay becomes work.
        for record in selected:
            identity = Identity.from_dict({key: record[key] for key in ("student_id", "student_name", "class_name")})
            identity_key = (identity.class_name, identity.student_id)
            if identity_key in seen:
                raise ValidationError(f"Duplicate selected student: {identity_key}")
            seen.add(identity_key)
            key = job_key(identity)
            state = self._workbook_state(identity)
            if state == "saved":
                existing.add(key)
                try:
                    self._discard_working_state(key, "already saved in workbook")
                except OSError as exc:
                    _marking_trace(f"cleanup failed student={key} {type(exc).__name__}: {exc}")
            elif state == "damaged":
                # Rows are never overwritten, so marking again could not save.
                failed.append({"identity": identity.to_dict(),
                               "source_pdf": str(source_dir / str(record["source_pdf"])),
                               "error": {"type": "ValidationError", "message": (
                                   "The workbook already has a row for this student that needs checking; "
                                   "it was not changed and the essay was not marked again")}})
            else:
                work_items.append({
                    "index": len(work_items), "record": record, "identity": identity,
                    "source_pdf": source_dir / str(record["source_pdf"]), "job_id": key,
                })
        report()

        def grade_one(item):
            key = item["job_id"]
            identity = item["identity"]
            label = f"{identity.class_name} · {identity.student_id} · {identity.student_name}"
            _marking_trace(f"start student={label}")
            self._discard_working_state(key, "not saved in workbook; marking again from scratch")
            source_pdf = Path(item["source_pdf"]).resolve()
            digest = fingerprint({
                "identity": identity.to_dict(),
                "source_sha256": hashlib.sha256(source_pdf.read_bytes()).hexdigest(),
                "essay_question": essay_question,
                "model_profile": profile,
            })
            result, suggested = self._grade_essay(
                source_pdf, identity, essay_question, profile,
                timing_callback=lambda event: record_timing(key, event),
            )
            record_timing(key, "validation_finish")
            _marking_trace(f"grader returned student={label}")
            return result, suggested, digest

        def display(item):
            identity = item["identity"]
            return f"{identity.class_name} · {identity.student_id} · {identity.student_name}"

        def fail(item, exc, stage):
            _marking_trace(f"{stage} failed={item['job_id']} {type(exc).__name__}: {exc}")
            if os.environ.get("MUMS_MARKING_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}:
                traceback.print_exception(exc, file=sys.stderr)
            failed.append({"identity": item["identity"].to_dict(), "source_pdf": str(item["source_pdf"]),
                           "error": {"type": type(exc).__name__, "message": str(exc)}})
            try:
                self._discard_working_state(item["job_id"], f"{stage} failed: {type(exc).__name__}")
            except OSError as cleanup_error:
                _marking_trace(f"cleanup failed student={item['job_id']} {cleanup_error}")

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

                # A graded result is still in progress until its workbook
                # row is saved; only that save makes the essay done.
                report(len(pending) + len(buffered), current_work(), interrupted=stopped_early)

                while next_to_persist in buffered:
                    item, graded, error = buffered.pop(next_to_persist)
                    next_to_persist += 1
                    if error is not None:
                        fail(item, error, "marking")
                        continue
                    identity = item["identity"]
                    grading, suggested, digest = graded
                    try:
                        with timing_guard:
                            active_writers += 1
                            max_active_writers = max(max_active_writers, active_writers)
                        try:
                            # A batch-level essay question takes precedence over the grader's reading.
                            self.excel.ensure_draft(grading, identity, item["job_id"], digest,
                                                    essay_question or suggested["question_number"] or "",
                                                    teacher_scores=suggested["scores"])
                            if self._workbook_state(identity) != "saved":
                                raise ValidationError("The result row could not be verified in the workbook after saving")
                            review_status = self.excel.get(item["job_id"], identity).review_status
                        finally:
                            with timing_guard:
                                active_writers = max(0, active_writers - 1)
                    except Exception as exc:
                        fail(item, exc, "saving")
                        continue
                    record_timing(item["job_id"], "persistence_finish")
                    validated.append({"identity": identity.to_dict(), "state": State.VALIDATED.value,
                                      "job_id": item["job_id"], "workbook": str(self.excel.path),
                                      "review_status": review_status})
                    try:
                        self._discard_working_state(item["job_id"])
                    except OSError as exc:
                        # The saved row is the completion; leftovers are
                        # cleared on the next run.
                        _marking_trace(f"cleanup failed student={item['job_id']} {exc}")

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
            "model_profile": profile,
            "already_complete": len(existing),
            "interrupted": stopped_early,
            "remaining_not_started": last_remaining_not_started,
        }
        if timing_warning is not None:
            outcome["timing_evidence_warning"] = timing_warning
        report(0, "", interrupted=stopped_early)
        return outcome

    def _workbook_state(self, identity):
        """Return "saved", "missing" or "damaged" for this essay's workbook row.

        "saved" (DONE) needs a valid result row plus its matching audit row.
        "damaged" means the workbook holds some row or audit entry for the
        student that is not a valid pair; it is left for the teacher to check.
        """
        key = job_key(identity)
        if not self.excel.path.is_file():
            return "missing"
        student = (identity.class_name, identity.student_id)
        try:
            book = self.excel._open()
        except Exception:
            return "damaged"
        try:
            audits = [audit for audit in book[AUDIT_SHEET].iter_rows(min_row=2)
                      if audit[0].value == key
                      or (roster_text(audit[1].value), roster_text(audit[2].value)) == student]
            rows = [row for row in book[SHEET].iter_rows(min_row=2)
                    if (roster_text(row[0].value), roster_text(row[1].value)) == student]
            if not audits and not rows:
                return "missing"
            try:
                row, audit = self.excel._row(book, key)
                if (row is None or audit is None or len(audits) != 1 or len(rows) != 1
                        or row[0].row != rows[0][0].row):
                    return "damaged"
                if (roster_text(audit[1].value), roster_text(audit[2].value)) != student:
                    return "damaged"
                if audit[3].value != row[0].row:
                    return "damaged"
                digest = audit[4].value
                if not isinstance(digest, str) or not digest.strip():
                    return "damaged"
                if audit[5].value not in {"VALIDATED", "REVIEWED", "APPROVED", "RENDERED", "COMPLETE"}:
                    return "damaged"
                record = self.excel._decode(row, identity)
            except Exception:
                return "damaged"
            return "saved" if record.review_status in ("PENDING", "APPROVED") else "damaged"
        finally:
            book.close()
