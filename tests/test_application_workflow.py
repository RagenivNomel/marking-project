import copy
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook
from PIL import Image
from pypdf import PdfWriter

from application import Action, AssignmentSource, WorkflowController
from excel.schema import AUDIT_SHEET, SHEET
from excel.workbook import ExcelStore
from grading.codex_sol_grader import CodexSolGrader
from grading.mock_grader import MockGrader
from grading.schemas import CRITERIA, CriterionResult, GradingResult, Identity, ValidationError, Validator
from grading.sol_grader import SolGrader
from rendering.renderer import PillowRenderer
from tests.local_temp import local_test_directory
from workflow.calibration_pipeline import CalibrationPipeline
from workflow.pipeline import Pipeline
from workflow import calibration_pipeline as calibration_pipeline_module
from workflow import pipeline as pipeline_module
from workflow import storage as storage_module


from application.workflows.sec2_hcl_composition_v1 import CompositionWorkflow


class ApplicationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory(self._testMethodName)
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)
        self.config_dir = self.root / "config"
        self.config_dir.mkdir()
        source_config = Path(__file__).resolve().parents[1] / "config"
        for config in source_config.glob("*.json"):
            shutil.copy2(config, self.config_dir / config.name)
        self.validator = Validator(self.config_dir)
        self.workbook = self.root / "results.xlsx"
        self.jobs = self.root / "jobs"
        self.receipts = self.root / "receipts"
        self.controller = WorkflowController()

    def _identity(self, student_id="016", student_name="测试学生", class_name="207"):
        return Identity(student_id, student_name, class_name)

    def _grading_result(self, identity):
        return GradingResult(
            student_id=identity.student_id,
            student_name=identity.student_name,
            class_name=identity.class_name,
            criteria={
                name: CriterionResult(
                    rating="可以更进一步",
                    short_comment=f"{identity.student_id}号{index}号评语。",
                )
                for index, name in enumerate(CRITERIA, 1)
            },
            teacher_comment=f"{identity.student_id}号教师总评。",
        )

    def _add_workbook_row(self, job_id, identity, review_status="PENDING", path=None):
        path = self.workbook if path is None else Path(path)
        store = ExcelStore(path, self.validator)
        digest = f"fixture-digest-{job_id}"
        store.ensure_draft(
            self._grading_result(identity),
            identity,
            job_id,
            digest,
            topic="Q2 临时题目",
        )
        pipeline_status = "APPROVED" if review_status == "APPROVED" else "VALIDATED"
        store.set_status(job_id, identity, pipeline_status, review_status)
        return store, digest

    def _write_receipt(
        self,
        job_id,
        identity,
        store,
        digest,
        *,
        make_artifact=True,
        mismatched=False,
        artifact_name="student_card.png",
    ):
        output_dir = self.receipts / job_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = output_dir / artifact_name
        width, height = 11, 7
        if make_artifact:
            image = Image.new("RGB", (width, height), (245, 245, 245))
            image.save(artifact, format="PNG")
            artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        else:
            artifact_hash = hashlib.sha256(b"missing fixture artifact").hexdigest()

        row_number = store.row_number(job_id, identity)
        record = store.get(job_id, identity, approved=True)
        approved_values = record.to_dict()
        source_digest = digest
        output_digest = artifact_hash
        source_job_id = job_id
        if mismatched:
            source_digest = "fixture-wrong-digest"
            output_digest = "0" * 64
            source_job_id = "fixture-wrong-job"
            approved_values = copy.deepcopy(approved_values)
            approved_values["teacher_comment"] = "receipt does not match workbook"

        field_names = [
            "class_name",
            "student_id",
            "student_name",
            "topic",
            "content_score",
            "language_structure_score",
            "total_score",
            "teacher_comment",
        ]
        field_names.extend(
            f"criteria.{criterion}.{part}"
            for criterion in CRITERIA
            for part in ("rating", "short_comment")
        )

        def field_value(name):
            if name.startswith("criteria."):
                _, criterion, part = name.split(".")
                return approved_values["criteria"][criterion][part]
            return approved_values[name]

        def display_value(value):
            if value is None or value == "":
                return ""
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return str(value)

        receipt = {
            "renderer": "pillow-renderer-v1.3",
            "status": "PASS",
            "source": {
                "workbook": str(store.path.resolve()),
                "excel_row": row_number,
                "job_id": source_job_id,
                "input_digest": source_digest,
                "pipeline_status": "APPROVED",
                "source_of_truth": "approved_excel_row",
            },
            "master": {
                "version": "fixture-master-v1",
                "filename": "fixture-master.png",
                "sha256": "0" * 64,
                "width": width,
                "height": height,
            },
            "layout_version": "fixture-layout-v1",
            "layout_sha256": "1" * 64,
            "font": {
                "family": "Noto Sans SC",
                "path": str(self.root / "fixture-font.ttf"),
                "sha256": "2" * 64,
                "weight": 600,
                "rating_weight": 700,
            },
            "rating_control": {"arrow_x": 4, "min_arrow_clearance": 1},
            "fields": {
                name: {
                    "source_value": field_value(name),
                    "rendered_text": display_value(field_value(name)),
                    "fits": True,
                }
                for name in field_names
            },
            "approved_excel_values": approved_values,
            "output": {
                "artifact": str(artifact.resolve()),
                "sha256": output_digest,
                "width": width,
                "height": height,
            },
        }
        receipt_path = output_dir / "render_receipt.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        return receipt_path, artifact

    def _source(
        self,
        *,
        workbook=None,
        job_roots=(),
        receipt_roots=(),
        split_pile=None,
        roster=None,
        identity_decisions=None,
    ):
        return AssignmentSource(
            workbook=None if workbook is None else Path(workbook),
            job_roots=tuple(Path(path) for path in job_roots),
            receipt_roots=tuple(Path(path) for path in receipt_roots),
            split_pile=None if split_pile is None else Path(split_pile),
            roster=None if roster is None else Path(roster),
            identity_decisions=(
                None if identity_decisions is None else Path(identity_decisions)
            ),
            config_dir=self.config_dir,
        )

    def _read_only_controller_call(self, method, source):
        guards = (
            (ExcelStore, "_save", "Stage 1 inspection must not save Excel"),
            (PillowRenderer, "render", "Stage 1 inspection must not render"),
            (MockGrader, "grade", "Stage 1 inspection must not use the mock grader"),
            (CodexSolGrader, "grade", "Stage 1 inspection must not use Codex grading"),
            (SolGrader, "grade", "Stage 1 inspection must not use API grading"),
            (Pipeline, "run_mock", "Stage 1 inspection must not run a mock pipeline"),
            (Pipeline, "run_real_pdf", "Stage 1 inspection must not run real grading"),
            (Pipeline, "run_real_batch", "Stage 1 inspection must not run real batches"),
            (CalibrationPipeline, "prepare", "Stage 1 inspection must not prepare grading"),
            (CalibrationPipeline, "run", "Stage 1 inspection must not run calibration"),
            (storage_module, "atomic_json", "Stage 1 inspection must not write checkpoints"),
            (pipeline_module, "atomic_json", "Stage 1 inspection must not write pipeline JSON"),
            (
                calibration_pipeline_module,
                "atomic_json",
                "Stage 1 inspection must not write calibration JSON",
            ),
            (
                calibration_pipeline_module,
                "immutable_json",
                "Stage 1 inspection must not write calibration snapshots",
            ),
            (
                calibration_pipeline_module,
                "immutable_text",
                "Stage 1 inspection must not write calibration text snapshots",
            ),
        )
        with ExitStack() as stack:
            for target, attribute, message in guards:
                stack.enter_context(
                    patch.object(target, attribute, side_effect=AssertionError(message))
                )
            return getattr(self.controller, method)(source)

    @staticmethod
    def _submission(inspection, submission_id):
        return next(item for item in inspection.submissions if item.submission_id == submission_id)

    @staticmethod
    def _attention_text(inspection, submission=None):
        items = list(inspection.attention)
        if submission is None:
            items.extend(
                attention
                for item in inspection.submissions
                for attention in item.attention
            )
        else:
            items.extend(submission.attention)
        return " ".join(
            f"{item.code} {item.message} {item.technical_details}" for item in items
        ).lower()

    @staticmethod
    def _tree_snapshot(root):
        snapshot = {}
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            stat = path.stat()
            if path.is_file():
                snapshot[relative] = (
                    "file",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.st_size,
                    stat.st_mtime_ns,
                )
            else:
                snapshot[relative] = ("directory", stat.st_size, stat.st_mtime_ns)
        return snapshot

    def _write_split_source(
        self,
        identity,
        filename="submission_001.pdf",
        match_status="STRONG_ROSTER_MATCH",
    ):
        split = self.root / "split-pile"
        split.mkdir(parents=True, exist_ok=True)
        source_pdf = split / filename
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with source_pdf.open("wb") as handle:
            writer.write(handle)
        (split / "_continuous.pdf").write_bytes(source_pdf.read_bytes())
        (split / "_manifest.csv").write_text(
            "file,pages,raw_ocr_name,start_page_idx,name_preview\n"
            f"{filename},1,,0,preview.png\n",
            encoding="utf-8-sig",
        )

        roster = self.root / "roster.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.title = "作文诊断输入"
        sheet.append(["班号", "学生姓名", "班级"])
        sheet.append([identity.student_id, identity.student_name, identity.class_name])
        book.save(roster)
        book.close()

        decisions = self.root / "identity-decisions.json"
        decisions.write_text(
            json.dumps(
                [
                    {
                        "source_pdf": filename,
                        "class_name": identity.class_name,
                        "student_id": identity.student_id,
                        "match_status": match_status,
                        "evidence": "fixture roster confirmation",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return split, roster, decisions, source_pdf

    def _write_checkpoint(
        self,
        identity,
        source_pdf,
        *,
        job_id="fixture-attempt",
        state="TRANSCRIBED",
        attempts=1,
        write_grading_result=False,
    ):
        job_dir = self.jobs / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        history = ["NEW", "SCANNED", "IDENTIFIED", "TRANSCRIBED"]
        if state in ("GRADED", "VALIDATED"):
            history.append("GRADED")
        if state == "VALIDATED":
            history.append("VALIDATED")
        checkpoint = {
            "schema_version": 2,
            "mode": "REAL_SOL_CALIBRATION",
            "job_id": job_id,
            "identity": identity.to_dict(),
            "source_original_path": str(source_pdf.resolve()),
            "source_sha256": hashlib.sha256(source_pdf.read_bytes()).hexdigest(),
            "source_page_count": 1,
            "execution_namespace": "fixture",
            "state": state,
            "history": history,
            "live_request_attempts": attempts,
            "review_status": None,
            "last_error": {
                "type": "ReadingUncertainty",
                "message": "material reading uncertainty; no safe grading result",
            },
        }
        (job_dir / "student_record.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if write_grading_result:
            (job_dir / "grading_result.json").write_text(
                json.dumps(
                    self._grading_result(identity).to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        return job_dir

    def _write_validated_job(self, job_id, identity, result_state="valid"):
        job_dir = self.jobs / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "schema_version": 2,
            "mode": "REAL_PDF_BATCH",
            "job_id": job_id,
            "identity": identity.to_dict(),
            "source_original_path": str((job_dir / "source.pdf").resolve()),
            "source_sha256": hashlib.sha256(job_id.encode()).hexdigest(),
            "source_page_count": 1,
            "execution_namespace": "fixture",
            "workbook": str(self.workbook),
            "state": "VALIDATED",
            "history": [
                "NEW",
                "SCANNED",
                "IDENTIFIED",
                "TRANSCRIBED",
                "GRADED",
                "VALIDATED",
            ],
            "live_request_attempts": 1,
            "review_status": "PENDING",
            "last_error": None,
        }
        (job_dir / "student_record.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if result_state != "missing":
            result = self._grading_result(identity).to_dict()
            if result_state == "corrupt":
                result["criteria"] = {"not-a-criterion": {"rating": "bad"}}
            (job_dir / "validated_result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return job_dir

    def test_inspect_projects_pending_approved_duplicate_ids_and_saved_grading(self):
        identity = self._identity()
        pending_store, pending_digest = self._add_workbook_row(
            "audit-job-pending", identity, "PENDING"
        )
        approved_store, approved_digest = self._add_workbook_row(
            "audit-job-approved", identity, "APPROVED"
        )
        self._write_receipt(
            "audit-job-approved", identity, approved_store, approved_digest
        )

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        self.assertEqual(
            [item.submission_id for item in inspection.submissions],
            ["audit-job-pending", "audit-job-approved"],
        )
        pending = self._submission(inspection, "audit-job-pending")
        approved = self._submission(inspection, "audit-job-approved")
        self.assertEqual(pending.review_status, "PENDING")
        self.assertEqual(approved.review_status, "APPROVED")
        self.assertTrue(pending.workbook_valid)
        self.assertTrue(approved.workbook_valid)
        self.assertTrue(pending.grading_available)
        self.assertTrue(approved.grading_available)
        self.assertFalse(pending.rendered)
        self.assertTrue(approved.rendered)
        self.assertEqual(inspection.summary["submissions"], 2)
        self.assertEqual(inspection.summary["awaiting_review"], 1)
        self.assertEqual(inspection.summary["approved"], 1)
        self.assertEqual(inspection.summary["grading_results_available"], 2)

        gates = [stage for stage in inspection.stages if stage.human_gate]
        self.assertTrue(gates)
        self.assertTrue(any("review" in stage.key.lower() for stage in gates))
        actions = {item.action: item for item in inspection.available_actions}
        self.assertIn(Action.REFRESH_REVIEW_STATUS, actions)
        self.assertTrue(actions[Action.REFRESH_REVIEW_STATUS].execution_wired)
        for item in inspection.available_actions:
            if item.action != Action.REFRESH_REVIEW_STATUS:
                self.assertFalse(item.execution_wired)

    def test_pending_review_is_not_an_attention_error(self):
        identity = self._identity("017", "待审学生")
        self._add_workbook_row("pending-only", identity, "PENDING")
        inspection = self._read_only_controller_call(
            "inspect", self._source(workbook=self.workbook)
        )
        pending = self._submission(inspection, "pending-only")
        self.assertEqual(pending.review_status, "PENDING")
        self.assertFalse(pending.attention)
        self.assertFalse(inspection.attention)
        self.assertEqual(inspection.summary["blocking_errors"], 0)

    def test_missing_mismatched_receipts_and_artifacts_need_attention(self):
        cases = (
            ("missing-receipt", "missing receipt"),
            ("missing-artifact", "missing artifact"),
            ("mismatched-receipt", "mismatched receipt"),
        )
        records = {}
        for index, (job_id, _) in enumerate(cases, 1):
            identity = self._identity(str(20 + index), f"学生{index}")
            store, digest = self._add_workbook_row(job_id, identity, "APPROVED")
            records[job_id] = (identity, store, digest)

        missing_receipt_identity, missing_store, _ = records["missing-receipt"]
        artifact = self.receipts / "missing-receipt" / "output" / "student_card.png"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (11, 7), (245, 245, 245)).save(artifact, format="PNG")

        missing_artifact_identity, missing_artifact_store, missing_artifact_digest = records[
            "missing-artifact"
        ]
        self._write_receipt(
            "missing-artifact",
            missing_artifact_identity,
            missing_artifact_store,
            missing_artifact_digest,
            make_artifact=False,
        )

        mismatch_identity, mismatch_store, mismatch_digest = records["mismatched-receipt"]
        self._write_receipt(
            "mismatched-receipt",
            mismatch_identity,
            mismatch_store,
            mismatch_digest,
            mismatched=True,
        )

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        for job_id, expected in cases:
            state = self._submission(inspection, job_id)
            self.assertFalse(state.rendered)
            self.assertTrue(state.attention)
            text = self._attention_text(inspection, state)
            self.assertTrue(
                "receipt" in text or "artifact" in text,
                f"{job_id} attention did not mention receipt/artifact: {text}",
            )
            if "mismatch" in expected:
                self.assertIn("mismatch", text)

    def test_malformed_audit_mapping_formulas_and_approvals_become_attention(self):
        scenarios = ("duplicate-audit", "bad-mapping", "formula", "invalid-approval")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                path = self.root / f"{scenario}.xlsx"
                identity = self._identity("3", "异常数据学生")
                store, digest = self._add_workbook_row(
                    f"malformed-{scenario}", identity, "PENDING", path
                )
                book = load_workbook(path)
                try:
                    audit = book[AUDIT_SHEET]
                    sheet = book[SHEET]
                    if scenario == "duplicate-audit":
                        audit.append(
                            [
                                f"malformed-{scenario}",
                                identity.class_name,
                                identity.student_id,
                                2,
                                digest,
                                "VALIDATED",
                            ]
                        )
                    elif scenario == "bad-mapping":
                        audit["D2"] = "not-an-excel-row"
                    elif scenario == "formula":
                        sheet["H2"] = "=1+1"
                    else:
                        sheet["Y2"] = "MAYBE"
                    book.save(path)
                finally:
                    book.close()

                inspection = self._read_only_controller_call(
                    "inspect", self._source(workbook=path)
                )
                all_attention = list(inspection.attention)
                all_attention.extend(
                    attention
                    for submission in inspection.submissions
                    for attention in submission.attention
                )
                self.assertTrue(all_attention)
                attention_text = self._attention_text(inspection)
                self.assertTrue(
                    any(
                        word in attention_text
                        for word in ("duplicate", "mapping", "row", "formula", "approval", "status")
                    ),
                    attention_text,
                )

    def test_validated_checkpoint_requires_present_validated_result(self):
        cases = (
            ("validated-good", "valid", True),
            ("validated-missing", "missing", False),
            ("validated-corrupt", "corrupt", False),
        )
        for index, (job_id, result_state, grading_available) in enumerate(cases, 50):
            identity = self._identity(str(index), f"已验证学生{index}")
            self._write_validated_job(job_id, identity, result_state)

        inspection = self._read_only_controller_call(
            "inspect", self._source(job_roots=(self.jobs,))
        )
        for job_id, result_state, grading_available in cases:
            state = self._submission(inspection, job_id)
            self.assertEqual(state.checkpoint_state, "VALIDATED")
            self.assertEqual(state.grading_available, grading_available)
            if result_state == "valid":
                text = self._attention_text(inspection, state)
                self.assertNotIn("grading_artifact_invalid", text)
                self.assertNotIn("grading_artifact_missing", text)
                self.assertNotIn(
                    Action.RUN_MARKING,
                    {item.action for item in inspection.available_actions},
                )
            else:
                self.assertTrue(state.attention)
                text = self._attention_text(inspection, state)
                self.assertTrue(
                    any(word in text for word in ("validated", "grading", "result", "missing", "invalid")),
                    text,
                )

    def test_receipt_with_same_job_id_but_wrong_workbook_is_not_rendered(self):
        identity = self._identity("044", "来源错配学生")
        store, digest = self._add_workbook_row("same-job-wrong-workbook", identity, "APPROVED")
        receipt_path, _ = self._write_receipt(
            "same-job-wrong-workbook", identity, store, digest
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["source"]["workbook"] = str((self.root / "other-results.xlsx").resolve())
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        state = self._submission(inspection, "same-job-wrong-workbook")
        self.assertFalse(state.rendered)
        self.assertTrue(state.attention)
        text = self._attention_text(inspection, state)
        self.assertTrue("workbook" in text or "source" in text or "mismatch" in text)

    def test_stale_approved_workbook_text_invalidates_existing_receipt(self):
        identity = self._identity("045", "旧评语学生")
        store, digest = self._add_workbook_row("stale-text", identity, "APPROVED")
        self._write_receipt("stale-text", identity, store, digest)
        book = load_workbook(self.workbook)
        try:
            book[SHEET]["X2"] = "教师后来修改的文字。"
            book.save(self.workbook)
        finally:
            book.close()

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        state = self._submission(inspection, "stale-text")
        self.assertFalse(state.rendered)
        self.assertTrue(state.attention)
        text = self._attention_text(inspection, state)
        self.assertTrue(any(word in text for word in ("stale", "mismatch", "receipt", "text")), text)

    def test_png_hash_mismatch_is_attention_even_when_receipt_values_match(self):
        identity = self._identity("046", "图片错配学生")
        store, digest = self._add_workbook_row("png-hash-mismatch", identity, "APPROVED")
        receipt_path, _ = self._write_receipt(
            "png-hash-mismatch", identity, store, digest
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["output"]["sha256"] = "f" * 64
        receipt_path.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        state = self._submission(inspection, "png-hash-mismatch")
        self.assertFalse(state.rendered)
        self.assertTrue(state.attention)
        text = self._attention_text(inspection, state)
        self.assertTrue(any(word in text for word in ("sha", "hash", "artifact", "png")), text)

    def test_inspection_and_refresh_do_not_mutate_any_fixture_artifact(self):
        identity = self._identity("040", "只读学生")
        store, digest = self._add_workbook_row("readonly-job", identity, "APPROVED")
        self._write_receipt("readonly-job", identity, store, digest)
        checkpoint = self.jobs / "readonly-job"
        checkpoint.mkdir(parents=True)
        (checkpoint / "student_record.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mode": "MOCK",
                    "job_id": "readonly-job",
                    "identity": identity.to_dict(),
                    "input_digest": digest,
                    "workbook": str(self.workbook),
                    "state": "APPROVED",
                    "history": [
                        "NEW",
                        "SCANNED",
                        "IDENTIFIED",
                        "TRANSCRIBED",
                        "GRADED",
                        "VALIDATED",
                        "REVIEWED",
                        "APPROVED",
                    ],
                    "last_error": None,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        source = self._source(
            workbook=self.workbook,
            job_roots=(self.jobs,),
            receipt_roots=(self.receipts,),
        )
        before = self._tree_snapshot(self.root)
        inspection = self._read_only_controller_call("inspect", source)
        refreshed = self._read_only_controller_call("refresh_review_status", source)
        after = self._tree_snapshot(self.root)
        self.assertTrue(inspection.submissions)
        self.assertTrue(refreshed.submissions)
        self.assertEqual(before, after)

    def test_uncertain_attempt_never_offers_run_marking(self):
        identity = self._identity("041", "不确定学生")
        split, roster, decisions, source_pdf = self._write_split_source(identity)
        self._write_checkpoint(identity, source_pdf)
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                job_roots=(self.jobs,),
                split_pile=split,
                roster=roster,
                identity_decisions=decisions,
            ),
        )
        self.assertEqual(len(inspection.submissions), 1)
        state = inspection.submissions[0]
        self.assertTrue(state.identity_confirmed)
        self.assertNotIn(
            Action.RUN_MARKING,
            {item.action for item in inspection.available_actions},
        )
        self.assertIn("uncertain", self._attention_text(inspection, state))
        self.assertIn("attempt", self._attention_text(inspection, state))

    def test_uncertain_graded_attempt_never_offers_run_marking(self):
        identity = self._identity("047", "不确定已评分学生")
        split, roster, decisions, source_pdf = self._write_split_source(identity)
        self._write_checkpoint(
            identity,
            source_pdf,
            state="GRADED",
            attempts=1,
            write_grading_result=True,
        )
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                job_roots=(self.jobs,),
                split_pile=split,
                roster=roster,
                identity_decisions=decisions,
            ),
        )
        self.assertNotIn(
            Action.RUN_MARKING,
            {item.action for item in inspection.available_actions},
        )
        self.assertIn("uncertain", self._attention_text(inspection))
        self.assertIn("attempt", self._attention_text(inspection))

    def test_failed_model_attempt_is_one_recoverable_teacher_issue(self):
        identity = self._identity("054", "模型失败学生")
        split, roster, decisions, source_pdf = self._write_split_source(identity)
        parent = self._write_checkpoint(
            identity, source_pdf, job_id="recoverable-parent", attempts=0
        )
        (parent / "source.pdf").write_bytes(source_pdf.read_bytes())
        parent_record = json.loads((parent / "student_record.json").read_text(encoding="utf-8"))
        parent_record["mode"] = "REAL_PDF_BATCH"
        parent_record["last_error"] = {
            "type": "CodexInvocationError",
            "message": "model call failed without a response",
        }
        (parent / "student_record.json").write_text(
            json.dumps(parent_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        child = self.root / "calibration-recoverable"
        child.mkdir()
        child_record = dict(parent_record)
        child_record.update({
            "mode": "REAL_SOL_CALIBRATION",
            "job_id": "calibration-recoverable",
            "live_request_attempts": 2,
            "last_error": parent_record["last_error"],
        })
        (child / "student_record.json").write_text(
            json.dumps(child_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (child / "validation_report.json").write_text(json.dumps({
            "status": "MODEL_CALL_FAILED",
            "model_request_attempted": True,
            "error": parent_record["last_error"],
        }), encoding="utf-8")
        (parent / "real_grading_bridge.json").write_text(json.dumps({
            "calibration_job": str(child.resolve()),
            "execution_namespace": "fixture",
            "status": "IN_PROGRESS",
        }), encoding="utf-8")

        inspection = self._read_only_controller_call(
            "inspect", self._source(job_roots=(self.jobs,))
        )
        state = self._submission(inspection, "recoverable-parent")
        self.assertTrue(state.retryable)
        self.assertEqual([item.code for item in state.attention], ["MARKING_RETRY_AVAILABLE"])
        self.assertEqual(inspection.summary["retryable_failures"], 1)
        self.assertEqual(inspection.summary["submissions_needing_attention"], 1)
        self.assertEqual(inspection.summary["blocking_errors"], 0)
        self.assertIn(Action.RUN_MARKING, {item.action for item in inspection.available_actions})

    def test_interrupted_calibration_checkpoint_is_recoverable(self):
        identity = self._identity("055", "中断学生")
        split, roster, decisions, source_pdf = self._write_split_source(identity)
        parent = self._write_checkpoint(
            identity, source_pdf, job_id="interrupted-parent", attempts=0
        )
        (parent / "source.pdf").write_bytes(source_pdf.read_bytes())
        child = self.root / "calibration-interrupted"
        child.mkdir()
        child_record = json.loads((parent / "student_record.json").read_text(encoding="utf-8"))
        child_record.update({
            "mode": "REAL_SOL_CALIBRATION",
            "job_id": "calibration-interrupted",
            "live_request_attempts": 1,
            "last_error": None,
        })
        (child / "student_record.json").write_text(
            json.dumps(child_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (parent / "real_grading_bridge.json").write_text(json.dumps({
            "calibration_job": str(child.resolve()),
            "execution_namespace": "fixture",
            "status": "IN_PROGRESS",
        }), encoding="utf-8")

        inspection = self._read_only_controller_call(
            "inspect", self._source(job_roots=(self.jobs,))
        )
        state = self._submission(inspection, "interrupted-parent")
        self.assertTrue(state.retryable)
        self.assertEqual([item.code for item in state.attention], ["MARKING_RETRY_AVAILABLE"])

    def test_fresh_confirmed_source_offers_only_safe_unwired_run(self):
        identity = self._identity("042", "新鲜学生")
        split, roster, decisions, _ = self._write_split_source(identity)
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                split_pile=split,
                roster=roster,
                identity_decisions=decisions,
            ),
        )
        self.assertEqual(len(inspection.submissions), 1)
        state = inspection.submissions[0]
        self.assertTrue(state.identity_confirmed)
        run_actions = [
            item
            for item in inspection.available_actions
            if item.action == Action.RUN_MARKING
        ]
        self.assertEqual(len(run_actions), 1)
        self.assertIn(state.submission_id, run_actions[0].submission_ids)
        self.assertTrue(run_actions[0].execution_wired)

    def test_unresolved_split_source_requires_confirmation_and_cannot_run(self):
        identity = self._identity("048", "待确认学生")
        split, roster, decisions, _ = self._write_split_source(
            identity, match_status="CONFIRMATION_REQUIRED"
        )
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                split_pile=split,
                roster=roster,
                identity_decisions=decisions,
            ),
        )
        state = inspection.submissions[0]
        self.assertFalse(state.identity_confirmed)
        self.assertNotIn(
            Action.RUN_MARKING,
            {item.action for item in inspection.available_actions},
        )
        confirmation_actions = [
            item
            for item in inspection.available_actions
            if item.action == Action.CONFIRM_SUBMISSIONS
        ]
        self.assertEqual(len(confirmation_actions), 1)
        self.assertEqual(confirmation_actions[0].submission_ids, (state.submission_id,))

    def test_declared_missing_roots_are_attention_not_silent_discovery(self):
        identity = self._identity("049", "根目录学生")
        self._add_workbook_row("missing-root-row", identity, "PENDING")
        missing_jobs = self.root / "declared-missing-jobs"
        missing_receipts = self.root / "declared-missing-receipts"
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                workbook=self.workbook,
                job_roots=(missing_jobs,),
                receipt_roots=(missing_receipts,),
            ),
        )
        text = self._attention_text(inspection)
        self.assertTrue(inspection.attention or any(item.attention for item in inspection.submissions))
        self.assertTrue("missing" in text or "root" in text or "directory" in text, text)

    def test_bad_receipt_does_not_block_another_approved_row_from_being_ready(self):
        bad_identity = self._identity("050", "坏卡学生")
        ready_identity = self._identity("051", "可渲染学生")
        bad_store, bad_digest = self._add_workbook_row(
            "bad-card", bad_identity, "APPROVED"
        )
        self._write_receipt(
            "bad-card", bad_identity, bad_store, bad_digest, mismatched=True
        )
        self._add_workbook_row("ready-approved", ready_identity, "APPROVED")

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        ready = self._submission(inspection, "ready-approved")
        self.assertTrue(ready.workbook_valid)
        self.assertTrue(ready.ready_to_render)
        self.assertFalse(ready.attention)
        actions = {item.action: item for item in inspection.available_actions}
        self.assertEqual(actions[Action.RENDER_APPROVED].submission_ids, ("ready-approved",))

    def test_linked_calibration_child_projects_as_one_parent_submission(self):
        identity = self._identity("052", "同源学生")
        split, _, _, source_pdf = self._write_split_source(identity)
        parent = self._write_checkpoint(
            identity,
            source_pdf,
            job_id="production-parent",
            state="VALIDATED",
            attempts=0,
            write_grading_result=True,
        )
        child = self._write_checkpoint(
            identity,
            source_pdf,
            job_id="calibration-child",
            state="VALIDATED",
            attempts=0,
            write_grading_result=True,
        )
        (parent / "real_grading_bridge.json").write_text(
            json.dumps({"calibration_job": str(child.resolve())}, indent=2),
            encoding="utf-8",
        )

        inspection = self._read_only_controller_call(
            "inspect", self._source(job_roots=(self.jobs,), split_pile=split)
        )
        self.assertEqual(
            [item.submission_id for item in inspection.submissions],
            ["production-parent"],
        )
        evidence = self._submission(inspection, "production-parent").evidence
        self.assertIn(str(parent / "student_record.json"), evidence)
        self.assertIn(str(child / "student_record.json"), evidence)

    def test_current_confirmation_required_suppresses_run_after_confirmed_checkpoint(self):
        identity = self._identity("053", "需重新确认学生")
        split, roster, decisions, source_pdf = self._write_split_source(
            identity, match_status="CONFIRMATION_REQUIRED"
        )
        job_dir = self._write_checkpoint(
            identity,
            source_pdf,
            job_id="confirmed-before",
            state="IDENTIFIED",
            attempts=0,
        )
        (job_dir / "source.pdf").write_bytes(source_pdf.read_bytes())
        checkpoint_path = job_dir / "student_record.json"
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        checkpoint["last_error"] = None
        checkpoint_path.write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        inspection = self._read_only_controller_call(
            "inspect",
            self._source(
                job_roots=(self.jobs,),
                split_pile=split,
                roster=roster,
                identity_decisions=decisions,
            ),
        )
        state = self._submission(inspection, "confirmed-before")
        self.assertFalse(state.identity_confirmed)
        self.assertNotIn(
            Action.RUN_MARKING,
            {item.action for item in inspection.available_actions},
        )
        self.assertIn("identity_unresolved", self._attention_text(inspection, state))

    def test_next_actions_have_exact_review_render_view_targets(self):
        review_identity = self._identity("060", "待复核学生")
        render_identity = self._identity("061", "待渲染学生")
        view_identity = self._identity("062", "已渲染学生")
        self._add_workbook_row("next-review", review_identity, "PENDING")
        render_store, render_digest = self._add_workbook_row(
            "next-render", render_identity, "APPROVED"
        )
        view_store, view_digest = self._add_workbook_row(
            "next-view", view_identity, "APPROVED"
        )
        self._write_receipt("next-view", view_identity, view_store, view_digest)
        inspection = self._read_only_controller_call(
            "inspect",
            self._source(workbook=self.workbook, receipt_roots=(self.receipts,)),
        )
        actions = {item.action: item for item in inspection.available_actions}
        self.assertIn(Action.REVIEW_EXCEL, actions)
        self.assertIn(Action.RENDER_APPROVED, actions)
        self.assertIn(Action.VIEW_OUTPUTS, actions)
        self.assertEqual(set(actions[Action.REVIEW_EXCEL].submission_ids), {"next-review"})
        self.assertEqual(set(actions[Action.RENDER_APPROVED].submission_ids), {"next-render"})
        self.assertEqual(set(actions[Action.VIEW_OUTPUTS].submission_ids), {"next-view"})
        self.assertFalse(self._submission(inspection, "next-review").ready_to_render)
        self.assertTrue(self._submission(inspection, "next-render").ready_to_render)
        self.assertTrue(self._submission(inspection, "next-view").rendered)
        self.assertFalse(actions[Action.REVIEW_EXCEL].execution_wired)
        self.assertTrue(actions[Action.RENDER_APPROVED].execution_wired)
        self.assertFalse(actions[Action.VIEW_OUTPUTS].execution_wired)

    def test_refresh_reflects_external_saved_workbook_changes(self):
        identity = self._identity("043", "外部修改学生")
        store, _ = self._add_workbook_row("refresh-job", identity, "PENDING")
        source = self._source(workbook=self.workbook)
        first = self._read_only_controller_call("inspect", source)
        self.assertEqual(self._submission(first, "refresh-job").review_status, "PENDING")

        store.set_status("refresh-job", identity, "APPROVED", "APPROVED")
        refreshed = self._read_only_controller_call("refresh_review_status", source)
        state = self._submission(refreshed, "refresh-job")
        self.assertEqual(state.review_status, "APPROVED")
        self.assertTrue(state.grading_available)
        refresh_actions = [
            item
            for item in refreshed.available_actions
            if item.action == Action.REFRESH_REVIEW_STATUS
        ]
        self.assertEqual(len(refresh_actions), 1)
        self.assertTrue(refresh_actions[0].execution_wired)

    def test_controller_keeps_non_execution_actions_outside_the_wired_boundary(self):
        source = self._source(workbook=self.workbook)
        for action in (Action.PREPARE_SUBMISSIONS, Action.CONFIRM_SUBMISSIONS,
                       Action.REVIEW_EXCEL, Action.REFRESH_REVIEW_STATUS,
                       Action.VIEW_OUTPUTS,
                       Action.RESOLVE_ATTENTION, "unknown", None):
            with self.subTest(action=action):
                with self.assertRaises(NotImplementedError):
                    self.controller.execute(action, source)
        with self.assertRaises(ValidationError):
            self.controller.execute(Action.RUN_MARKING, source)
        with self.assertRaises(ValidationError):
            self.controller.execute(Action.RENDER_APPROVED, source)


if __name__ == "__main__":
    unittest.main()
