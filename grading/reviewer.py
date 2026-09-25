from typing import Protocol
from .schemas import GradingResult


class Reviewer(Protocol):
    def review(self, result: GradingResult) -> bool: ...


class MockReviewer:
    """Test-only approval; must be replaced by teacher review in production."""
    def review(self, result: GradingResult) -> bool:
        return True
