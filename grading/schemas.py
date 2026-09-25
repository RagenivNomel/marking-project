"""Strict JSON contract. Validation never trims or rewrites feedback."""
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import json
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ("审题扣题", "情节紧凑", "重点突出", "详略得当", "情景交融", "多感官", "修辞运用", "结尾照应／升华")


class Rating(str, Enum):
    DID_WELL = "做得很好"
    CAN_GO_FURTHER = "可以更进一步"
    NEEDS_STRENGTHENING = "待加强"


RATINGS = tuple(rating.value for rating in Rating)


class ValidationError(ValueError):
    pass


def exact_keys(value: Any, keys, label: str):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValidationError(f"{label}: expected exactly {list(keys)}")


def required_text(value, label, maximum=None):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label}: nonempty text required")
    if any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ValidationError(f"{label}: invalid control character")
    if maximum is not None and len(value) > maximum:
        raise ValidationError(f"{label}: {len(value)} characters exceeds {maximum}")
    return value


@dataclass(frozen=True)
class Identity:
    student_id: str
    student_name: str
    class_name: str

    @classmethod
    def from_dict(cls, data):
        exact_keys(data, ("student_id", "student_name", "class_name"), "identity")
        for key, value in data.items():
            required_text(value, key, 100)
        return cls(**data)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class CriterionResult:
    rating: str
    short_comment: str


@dataclass(frozen=True)
class GradingResult:
    student_id: str
    student_name: str
    class_name: str
    criteria: dict[str, CriterionResult]
    teacher_comment: str

    def to_dict(self):
        return asdict(self)


class Validator:
    def __init__(self, config_dir=ROOT / "config"):
        config_dir = Path(config_dir)
        contract = json.loads((config_dir / "criteria.json").read_text(encoding="utf-8"))
        if contract != {"criteria": list(CRITERIA), "ratings": list(RATINGS)}:
            raise ValidationError("Criteria and rating vocabulary must match the fixed contract")
        self.limits = json.loads((config_dir / "text_limits.json").read_text(encoding="utf-8"))
        exact_keys(self.limits, ("criterion_comment", "teacher_comment"), "limits")
        for label, limits in self.limits.items():
            exact_keys(limits, ("preferred_min", "preferred_max", "hard_max"), label)
            if (any(type(n) is not int or n <= 0 for n in limits.values())
                    or not limits["preferred_min"] <= limits["preferred_max"] <= limits["hard_max"]):
                raise ValidationError(f"{label}: invalid text limits")

    def validate(self, data, identity: Identity) -> GradingResult:
        exact_keys(data, ("student_id", "student_name", "class_name", "criteria", "teacher_comment"), "grading result")
        actual = Identity.from_dict({key: data[key] for key in identity.to_dict()})
        if actual != identity:
            raise ValidationError("Grading identity does not match this job")
        exact_keys(data["criteria"], CRITERIA, "criteria")
        criteria = {}
        for name in CRITERIA:
            item = data["criteria"][name]
            exact_keys(item, ("rating", "short_comment"), name)
            if item["rating"] not in RATINGS:
                raise ValidationError(f"{name}: invalid rating {item['rating']!r}")
            required_text(item["short_comment"], name, self.limits["criterion_comment"]["hard_max"])
            criteria[name] = CriterionResult(**item)
        required_text(data["teacher_comment"], "teacher_comment", self.limits["teacher_comment"]["hard_max"])
        return GradingResult(**{**data, "criteria": criteria})
