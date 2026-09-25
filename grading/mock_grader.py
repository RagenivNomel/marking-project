from .grader import GradingInput
from .schemas import CRITERIA


class MockGrader:
    """No network or model. Instantiate a new provider for each student."""
    def __init__(self, failure=None):
        if failure not in (None, "invalid-rating", "long-comment"):
            raise ValueError("Unknown mock failure")
        self.failure = failure

    def grade(self, request: GradingInput) -> dict:
        result = {
            **request.identity.to_dict(),
            "criteria": {name: {"rating": "可以更进一步", "short_comment": "【模拟评语】文章已交代主要事件，但关键转折仍较简略；可补写人物动作、对话和当时感受，使变化更具体。"} for name in CRITERIA},
            "teacher_comment": "【模拟总评】文章能完整交代事件经过，也呈现人物态度变化；关键场景和情绪转折仍可展开，并加入更具体的动作、对话与感官描写。",
        }
        if self.failure == "invalid-rating":
            result["criteria"][CRITERIA[0]]["rating"] = "优秀"
        elif self.failure == "long-comment":
            result["criteria"][CRITERIA[0]]["short_comment"] = "长" * 1000
        return result
