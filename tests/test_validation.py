import copy
from pathlib import Path
import unittest
from grading.grader import GradingInput
from grading.mock_grader import MockGrader
from excel.schema import HEADERS
from grading.schemas import CRITERIA, RATINGS, Identity, ROOT, Rating, Validator, ValidationError
from workflow.storage import atomic_json, read_json
from tests.local_temp import local_test_directory


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.identity = Identity("016", "测试学生", "MOCK-207")
        self.validator = Validator()
        self.valid = MockGrader().grade(GradingInput(self.identity, "测试作文"))

    def test_valid_roundtrip(self):
        self.assertEqual(self.validator.validate(self.valid, self.identity).to_dict(), self.valid)

    def test_fixed_criteria_rating_enum_and_excel_contract(self):
        self.assertEqual(CRITERIA, (
            "审题扣题", "情节紧凑", "重点突出", "详略得当", "情景交融", "多感官", "修辞运用", "结尾照应／升华",
        ))
        self.assertEqual(tuple(item.value for item in Rating), RATINGS)
        self.assertEqual(RATINGS, ("做得很好", "可以更进一步", "待加强"))
        self.assertEqual(HEADERS, [
            "班级", "班号", "姓名", "题目", "内容分", "语文与结构分", "总分",
            "审题扣题_等级", "审题扣题_评语", "情节紧凑_等级", "情节紧凑_评语",
            "重点突出_等级", "重点突出_评语", "详略得当_等级", "详略得当_评语",
            "情景交融_等级", "情景交融_评语", "多感官_等级", "多感官_评语",
            "修辞运用_等级", "修辞运用_评语", "结尾照应／升华_等级",
            "结尾照应／升华_评语", "教师总评", "审核状态",
        ])

    def test_invalid_ratings(self):
        for rating in ("优秀", "达标", "做得很好 ", "", None, 1):
            with self.subTest(rating=rating):
                data = copy.deepcopy(self.valid)
                data["criteria"][CRITERIA[0]]["rating"] = rating
                with self.assertRaises(ValidationError):
                    self.validator.validate(data, self.identity)

    def test_exact_eight_criteria_and_spelling(self):
        for mutation in ("missing", "extra", "slash"):
            data = copy.deepcopy(self.valid)
            if mutation == "missing":
                data["criteria"].pop(CRITERIA[0])
            elif mutation == "extra":
                data["criteria"]["额外项目"] = data["criteria"][CRITERIA[0]]
            else:
                data["criteria"]["结尾照应/升华"] = data["criteria"].pop(CRITERIA[-1])
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                self.validator.validate(data, self.identity)

    def test_identity_must_match_all_fields(self):
        for field in self.identity.to_dict():
            data = copy.deepcopy(self.valid)
            data[field] = "另一个学生"
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate(data, self.identity)

    def test_limits_inclusive_and_empty_comments_rejected(self):
        for field, limit in (("criterion_comment", 90), ("teacher_comment", 300)):
            for text, allowed in (("字" * limit, True), ("字" * (limit+1), False), (" \n", False), (None, False)):
                data = copy.deepcopy(self.valid)
                if field == "criterion_comment":
                    data["criteria"][CRITERIA[0]]["short_comment"] = text
                else:
                    data[field] = text
                with self.subTest(field=field, allowed=allowed):
                    if allowed:
                        self.validator.validate(data, self.identity)
                    else:
                        with self.assertRaises(ValidationError):
                            self.validator.validate(data, self.identity)

    def test_grader_cannot_supply_scores_next_improvement_or_unknown_fields(self):
        for field, value in (("score", 42), ("内容分", 20), ("语文与结构分", 30), ("总分", 50), ("next_improvement", "不得输出")):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.validator.validate({**self.valid, field: value}, self.identity)
        with self.assertRaises(ValidationError):
            self.validator.validate({**self.valid, "next_action": "write files"}, self.identity)

    def test_configured_limits_are_used(self):
        with local_test_directory("configured-limits") as directory:
            config = Path(directory)
            atomic_json(config / "criteria.json", read_json(ROOT / "config/criteria.json"))
            limits = read_json(ROOT / "config/text_limits.json")
            limits["criterion_comment"] = {"preferred_min": 1, "preferred_max": 2, "hard_max": 2}
            atomic_json(config / "text_limits.json", limits)
            with self.assertRaises(ValidationError):
                Validator(config).validate(self.valid, self.identity)


if __name__ == "__main__":
    unittest.main()
