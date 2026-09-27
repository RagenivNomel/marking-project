"""Structured contract for blind real-essay calibration responses."""
from dataclasses import asdict, dataclass
import re
from typing import Any

from .schemas import CRITERIA, RATINGS, CriterionResult, Identity, ValidationError, exact_keys, required_text

READING_UNCERTAINTY_MAX = 200
EVIDENCE_RATIONALE_MAX = 240
EVIDENCE_JUDGMENTS = CRITERIA + ("教师总评",)
SECTION_SCORE_MAX = 30
SCORE_KEYS = ("content_score", "language_structure_score")
QUESTION_NUMBER_PATTERN = re.compile(r"^Q[1-9][0-9]*$")


@dataclass(frozen=True)
class ReadingUncertainty:
    page_number: int
    description: str


@dataclass(frozen=True)
class ReadingQuality:
    complete_essay_legible: bool
    uncertainties: tuple[ReadingUncertainty, ...]
    materially_affects_grade: bool


@dataclass(frozen=True)
class EvidenceReference:
    judgment: str
    page_numbers: tuple[int, ...]
    rationale: str


@dataclass(frozen=True)
class CalibrationGrade:
    student_id: str
    student_name: str
    class_name: str
    criteria: dict[str, CriterionResult]
    teacher_comment: str


@dataclass(frozen=True)
class CalibrationResponse:
    reading_quality: ReadingQuality
    grading: CalibrationGrade | None
    evidence: tuple[EvidenceReference, ...]
    question_number: str | None = None
    scores: dict[str, int] | None = None

    def to_dict(self):
        return asdict(self)


def response_json_schema(text_limits: dict) -> dict:
    criterion = {
        "type": "object",
        "properties": {
            "rating": {"type": "string", "enum": list(RATINGS)},
            "short_comment": {
                "type": "string", "minLength": 1,
                "maxLength": text_limits["criterion_comment"]["hard_max"],
            },
        },
        "required": ["rating", "short_comment"],
        "additionalProperties": False,
    }
    grading = {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "student_name": {"type": "string"},
            "class_name": {"type": "string"},
            "criteria": {
                "type": "object",
                "properties": {name: criterion for name in CRITERIA},
                "required": list(CRITERIA),
                "additionalProperties": False,
            },
            "teacher_comment": {
                "type": "string", "minLength": 1,
                "maxLength": text_limits["teacher_comment"]["hard_max"],
            },
        },
        "required": ["student_id", "student_name", "class_name", "criteria", "teacher_comment"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "reading_quality": {
                "type": "object",
                "properties": {
                    "complete_essay_legible": {"type": "boolean"},
                    "uncertainties": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "page_number": {"type": "integer", "minimum": 1},
                                "description": {"type": "string", "minLength": 1, "maxLength": READING_UNCERTAINTY_MAX},
                            },
                            "required": ["page_number", "description"],
                            "additionalProperties": False,
                        },
                    },
                    "materially_affects_grade": {"type": "boolean"},
                },
                "required": ["complete_essay_legible", "uncertainties", "materially_affects_grade"],
                "additionalProperties": False,
            },
            "grading": {"anyOf": [grading, {"type": "null"}]},
            "question_number": {"anyOf": [
                {"type": "string", "pattern": QUESTION_NUMBER_PATTERN.pattern}, {"type": "null"},
            ]},
            "scores": {"anyOf": [{
                "type": "object",
                "properties": {key: {"type": "integer", "minimum": 0, "maximum": SECTION_SCORE_MAX} for key in SCORE_KEYS},
                "required": list(SCORE_KEYS),
                "additionalProperties": False,
            }, {"type": "null"}]},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "judgment": {"type": "string", "enum": list(EVIDENCE_JUDGMENTS)},
                        "page_numbers": {"type": "array", "minItems": 1, "items": {"type": "integer", "minimum": 1}},
                        "rationale": {"type": "string", "minLength": 1, "maxLength": EVIDENCE_RATIONALE_MAX},
                    },
                    "required": ["judgment", "page_numbers", "rationale"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["reading_quality", "grading", "question_number", "scores", "evidence"],
        "additionalProperties": False,
    }


class CalibrationValidator:
    def __init__(self, text_limits: dict, page_count: int):
        self.text_limits = text_limits
        self.page_count = page_count

    def _pages(self, values: Any, label: str, allow_empty=False) -> tuple[int, ...]:
        if not isinstance(values, list) or (not allow_empty and not values):
            raise ValidationError(f"{label}: page number list required")
        if any(type(page) is not int or page < 1 or page > self.page_count for page in values):
            raise ValidationError(f"{label}: page number outside 1..{self.page_count}")
        return tuple(values)

    def validate(self, data: Any, identity: Identity) -> CalibrationResponse:
        # Jobs prepared before scores were added keep their older schema snapshot.
        if not isinstance(data, dict) or "scores" in data or "question_number" in data:
            exact_keys(data, ("reading_quality", "grading", "question_number", "scores", "evidence"), "calibration response")
        else:
            exact_keys(data, ("reading_quality", "grading", "evidence"), "calibration response")
        question_number, scores = data.get("question_number"), data.get("scores")
        if question_number is not None and (not isinstance(question_number, str)
                                            or not QUESTION_NUMBER_PATTERN.match(question_number)):
            raise ValidationError(f"question_number: expected Q followed by a number, got {question_number!r}")
        if scores is not None:
            exact_keys(scores, SCORE_KEYS, "scores")
            for key in SCORE_KEYS:
                if type(scores[key]) is not int or not 0 <= scores[key] <= SECTION_SCORE_MAX:
                    raise ValidationError(f"scores.{key}: whole number 0..{SECTION_SCORE_MAX} required")
        reading = data["reading_quality"]
        exact_keys(reading, ("complete_essay_legible", "uncertainties", "materially_affects_grade"), "reading_quality")
        if type(reading["complete_essay_legible"]) is not bool or type(reading["materially_affects_grade"]) is not bool:
            raise ValidationError("reading_quality: boolean fields required")
        if not isinstance(reading["uncertainties"], list):
            raise ValidationError("reading_quality.uncertainties: list required")
        uncertainties = []
        for index, item in enumerate(reading["uncertainties"]):
            exact_keys(item, ("page_number", "description"), f"uncertainty[{index}]")
            pages = self._pages([item["page_number"]], f"uncertainty[{index}]")
            uncertainties.append(ReadingUncertainty(pages[0], required_text(item["description"], f"uncertainty[{index}]", READING_UNCERTAINTY_MAX)))
        quality = ReadingQuality(reading["complete_essay_legible"], tuple(uncertainties), reading["materially_affects_grade"])

        if not isinstance(data["evidence"], list):
            raise ValidationError("evidence: list required")
        evidence = []
        for index, item in enumerate(data["evidence"]):
            exact_keys(item, ("judgment", "page_numbers", "rationale"), f"evidence[{index}]")
            if item["judgment"] not in EVIDENCE_JUDGMENTS:
                raise ValidationError(f"evidence[{index}]: unknown judgment")
            pages = self._pages(item["page_numbers"], f"evidence[{index}]")
            evidence.append(EvidenceReference(item["judgment"], pages, required_text(item["rationale"], f"evidence[{index}]", EVIDENCE_RATIONALE_MAX)))

        if quality.materially_affects_grade:
            if data["grading"] is not None:
                raise ValidationError("Materially unreadable essay must not contain fabricated grading")
            if scores is not None:
                raise ValidationError("Materially unreadable essay must not contain fabricated scores")
            return CalibrationResponse(quality, None, tuple(evidence), question_number)

        grading = data["grading"]
        if grading is None:
            raise ValidationError("Assessable essay requires a complete grading result")
        exact_keys(grading, ("student_id", "student_name", "class_name", "criteria", "teacher_comment"), "grading")
        actual = Identity.from_dict({key: grading[key] for key in identity.to_dict()})
        if actual != identity:
            raise ValidationError("Grading identity does not match this calibration job")
        exact_keys(grading["criteria"], CRITERIA, "criteria")
        criteria = {}
        for name in CRITERIA:
            item = grading["criteria"][name]
            exact_keys(item, ("rating", "short_comment"), name)
            if item["rating"] not in RATINGS:
                raise ValidationError(f"{name}: invalid rating {item['rating']!r}")
            criteria[name] = CriterionResult(item["rating"], required_text(item["short_comment"], name, self.text_limits["criterion_comment"]["hard_max"]))
        teacher_comment = required_text(grading["teacher_comment"], "teacher_comment", self.text_limits["teacher_comment"]["hard_max"])
        if not evidence:
            raise ValidationError("Assessable essay requires evidence with page references")
        if "scores" in data and scores is None:
            raise ValidationError("Assessable essay requires content_score and language_structure_score")
        grade = CalibrationGrade(actual.student_id, actual.student_name, actual.class_name, criteria, teacher_comment)
        return CalibrationResponse(quality, grade, tuple(evidence), question_number, scores)
