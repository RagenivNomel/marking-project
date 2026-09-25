from grading.schemas import CRITERIA

SHEET = "Phase1批改结果"
AUDIT_SHEET = "Pipeline审计"
CRITERION_PREFIX = {name: name for name in CRITERIA}
HEADERS = ["班级", "班号", "姓名", "题目", "内容分", "语文与结构分", "总分"]
for name in CRITERIA:
    HEADERS.extend([CRITERION_PREFIX[name] + "_等级", CRITERION_PREFIX[name] + "_评语"])
HEADERS += ["教师总评", "审核状态"]
AUDIT_HEADERS = ["任务ID", "班级", "班号", "Excel行", "输入摘要", "流程状态"]
