"""The roster is any Excel file with one sheet holding 班级, 班号 and 姓名."""
from pathlib import Path
import unittest

from openpyxl import Workbook

from excel.workbook import read_roster
from grading.schemas import Identity, ValidationError
from tests.local_temp import local_test_directory


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.temp = local_test_directory(self._testMethodName)
        self.root = Path(self.temp.__enter__())
        self.addCleanup(self.temp.__exit__, None, None, None)

    def roster(self, *sheets):
        """Write sheets given as (title, rows) and return the file path."""
        path = self.root / "any name.xlsx"
        book = Workbook()
        book.remove(book.active)
        for title, rows in sheets:
            sheet = book.create_sheet(title)
            for row in rows:
                sheet.append(row)
        book.save(path)
        book.close()
        return path

    def test_any_file_and_sheet_name_with_extra_columns_ignored(self):
        path = self.roster(
            ("说明", [["使用说明"], ["请填写名单"]]),
            ("随便什么名字", [["备注", "姓名", "班号", "分数", "班级"],
                             ["x", "陈一", 2, 50, 207], [None, None, None, None, None],
                             ["y", "林二", 1.0, 40, 207.0]]),
        )
        self.assertEqual(read_roster(path), [Identity("2", "陈一", "207"), Identity("1", "林二", "207")])

    def test_one_roster_may_hold_several_classes(self):
        path = self.roster(("名单", [["班级", "班号", "学生姓名"], [207, 1, "甲"], [208, 1, "乙"], [211, 5, "丙"]]))
        self.assertEqual({(i.class_name, i.student_id) for i in read_roster(path)},
                         {("207", "1"), ("208", "1"), ("211", "5")})

    def test_class_is_given_once_only_when_the_roster_has_no_class_column(self):
        path = self.roster(("名单", [["班号", "姓名"], [1, "甲"], [2, "乙"]]))
        self.assertEqual(read_roster(path, class_name="207"), [Identity("1", "甲", "207"), Identity("2", "乙", "207")])
        with self.assertRaisesRegex(ValidationError, "请填写班级"):
            read_roster(path)
        with_class = self.roster(("名单", [["班级", "班号", "姓名"], [207, 1, "甲"]]))
        with self.assertRaisesRegex(ValidationError, "不要另外填写班级"):
            read_roster(with_class, class_name="207")

    def test_other_headings_are_not_guessed(self):
        path = self.roster(("名单", [["班别", "学号", "Name"], [207, 1, "甲"]]))
        with self.assertRaisesRegex(ValidationError, "找不到学生名单"):
            read_roster(path, class_name="207")

    def test_every_student_sheet_is_read_and_repeats_count_once(self):
        path = self.roster(
            ("作文诊断输入", [["班号", "学生姓名", "班级", "教师点评"], [1, "甲", 207, "好"], [2, "乙", 207, ""]]),
            ("补充作文评改", [["班号", "学生姓名", "班级", "来源文件"], [2, "乙", 207.0, "乙_2.pdf"]]),
            ("208班", [["班级", "班号", "姓名"], [208, 1, "丙"]]),
        )
        self.assertEqual(read_roster(path), [Identity("1", "甲", "207"), Identity("2", "乙", "207"),
                                             Identity("1", "丙", "208")])
        self.assertEqual(read_roster(path, sheet_name="208班"), [Identity("1", "丙", "208")])

    def test_class_typed_once_fills_only_sheets_without_a_class_column(self):
        path = self.roster(("207班", [["班号", "姓名"], [1, "甲"]]),
                           ("208班", [["班级", "班号", "姓名"], [208, 1, "丙"]]))
        self.assertEqual(read_roster(path, class_name="207"), [Identity("1", "甲", "207"), Identity("1", "丙", "208")])
        with self.assertRaisesRegex(ValidationError, "“207班”没有“班级”列"):
            read_roster(path)

    def test_one_student_number_with_two_names_is_refused(self):
        path = self.roster(("A", [["班级", "班号", "姓名"], [207, 1, "甲"]]),
                           ("B", [["班级", "班号", "姓名"], [207, 1, "乙"]]))
        with self.assertRaisesRegex(ValidationError, "工作表“A”第 2 行是“甲”，工作表“B”第 2 行是“乙”"):
            read_roster(path)

    def test_bad_rows_name_the_row(self):
        missing = self.roster(("名单", [["班级", "班号", "姓名"], [207, 1, "甲"], [207, None, "乙"]]))
        with self.assertRaisesRegex(ValidationError, "第 3 行缺少班号"):
            read_roster(missing)
        duplicate = self.roster(("名单", [["班级", "班号", "姓名"], [207, 1, "甲"], [207, 1.0, "乙"]]))
        with self.assertRaisesRegex(ValidationError, "两个不同的名字"):
            read_roster(duplicate)
        both = self.roster(("名单", [["班级", "班号", "姓名", "学生姓名"], [207, 1, "甲", "甲"]]))
        with self.assertRaisesRegex(ValidationError, "只保留一个"):
            read_roster(both)
        empty = self.roster(("名单", [["班级", "班号", "姓名"]]))
        with self.assertRaisesRegex(ValidationError, "没有学生"):
            read_roster(empty)


if __name__ == "__main__":
    unittest.main()
