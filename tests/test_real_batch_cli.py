import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from pypdf import PdfReader, PdfWriter

import run_pipeline
from tests.local_temp import local_test_directory


class FakeBatchPipeline:
    calls = []

    def __init__(self, project_dir, batch_id, **kwargs):
        self.project_dir = project_dir
        self.batch_id = batch_id
        self.kwargs = kwargs

    def run_real_batch(self, records, source_dir, **kwargs):
        self.__class__.calls.append({"records": records, "source_dir": source_dir, "kwargs": kwargs})
        return {"selected": len(records[:kwargs.get("limit")]) if kwargs.get("limit") else len(records), "validated": [], "failed": []}


class RealBatchCliTests(unittest.TestCase):
    def test_real_batch_cli_uses_intake_order_and_limit_without_grading(self):
        with local_test_directory("real-batch-cli") as directory:
            root = Path(directory)
            pile = root / "pile"
            pile.mkdir()
            pages = []
            for index in range(1, 4):
                source = pile / f"submission_{index:03}.pdf"
                writer = PdfWriter()
                writer.add_blank_page(width=612 + index, height=792)
                with source.open("wb") as handle:
                    writer.write(handle)
                pages.extend(PdfReader(str(source)).pages)
            continuous = pile / "_continuous.pdf"
            writer = PdfWriter()
            for page in pages:
                writer.add_page(page)
            with continuous.open("wb") as handle:
                writer.write(handle)
            (pile / "_manifest.csv").write_text(
                "start_page_idx,pages,raw_ocr_name,name_preview\n"
                "0,1,,preview-1.png\n1,1,,preview-2.png\n2,1,,preview-3.png\n",
                encoding="utf-8",
            )
            roster_path = root / "roster.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "作文诊断输入"
            sheet.append(["班号", "学生姓名", "班级"])
            for index, name in enumerate(("甲学生", "乙学生", "丙学生"), 1):
                sheet.append([index, name, 207])
            book.save(roster_path)
            book.close()
            decisions = [
                {
                    "source_pdf": f"submission_{index:03}.pdf",
                    "class_name": "207", "student_id": str(index),
                    "match_status": "CONFIRMATION_REQUIRED" if index == 1 else "STRONG_ROSTER_MATCH",
                    "evidence": "reviewed",
                }
                for index in range(1, 4)
            ]
            decisions_path = root / "decisions.json"
            decisions_path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
            FakeBatchPipeline.calls = []
            with patch.object(run_pipeline, "Pipeline", FakeBatchPipeline):
                exit_code = run_pipeline.main([
                    "--project-dir", str(root), "real-batch",
                    "--pile", str(pile), "--workbook", str(roster_path),
                    "--decisions", str(decisions_path), "--limit", "2",
                    "--model-profile", "luna_xhigh", "--batch", "cli-test",
                ])
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(FakeBatchPipeline.calls), 1)
            call = FakeBatchPipeline.calls[0]
            self.assertEqual([item["student_id"] for item in call["records"]], ["2", "3"])
            self.assertEqual(call["kwargs"]["limit"], 2)
            self.assertEqual(call["kwargs"]["model_profile"], "luna_xhigh")


if __name__ == "__main__":
    unittest.main()
