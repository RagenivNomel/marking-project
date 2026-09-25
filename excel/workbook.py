"""Batch-friendly Excel repository; approved wording is read back verbatim."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import math
import os
import shutil
import tempfile
import threading

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

from grading.schemas import CRITERIA, RATINGS, CriterionResult, Identity, ValidationError
from .schema import AUDIT_HEADERS, AUDIT_SHEET, HEADERS, SHEET


APPROVAL_STATUSES = ("PENDING", "APPROVED")
APPROVAL_VALIDATION_RANGE = "Y2:Y1048576"

_WORKBOOK_LOCKS = {}
_WORKBOOK_LOCKS_GUARD = threading.Lock()


def _workbook_lock(path):
    key = str(Path(path).resolve()).casefold()
    with _WORKBOOK_LOCKS_GUARD:
        return _WORKBOOK_LOCKS.setdefault(key, threading.RLock())


def roster_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() if value is not None else ""


def read_roster(path, sheet_name="作文诊断输入"):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = book[sheet_name]
        rows = sheet.iter_rows(values_only=True)
        headers = next(rows)
        name_col = "学生姓名" if "学生姓名" in headers else "姓名"
        indices = [headers.index(key) for key in ("班号", name_col, "班级")]
        result, seen = [], set()
        for row in rows:
            values = [roster_text(row[i]) if i < len(row) else "" for i in indices]
            if not any(values):
                continue
            identity = Identity.from_dict(dict(zip(("student_id", "student_name", "class_name"), values)))
            key = (identity.class_name, identity.student_id)
            if key in seen:
                raise ValidationError(f"Duplicate roster identity: {key}")
            seen.add(key)
            result.append(identity)
        return result
    finally:
        book.close()


@dataclass(frozen=True)
class ExcelStudentRecord:
    student_id: str
    student_name: str
    class_name: str
    topic: str
    content_score: float | None
    language_structure_score: float | None
    total_score: float | None
    criteria: dict[str, CriterionResult]
    teacher_comment: str
    review_status: str

    def to_dict(self):
        return asdict(self)


class ExcelStore:
    def __init__(self, path, validator, *, backup_dir=None):
        self.path = Path(path)
        self.validator = validator
        self.backup_dir = Path(backup_dir) if backup_dir is not None else None
        # Separate stores targeting the same authoritative workbook share the
        # complete read/modify/save critical section.
        self._write_lock = _workbook_lock(self.path)

    def _open(self):
        if self.path.exists():
            book = load_workbook(self.path)
            valid = (SHEET in book.sheetnames and AUDIT_SHEET in book.sheetnames
                     and [c.value for c in book[SHEET][1]] == HEADERS
                     and [c.value for c in book[AUDIT_SHEET][1]] == AUDIT_HEADERS)
            if not valid:
                book.close()
                raise ValidationError("Unexpected results workbook schema")
            self._ensure_approval_validation(book[SHEET])
            return book
        book = Workbook()
        sheet = book.active
        sheet.title = SHEET
        sheet.append(HEADERS)
        sheet.freeze_panes = "H2"
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="285E61")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.row_dimensions[1].height = 42
        for index, header in enumerate(HEADERS, 1):
            wide = header.endswith("评语") or header == "教师总评" or header == "题目"
            sheet.column_dimensions[get_column_letter(index)].width = 34 if wide else 16
        for index in range(8, 24, 2):
            validation = DataValidation(type="list", formula1='"' + ','.join(RATINGS) + '"')
            validation.errorTitle = "等级无效"
            validation.error = "请选择指定的三个等级之一。"
            validation.showErrorMessage = True
            validation.errorStyle = "stop"
            sheet.add_data_validation(validation)
            validation.add(f"{get_column_letter(index)}2:{get_column_letter(index)}1048576")
        self._ensure_approval_validation(sheet)
        audit = book.create_sheet(AUDIT_SHEET)
        audit.append(AUDIT_HEADERS)
        audit.sheet_state = "hidden"
        return book

    @staticmethod
    def _ensure_approval_validation(sheet):
        formula = '"' + ','.join(APPROVAL_STATUSES) + '"'
        for validation in sheet.data_validations.dataValidation:
            if (validation.type == "list" and validation.formula1 == formula
                    and str(validation.sqref) == APPROVAL_VALIDATION_RANGE):
                return
        validation = DataValidation(type="list", formula1=formula, allow_blank=False)
        validation.errorTitle = "审核状态无效"
        validation.error = "请选择 PENDING 或 APPROVED。"
        validation.showErrorMessage = True
        validation.errorStyle = "stop"
        sheet.add_data_validation(validation)
        validation.add(APPROVAL_VALIDATION_RANGE)

    def ensure_validation_rules(self):
        """Persist current production validation rules without changing cell values."""
        with self._write_lock:
            return self._ensure_validation_rules_unlocked()

    def _ensure_validation_rules_unlocked(self):
        if not self.path.exists():
            raise ValidationError("Results workbook does not exist")
        book = self._open()
        try:
            self._save(book)
        finally:
            book.close()

    def _save(self, book):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, suffix=".xlsx")
        os.close(fd)
        try:
            book.save(temporary)
            if self.path.exists():
                backups = self.backup_dir or (self.path.parent / "backups")
                backups.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
                shutil.copy2(self.path, backups / f"{self.path.stem}-{stamp}.xlsx")
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    @staticmethod
    def _row(book, job_id):
        matches = [row for row in book[AUDIT_SHEET].iter_rows(min_row=2) if row[0].value == job_id]
        if len(matches) > 1:
            raise ValidationError("Duplicate job rows in Excel audit sheet")
        if not matches:
            return None, None
        row_number = matches[0][3].value
        if type(row_number) is not int or row_number < 2:
            raise ValidationError("Invalid Excel row reference in audit sheet")
        return book[SHEET][row_number], matches[0]

    @staticmethod
    def _score(value, label):
        if value is None or value == "":
            return None
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValidationError(f"{label}: blank or finite nonnegative number required")
        return value

    def ensure_draft(self, result, identity, job_id, digest, topic="", teacher_scores=None):
        result = self.validator.validate(result.to_dict(), identity)
        if not isinstance(topic, str):
            raise ValidationError("题目 must be text")
        teacher_scores = {} if teacher_scores is None else teacher_scores
        score_keys = {"content_score", "language_structure_score", "total_score"}
        if not isinstance(teacher_scores, dict) or not set(teacher_scores).issubset(score_keys):
            raise ValidationError("teacher_scores: unexpected score field")
        content_score = self._score(teacher_scores.get("content_score"), "内容分")
        language_structure_score = self._score(teacher_scores.get("language_structure_score"), "语文与结构分")
        total_score = self._score(teacher_scores.get("total_score"), "总分")
        with self._write_lock:
            return self._ensure_draft_unlocked(
                result, identity, job_id, digest, topic,
                content_score, language_structure_score, total_score,
            )

    def _ensure_draft_unlocked(self, result, identity, job_id, digest, topic,
                               content_score, language_structure_score, total_score):
        book = self._open()
        try:
            sheet = book[SHEET]
            existing, audit_row = self._row(book, job_id)
            if existing:
                if audit_row[4].value != digest:
                    raise ValidationError("Existing Excel row belongs to different input")
                self._decode(existing, identity)
                return
            values = [result.class_name, result.student_id, result.student_name, topic,
                      content_score, language_structure_score, total_score]
            for name in CRITERIA:
                values += [result.criteria[name].rating, result.criteria[name].short_comment]
            values += [result.teacher_comment, "PENDING"]
            row_index = sheet.max_row + 1
            for col, value in enumerate(values, 1):
                cell = sheet.cell(row_index, col, value)
                if isinstance(value, str):
                    cell.data_type = "s"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            sheet.row_dimensions[row_index].height = 120
            sheet.auto_filter.ref = sheet.dimensions
            book[AUDIT_SHEET].append([job_id, identity.class_name, identity.student_id, row_index, digest, "VALIDATED"])
            self._save(book)
        finally:
            book.close()

    def _decode(self, row, identity):
        if any(cell.data_type == "f" for cell in row):
            raise ValidationError("Result rows require literal approved values, not formulas")
        values = [cell.value for cell in row]
        grading = dict(
            class_name=roster_text(values[0]), student_id=roster_text(values[1]), student_name=roster_text(values[2]),
            criteria={name: {"rating": values[7 + 2*i], "short_comment": values[8 + 2*i]} for i, name in enumerate(CRITERIA)},
            teacher_comment=values[23],
        )
        validated = self.validator.validate(grading, identity)
        return ExcelStudentRecord(
            validated.student_id, validated.student_name, validated.class_name, values[3] or "",
            self._score(values[4], "内容分"), self._score(values[5], "语文与结构分"), self._score(values[6], "总分"),
            validated.criteria, validated.teacher_comment, values[24],
        )

    def get(self, job_id, identity, approved=False):
        if not self.path.exists():
            raise ValidationError("Results workbook does not exist")
        book = self._open()
        try:
            row, _ = self._row(book, job_id)
            if row is None:
                raise ValidationError("Student result not found")
            record = self._decode(row, identity)
            if approved and record.review_status != "APPROVED":
                raise ValidationError("Student result is not APPROVED in Excel")
            return record
        finally:
            book.close()

    def get_render_source(self, preferred_job_id, identity):
        """Return an approved row and its workbook audit metadata for rendering.

        Normal production rows are addressed by the pipeline job key. A workbook
        imported from an existing calibration job may retain that job ID instead;
        in that case an unambiguous class/student audit match is sufficient. The
        approved Excel row remains the sole feedback source in both cases.
        """
        if not self.path.exists():
            raise ValidationError("Results workbook does not exist")
        book = self._open()
        try:
            audit = book[AUDIT_SHEET]
            preferred = [row for row in audit.iter_rows(min_row=2) if row[0].value == preferred_job_id]
            if len(preferred) > 1:
                raise ValidationError("Duplicate job rows in Excel audit sheet")
            candidates = preferred
            if not candidates:
                candidates = [
                    row for row in audit.iter_rows(min_row=2)
                    if roster_text(row[1].value) == identity.class_name
                    and roster_text(row[2].value) == identity.student_id
                ]
            if len(candidates) != 1:
                raise ValidationError("Approved Excel render source is not uniquely identified")
            audit_row = candidates[0]
            row_number = audit_row[3].value
            if type(row_number) is not int or row_number < 2:
                raise ValidationError("Invalid Excel row reference in audit sheet")
            record = self._decode(book[SHEET][row_number], identity)
            if record.review_status != "APPROVED":
                raise ValidationError("Student result is not APPROVED in Excel")
            digest = audit_row[4].value
            if not isinstance(digest, str) or not digest:
                raise ValidationError("Excel audit input digest is missing")
            return record, {
                "job_id": audit_row[0].value,
                "excel_row": row_number,
                "input_digest": digest,
                "pipeline_status": audit_row[5].value,
            }
        finally:
            book.close()

    def row_number(self, job_id, identity):
        """Return the validated teacher-sheet row for render audit metadata."""
        if not self.path.exists():
            raise ValidationError("Results workbook does not exist")
        book = self._open()
        try:
            row, _ = self._row(book, job_id)
            if row is None:
                raise ValidationError("Student result not found")
            self._decode(row, identity)
            return row[0].row
        finally:
            book.close()

    def set_status(self, job_id, identity, pipeline_status, review_status=None):
        with self._write_lock:
            return self._set_status_unlocked(job_id, identity, pipeline_status, review_status)

    def _set_status_unlocked(self, job_id, identity, pipeline_status, review_status=None):
        book = self._open()
        try:
            row, audit_row = self._row(book, job_id)
            if row is None:
                raise ValidationError("Student result not found")
            self._decode(row, identity)
            if review_status is not None:
                if review_status not in ("PENDING", "APPROVED"):
                    raise ValidationError("Unknown review status")
                row[24].value = review_status
            audit_row[5].value = pipeline_status
            self._save(book)
        finally:
            book.close()
