"""One-student blind calibration orchestration; stops at VALIDATED."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil

from pypdf import PdfReader

from excel.calibration_workbook import CalibrationWorkbookRepository, REVIEW_STATUS
from grading.calibration_schema import CalibrationValidator, response_json_schema
from grading.codex_sol_grader import CodexSolGrader
from grading.schemas import CRITERIA, RATINGS, Identity, ROOT, ValidationError
from grading.sol_grader import CredentialUnavailable, ModelCallError, SolGrader, SolGradingInput, extract_output_text
from .pipeline import fingerprint, job_key, safe_batch_id
from .state import State, transition
from .storage import atomic_json, exclusive_lock, read_json


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def immutable_json(path, value):
    path = Path(path)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValidationError(f"Immutable snapshot changed: {path.name}")
    else:
        path.write_text(encoded, encoding="utf-8", newline="\n")


def immutable_text(path, value):
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") != value:
            raise ValidationError(f"Immutable snapshot changed: {path.name}")
    else:
        path.write_text(value, encoding="utf-8", newline="\n")


class CalibrationPipeline:
    def __init__(self, project_dir=ROOT, *, config_dir=ROOT / "config", grader_factory=None, model_profile=None,
                 marker_skill_path=None):
        self.project_dir = Path(project_dir).resolve()
        self.config_dir = Path(config_dir).resolve()
        self.grader_factory = grader_factory
        model_catalog = read_json(self.config_dir / "calibration_model.json")
        configured_skill = marker_skill_path or model_catalog.get("marker_skill_path")
        self.marker_skill_path = (ROOT / "grading/skills/sol-grader/SKILL.md"
                                  if configured_skill is None else Path(configured_skill))
        if not self.marker_skill_path.is_absolute():
            self.marker_skill_path = self.config_dir / self.marker_skill_path
        profiles = model_catalog.get("profiles")
        if not isinstance(profiles, dict):
            raise ValidationError("Calibration model configuration must contain profiles")
        self.model_profile = model_profile or model_catalog.get("active_profile")
        if self.model_profile not in profiles:
            raise ValidationError(f"Unknown calibration model profile: {self.model_profile}")
        self.model_config = profiles[self.model_profile]
        self.criteria_config = read_json(self.config_dir / "criteria.json")
        self.text_limits = read_json(self.config_dir / "text_limits.json")
        self.rubric = read_json(self.config_dir / "calibration_rubric_v2.json")
        self.reference_path = ROOT / "grading/references/reference_example_v1.md"
        if self.model_config.get("backend") not in ("codex", "openai_api"):
            raise ValidationError("Calibration backend must be codex or openai_api")
        if self.model_config.get("prompt_version") != "sol-calibration-v2" or self.model_config.get("schema_version") != "calibration-response-v2":
            raise ValidationError("Unsupported active grading instruction or schema version")
        if self.criteria_config != {"criteria": list(CRITERIA), "ratings": list(RATINGS)}:
            raise ValidationError("Calibration criteria configuration changed")
        if (self.rubric["rubric_version"] != self.model_config["rubric_version"]
                or self.rubric["criteria"] != list(CRITERIA)
                or self.rubric["numeric_score"]["available"] is not False):
            raise ValidationError("Calibration rubric must use the approved criteria and no invented score")
        if self.model_config.get("reference_version") != "reference-example-v1" or not self.reference_path.is_file():
            raise ValidationError("Versioned feedback reference is unavailable")

    def _new_grader(self):
        if self.grader_factory is not None:
            return self.grader_factory()
        common = {
            "model": self.model_config["model"],
            "reasoning_effort": self.model_config["reasoning_effort"],
            "timeout_seconds": self.model_config["request_timeout_seconds"],
        }
        if self.model_config["backend"] == "codex":
            return CodexSolGrader(
                **common,
                codex_executable=self.model_config.get("codex_executable", "codex"),
                render_dpi=self.model_config.get("codex_render_dpi", 200),
                workspace_parent=self.project_dir / "jobs" / ".codex-workspaces",
            )
        return SolGrader(**common)

    def _advance(self, checkpoint_path, checkpoint, target):
        checkpoint["state"] = transition(State(checkpoint["state"]), target).value
        checkpoint["history"].append(target.value)
        checkpoint["last_error"] = None
        atomic_json(checkpoint_path, checkpoint)

    def _prompt(self, identity, essay_question, schema, marker_skill=None):
        template = self.marker_skill_path.read_text(encoding="utf-8") if marker_skill is None else marker_skill
        if not template.strip():
            raise ValidationError("Marker SKILL.md must not be empty")
        reference = self.reference_path.read_text(encoding="utf-8")
        context = {
            "identity": identity.to_dict(),
            "essay_question": essay_question,
            "criteria": list(CRITERIA),
            "allowed_ratings": list(RATINGS),
            "rubric": self.rubric,
            "text_limits": self.text_limits,
            "required_output_schema": schema,
        }
        return (template.rstrip() + "\n\n--- reference_example.md（仅作语言质量参考）---\n"
                + reference.rstrip() + "\n--- reference_example.md 结束 ---\n\n校准输入：\n"
                + json.dumps(context, ensure_ascii=False, sort_keys=True) + "\n")

    def prepare(self, source_pdf, identity: Identity, essay_question=None, execution_namespace=None):
        source_pdf = Path(source_pdf).resolve()
        if not source_pdf.is_file() or source_pdf.suffix.lower() != ".pdf":
            raise ValidationError("One existing PDF source is required")
        source_bytes = source_pdf.read_bytes()
        source_hash = sha256_bytes(source_bytes)
        page_count = len(PdfReader(source_pdf).pages)
        if page_count < 1:
            raise ValidationError("Source PDF has no pages")
        namespace = None if execution_namespace is None else safe_batch_id(execution_namespace)
        profile_suffix = "" if self.model_profile == "sol_medium" else "_" + self.model_profile
        namespace_suffix = "" if namespace is None else "_" + namespace
        key = "calibration" + namespace_suffix + "_" + job_key(identity).removeprefix("student_") + profile_suffix + "_" + source_hash[:12]
        job_dir = self.project_dir / "jobs" / key
        output_dir = self.project_dir / "output" / key
        checkpoint_path = job_dir / "student_record.json"
        with exclusive_lock(self.project_dir / "jobs" / ".calibration.lock"):
            job_dir.mkdir(parents=True, exist_ok=True)
            if checkpoint_path.exists():
                checkpoint = read_json(checkpoint_path)
                if checkpoint["source_sha256"] != source_hash or checkpoint["identity"] != identity.to_dict():
                    raise ValidationError("Existing calibration job belongs to different input")
            else:
                checkpoint = {
                    "schema_version": self.model_config["schema_version"],
                    "mode": "REAL_SOL_CALIBRATION",
                    "job_id": key,
                    "model_profile": self.model_profile,
                    "execution_namespace": namespace,
                    "identity": identity.to_dict(),
                    "source_original_path": str(source_pdf),
                    "source_sha256": source_hash,
                    "source_page_count": page_count,
                    "model_identifier": self.model_config["model"],
                    "reasoning_effort": self.model_config["reasoning_effort"],
                    "prompt_version": self.model_config["prompt_version"],
                    "reference_version": self.model_config["reference_version"],
                    "rubric_version": self.model_config["rubric_version"],
                    "state": State.NEW.value,
                    "history": [State.NEW.value],
                    "live_request_attempts": 0,
                    "review_status": None,
                    "last_error": None,
                }
                atomic_json(checkpoint_path, checkpoint)
            isolated_source = job_dir / "source.pdf"
            if isolated_source.exists() and sha256_file(isolated_source) != source_hash:
                raise ValidationError("Existing isolated source.pdf hash mismatch")
            manifest_path = job_dir / "grading_input_manifest.json"
            if manifest_path.exists():
                manifest = read_json(manifest_path)
                if manifest["source_sha256"] != source_hash:
                    raise ValidationError("Calibration manifest source hash mismatch")
                for name, expected_hash in manifest["snapshot_sha256"].items():
                    snapshot = job_dir / name
                    if not snapshot.exists() or sha256_file(snapshot) != expected_hash:
                        raise ValidationError(f"Calibration snapshot hash mismatch: {name}")
            if State(checkpoint["state"]) == State.NEW:
                target = job_dir / "source.pdf"
                if not target.exists():
                    shutil.copyfile(source_pdf, target)
                self._advance(checkpoint_path, checkpoint, State.SCANNED)
            if State(checkpoint["state"]) == State.SCANNED:
                immutable_json(job_dir / "identity_snapshot.json", identity.to_dict())
                self._advance(checkpoint_path, checkpoint, State.IDENTIFIED)
            if State(checkpoint["state"]) == State.IDENTIFIED:
                schema = response_json_schema(self.text_limits)
                marker_skill = self.marker_skill_path.read_text(encoding="utf-8")
                prompt = self._prompt(identity, essay_question, schema, marker_skill)
                immutable_json(job_dir / "criteria_snapshot.json", self.criteria_config)
                immutable_json(job_dir / "text_limits_snapshot.json", self.text_limits)
                immutable_json(job_dir / "rubric_snapshot.json", self.rubric)
                immutable_text(job_dir / "reference_example.md", self.reference_path.read_text(encoding="utf-8"))
                immutable_json(job_dir / "schema_snapshot.json", schema)
                immutable_text(job_dir / "prompt_snapshot.txt", prompt)
                immutable_text(job_dir / "marker_SKILL.md", marker_skill)
                immutable_json(job_dir / "transcription_status.json", {"required": False, "input_mode": "direct_pdf", "page_order": list(range(1, page_count + 1))})
                snapshot_files = ["criteria_snapshot.json", "text_limits_snapshot.json", "rubric_snapshot.json", "reference_example.md", "schema_snapshot.json", "prompt_snapshot.txt", "marker_SKILL.md"]
                hashes = {name: sha256_file(job_dir / name) for name in snapshot_files}
                immutable_json(job_dir / "grading_input_manifest.json", {
                    "job_id": key,
                    "identity": identity.to_dict(),
                    "model_profile": self.model_profile,
                    "execution_namespace": namespace,
                    "source_file": "source.pdf",
                    "source_sha256": source_hash,
                    "source_page_count": page_count,
                    "essay_question": essay_question,
                    "input_mode": "direct_pdf",
                    "model_identifier": self.model_config["model"],
                    "reasoning_effort": self.model_config["reasoning_effort"],
                    "prompt_version": self.model_config["prompt_version"],
                    "reference_version": self.model_config["reference_version"],
                    "rubric_version": self.model_config["rubric_version"],
                    "schema_version": self.model_config["schema_version"],
                    "snapshot_sha256": hashes,
                    "excluded_inputs": ["other student essays", "historical teacher comments", "historical ratings", "historical scores", "expected output", "diagnostic card"],
                })
                self._advance(checkpoint_path, checkpoint, State.TRANSCRIBED)
            return job_dir, output_dir, read_json(checkpoint_path)

    def run(self, source_pdf, identity: Identity, essay_question=None, *, allow_second_live_attempt=False,
            execution_namespace=None, timing_callback=None):
        job_dir, output_dir, checkpoint = self.prepare(
            source_pdf, identity, essay_question, execution_namespace=execution_namespace
        )
        checkpoint_path = job_dir / "student_record.json"
        if State(checkpoint["state"]) == State.VALIDATED:
            return {"state": checkpoint["state"], "job_dir": str(job_dir), "workbook": str(output_dir / "calibration.xlsx")}
        if State(checkpoint["state"]) != State.TRANSCRIBED:
            raise ValidationError(f"Calibration cannot run from {checkpoint['state']}")
        attempts = checkpoint["live_request_attempts"]
        if allow_second_live_attempt and attempts != 1:
            raise ModelCallError("Second-attempt authorization requires exactly one recorded prior attempt")
        maximum_attempts = 2 if allow_second_live_attempt else 1
        if attempts >= maximum_attempts:
            raise ModelCallError("This calibration job already used its single model attempt")

        grader = self._new_grader()
        try:
            grader.ensure_ready()
        except CredentialUnavailable as exc:
            checkpoint["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
            atomic_json(checkpoint_path, checkpoint)
            atomic_json(job_dir / "validation_report.json", {"status": "PREFLIGHT_BLOCKED", "model_request_attempted": False, "error": checkpoint["last_error"]})
            raise

        schema = read_json(job_dir / "schema_snapshot.json")
        request = SolGradingInput(
            identity=identity,
            pdf_bytes=(job_dir / "source.pdf").read_bytes(),
            pdf_sha256=checkpoint["source_sha256"],
            essay_question=essay_question,
            criteria=CRITERIA,
            ratings=RATINGS,
            rubric=read_json(job_dir / "rubric_snapshot.json"),
            text_limits=read_json(job_dir / "text_limits_snapshot.json"),
            response_schema=schema,
            prompt=(job_dir / "prompt_snapshot.txt").read_text(encoding="utf-8"),
            prompt_version=checkpoint["prompt_version"],
            reference_example=(job_dir / "reference_example.md").read_text(encoding="utf-8"),
            reference_version=checkpoint["reference_version"],
            rubric_version=checkpoint["rubric_version"],
            schema_version=checkpoint["schema_version"],
        )
        checkpoint["live_request_attempts"] = attempts + 1
        atomic_json(checkpoint_path, checkpoint)
        try:
            if timing_callback is not None:
                timing_callback("grading_start")
            try:
                raw = grader.grade(request)
            finally:
                if timing_callback is not None:
                    timing_callback("grading_finish")
        except Exception as exc:
            checkpoint["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
            atomic_json(checkpoint_path, checkpoint)
            atomic_json(job_dir / "validation_report.json", {"status": "MODEL_CALL_FAILED", "model_request_attempted": True, "error": checkpoint["last_error"]})
            raise
        atomic_json(job_dir / "raw_model_response.json", raw)
        self._advance(checkpoint_path, checkpoint, State.GRADED)
        try:
            parsed = json.loads(extract_output_text(raw))
            validator = CalibrationValidator(self.text_limits, checkpoint["source_page_count"])
            result = validator.validate(parsed, identity)
            atomic_json(job_dir / "parsed_result.json", result.to_dict())
            if result.reading_quality.materially_affects_grade:
                atomic_json(job_dir / "validation_report.json", {
                    "status": "MATERIAL_READING_UNCERTAINTY",
                    "structurally_valid": True,
                    "grading_accepted": False,
                    "workbook_written": False,
                })
                return {"state": State.GRADED.value, "job_dir": str(job_dir), "workbook": None, "review_status": None}
            metadata = {
                "模型标识": checkpoint["model_identifier"],
                "模型配置": self.model_profile,
                "推理强度": checkpoint["reasoning_effort"],
                "提示词版本": checkpoint["prompt_version"],
                "参考范例版本": checkpoint["reference_version"],
                "评分规则版本": checkpoint["rubric_version"],
                "结构版本": checkpoint["schema_version"],
                "原PDF SHA-256": checkpoint["source_sha256"],
                "输入模式": "direct_pdf",
                "题目": essay_question or "仅知题号 Q2；完整题目未提供",
                "配置快照哈希": json.dumps(read_json(job_dir / "grading_input_manifest.json")["snapshot_sha256"], ensure_ascii=False, sort_keys=True),
            }
            workbook = CalibrationWorkbookRepository(output_dir / "calibration.xlsx")
            workbook.write_initial(result, metadata, essay_question or "")
            checkpoint["review_status"] = REVIEW_STATUS
            atomic_json(job_dir / "validation_report.json", {
                "status": "VALID",
                "structurally_valid": True,
                "grading_accepted": True,
                "reading_materially_affects_grade": False,
                "workbook_written": True,
                "workbook": str(workbook.path),
            })
            self._advance(checkpoint_path, checkpoint, State.VALIDATED)
            return {"state": State.VALIDATED.value, "job_dir": str(job_dir), "workbook": str(workbook.path), "review_status": REVIEW_STATUS}
        except Exception as exc:
            checkpoint = read_json(checkpoint_path)
            checkpoint["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
            atomic_json(checkpoint_path, checkpoint)
            atomic_json(job_dir / "validation_report.json", {
                "status": "VALIDATION_FAILED",
                "structurally_valid": False,
                "grading_accepted": False,
                "workbook_written": False,
                "error": checkpoint["last_error"],
            })
            raise
