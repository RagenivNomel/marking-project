"""Regression coverage of preserved code; no OCR executable or real scans used."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from pypdf import PdfReader, PdfWriter
from grading.schemas import ROOT
from scanning.split_by_student import legacy_splitter, scan_anonymous
from scanning.intake import SplitSubmission, apply_identity_decisions, read_existing_split
from grading.schemas import Identity, ValidationError
from tests.local_fixtures import require_local_fixtures
from tests.local_temp import local_test_directory


def page(index, ink=0.1, name="张三"):
    return dict(page_idx=index, is_front=index % 2 == 0, ink_frac=ink, name_text=name)


class ScannerRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = legacy_splitter()

    def test_originals_and_backups_match_recorded_hashes(self):
        backup = ROOT / "backups/phase1_originals"
        manifest_path = backup / "manifest.json"
        require_local_fixtures(self, [manifest_path])
        entries = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        required = [path for entry in entries for path in (ROOT / entry["path"], backup / entry["path"])]
        require_local_fixtures(self, required)
        for entry in entries:
            for path in (ROOT / entry["path"], backup / entry["path"]):
                with self.subTest(path=str(path)):
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().upper(), entry["sha256"])

    def test_reverse_back_pile_interleaving_and_unequal_rejection(self):
        self.assertEqual(self.engine.interleave_front_back([1, 3, 5], [6, 4, 2]), [1, 2, 3, 4, 5, 6])
        with self.assertRaises(ValueError):
            self.engine.interleave_front_back([1], [2, 3])

    def test_boundary_dedup_gap_new_name_and_first_page(self):
        cases = [
            ([page(0), page(2), page(4)], [(0, "张三")]),
            ([page(0), page(2, 0, ""), page(4)], [(0, "张三"), (4, "张三")]),
            ([page(0), page(2, name="李四")], [(0, "张三"), (2, "李四")]),
            ([page(0, 0, ""), page(2, name="李四")], [(0, ""), (2, "李四")]),
            ([page(0, 0, ""), page(2, 0, "")], [(0, "")]),
            ([page(0), page(1, name="李四"), page(2)], [(0, "张三")]),
            ([page(0, name=""), page(2, name="")], [(0, ""), (2, "")]),
        ]
        for analysis, expected in cases:
            with self.subTest(analysis=analysis):
                self.assertEqual(self.engine.detect_student_boundaries(analysis), expected)

    def test_pdf_order_anonymous_exports_and_manifest(self):
        with local_test_directory("pdf-order") as directory:
            root = Path(directory)
            for name, widths in (("front", [101, 103]), ("back", [104, 102])):
                writer = PdfWriter()
                for width in widths:
                    writer.add_blank_page(width=width, height=200)
                writer.write(root / f"{name}.pdf")
            analysis = [page(0), page(1), page(2, name="李四"), page(3)]
            with patch("scanning.split_by_student.legacy_splitter", return_value=self.engine), patch.object(self.engine, "analyze_front_pages", return_value=analysis), patch.object(self.engine, "save_name_preview", return_value="mock-preview.png"):
                result = scan_anonymous([(root / "front.pdf", root / "back.pdf")], root / "anonymous")
            master = PdfReader(root / "anonymous/_continuous.pdf")
            self.assertEqual([int(p.mediabox.width) for p in master.pages], [101, 102, 103, 104])
            self.assertEqual([Path(e["file"]).name for e in result["written"]], ["submission_001.pdf", "submission_002.pdf"])
            self.assertEqual([e["raw_ocr_name"] for e in result["written"]], ["张三", "李四"])
            for item in result["written"]:
                self.assertEqual(len(PdfReader(item["file"]).pages), 2)
            manifest = Path(result["manifest_path"]).read_text(encoding="utf-8-sig")
            self.assertIn("raw_ocr_name", manifest)
            self.assertIn("submission_001.pdf", manifest)
            with self.assertRaises(FileExistsError):
                scan_anonymous([], root / "anonymous")

    def test_existing_split_rejoins_renamed_pdfs_by_page_content(self):
        with local_test_directory("existing-split") as directory:
            root = Path(directory)
            writer = PdfWriter()
            for width in (101, 102, 103):
                writer.add_blank_page(width=width, height=200)
            writer.write(root / "_continuous.pdf")
            continuous = PdfReader(root / "_continuous.pdf")
            for name, indices in (("renamed-a.pdf", (0, 1)), ("renamed-b.pdf", (2,))):
                part = PdfWriter()
                for index in indices:
                    part.add_page(continuous.pages[index])
                part.write(root / name)
            (root / "_manifest.csv").write_text(
                "file,pages,raw_ocr_name,start_page_idx,name_preview\n"
                "old-a.pdf,2,bad-a,0,previews/a.png\n"
                "old-b.pdf,1,bad-b,2,previews/b.png\n",
                encoding="utf-8-sig",
            )
            records = read_existing_split(root)
            self.assertEqual([(r.source_pdf, r.start_page_idx, r.pages) for r in records],
                             [("renamed-a.pdf", 0, 2), ("renamed-b.pdf", 2, 1)])

    def test_identity_decisions_keep_confirmation_required_status(self):
        submission = SplitSubmission(1, "one.pdf", 0, 4, "", "name.png")
        roster = [Identity("1", "学生甲", "207")]
        result = apply_identity_decisions([submission], roster, [{
            "source_pdf": "one.pdf", "class_name": "207", "student_id": "1",
            "match_status": "CONFIRMATION_REQUIRED", "evidence": "姓名被覆盖",
        }])
        self.assertEqual(result[0]["match_status"], "CONFIRMATION_REQUIRED")
        with self.assertRaises(ValidationError):
            apply_identity_decisions([submission], roster, [])
