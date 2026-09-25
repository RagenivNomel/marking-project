"""Closed-set identity seam; Phase 1 uses explicit roster confirmation only."""
from dataclasses import dataclass
from typing import Protocol
from grading.schemas import Identity, ValidationError


@dataclass(frozen=True)
class IdentityCandidate:
    student_id: str
    confidence: float


class IdentityResolver(Protocol):
    def propose(self, name_crop: bytes, roster: tuple[Identity, ...]) -> IdentityCandidate: ...


def confirm_identity(roster, class_name, student_id):
    matches = [student for student in roster if student.class_name == class_name and student.student_id == student_id]
    if len(matches) != 1:
        raise ValidationError("Identity must match exactly one roster entry; human confirmation required")
    return matches[0]
