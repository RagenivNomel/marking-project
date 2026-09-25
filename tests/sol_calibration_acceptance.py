"""Create persistent fictional calibration artifacts for workbook inspection."""
import argparse
import json
from pathlib import Path

from pypdf import PdfWriter

from grading.schemas import CRITERIA, Identity
from grading.sol_grader import SolGrader
from workflow.calibration_pipeline import CalibrationPipeline


class SyntheticTransport:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def ensure_ready(self):
        return None

    def __call__(self, payload, timeout_seconds):
        self.calls += 1
        return self.response


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    args.root.mkdir(parents=True, exist_ok=False)
    source = args.root / "fictional-source.pdf"
    writer = PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=612, height=792)
    writer.write(source)
    identity = Identity("016", "虚构测试学生", "MOCK-207")
    output = {
        "reading_quality": {"complete_essay_legible": True, "uncertainties": [], "materially_affects_grade": False},
        "grading": {
            **identity.to_dict(),
            "criteria": {name: {"rating": "可以更进一步", "short_comment": f"【模拟】围绕{name}补充具体细节。"} for name in CRITERIA},
            "teacher_comment": "【模拟】这是用于验证工作簿边界的虚构反馈。",
        },
        "evidence": [{"judgment": "重点突出", "page_numbers": [2], "rationale": "【模拟】用于检查审计字段。"}],
    }
    transport = SyntheticTransport({"id": "resp_synthetic", "model": "gpt-5.6-sol", "status": "completed", "output_text": json.dumps(output, ensure_ascii=False)})
    pipeline = CalibrationPipeline(args.root, grader_factory=lambda: SolGrader(transport=transport))
    result = pipeline.run(source, identity)
    assert result["state"] == "VALIDATED" and result["review_status"] == "PENDING_HUMAN_REVIEW"
    assert transport.calls == 1
    print(json.dumps({**result, "synthetic": True, "transport_calls": transport.calls}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
