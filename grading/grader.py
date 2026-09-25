"""Providers receive only one student's immutable input; no workflow or paths."""
from dataclasses import dataclass
from typing import Protocol
from .schemas import Identity


@dataclass(frozen=True)
class GradingInput:
    identity: Identity
    essay: str


class Grader(Protocol):
    def grade(self, request: GradingInput) -> dict: ...
