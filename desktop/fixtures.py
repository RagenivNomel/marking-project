"""Clearly identified, in-memory visual examples using the real Stage 1 model types."""
from dataclasses import replace
from application.models import Inspection, SubmissionState, Attention
from desktop.projection import project, set_section
from desktop.teacher_flow import derive_teacher_flow

DEMO_NAMES_ZH = {
    'home': '首页 / 最近任务', 'workspace': '混合状态', 'marking': '批改进度演示',
    'handoff': 'Excel 交接', 'review': '部分审核', 'attention': '部分输出失败',
    'complete': '当前输出完成', 'create': '本地材料', 'identity': '身份核对',
    'generate': '生成范围', 'empty': '空状态', 'unknown': '状态不确定',
    'system': '组件与键盘焦点', 'stress': '长内容 / 40份作文',
}
DEMO_NAMES_EN = {
    'home': 'Home / Recent Tasks', 'workspace': 'Mixed Status', 'marking': 'Marking Progress Demo',
    'handoff': 'Excel Handoff', 'review': 'Partial Review', 'attention': 'Partial Output Failure',
    'complete': 'Current Output Complete', 'create': 'Local Materials', 'identity': 'Identity Check',
    'generate': 'Generation Scope', 'empty': 'Empty State', 'unknown': 'Uncertain Status',
    'system': 'Components & Keyboard Focus', 'stress': 'Long Content / 40 Submissions',
}
DEMO_NAMES = DEMO_NAMES_ZH

def demo_state(key='home', language='zh'):
    language = 'en' if language == 'en' else 'zh'
    en = language == 'en'
    if key not in DEMO_NAMES_ZH:
        raise ValueError('Unknown demo')
    count = 0 if key == 'empty' else 40 if key == 'stress' else 31
    items = []
    for i in range(count):
        # Two separate submissions share the same visible identity intentionally.
        student = 20 if i in (16, 17) else 32 if i == 19 else i + 1
        name = '张瑞颖' if i in (16, 17) else ('欧阳司徒佳宁' if i == 5 else ('Demo Student' if en else '演示学生'))
        approved = i < (37 if key == 'stress' else 28)
        rendered = i < 24
        if key in ('complete', 'attention'):
            approved, rendered = True, key == 'complete' or i != 18
        if key in ('handoff', 'marking', 'unknown', 'identity', 'create'):
            approved, rendered = False, False
        grading = key not in ('create', 'identity') and (key not in ('marking', 'unknown') or i < 17)
        confirmed = key != 'create' and not (key == 'identity' and i == 17)
        issues = ()
        if key == 'attention' and i == 18:
            name = '李佳恩'
            issues = (Attention('DEMO_LAYOUT_OVERFLOW', 'error',
                ('The teacher comment is too long for the current layout. The original comment was not changed, and the other 30 feedback cards were generated successfully. Return to Excel to review it; you decide any wording changes.' if en else '教师总评超出当前版面可以容纳的长度。原有评语没有被修改，其他30张体检卡已正常生成。请回到 Excel 检查总评；如需修改，由您决定措辞。'),
                ('Future execution-result demo only. Read-only inspection cannot predict layout failure.' if en else '仅为未来执行结果演示。当前只读检查不能预测排版失败。'), f'demo-{i+1:03}'),)
        if key == 'unknown' and i == 17:
            issues = (Attention('DEMO_ATTEMPT_UNKNOWN', 'error',
                ('The final submission may have been sent for marking, but completion cannot be confirmed. Do not mark it again. The 17 results already found remain readable.' if en else '最后一份作文可能已发起批改请求，目前无法确认是否完成，请勿重复批改。已找到的17份结果仍可读取。'),
                ('Demo call evidence is uncertain; do not retry automatically or clear a lock.' if en else '演示关联调用证据不确定；不得自动重试或清理锁。'), f'demo-{i+1:03}'),)
        items.append(SubmissionState(f'demo-{i+1:03}', name, '207' if i < 24 else '211',
                     f'{student:02}', confirmed, grading, grading, 'APPROVED' if approved else 'PENDING' if grading else None,
                     rendered, approved and not rendered and not issues, evidence=(('Demo source; no real student files were read' if en else '演示来源；未读取真实学生文件'),), attention=issues))
    state = project(Inspection('sec2_hcl_composition_v1', ('Secondary 2 Higher Chinese Composition' if en else '中二高华作文批改'), (), tuple(items)),
                    title=('The Time I Learned to Persevere' if en else '那一次，我学会了坚持'), language=language)
    state.update(demo=True, scenario=key,
                 notice=('Demo data · Names and statuses are examples; no marking or generation was run.' if en else '演示数据 · 姓名与状态均为示例，未执行批改或生成。'),
                 workbook=('Composition_3_Marking_Results.xlsx' if en else '作文三_批改结果.xlsx'),
                 fileReferences=[('Demo file location; no file will be created or opened' if en else '演示文件位置；不会创建或打开文件')])
    section = {'marking': 1, 'unknown': 1, 'identity': 0, 'create': 0,
               'attention': 3, 'generate': 3, 'complete': 3}.get(key, 2)
    set_section(state, section, language)
    state['view'] = key if key in ('home', 'create', 'empty', 'system') else 'workspace'
    if key == 'home':
        state['hero'].update(title=('Composition 3 · The Time I Learned to Persevere' if en else '作文三 · 那一次，我学会了坚持'), subtitle=('Classes 207 / 211 · 31 submissions · 3 still await your review' if en else '207 / 211 班 · 31份作文 · 还有3份等待您的审核'), kicker=('Continue where you left off' if en else '接着上次的工作'), action=('View this assignment' if en else '查看这次任务'))
    elif key == 'marking':
        state['progress'] = dict(completed=17, total=31, active=1, waiting=13, attention=0,
            current=('207 · 20 · 张瑞颖 · Submission 018' if en else '207 · 20 · 张瑞颖 · 作文 018'), elapsed=('48 min' if en else '48分钟'), saved=('Demo: the 17 completed marking results have been saved.' if en else '演示：已完成的17份批改结果已保存。'))
        state['hero'].update(title=('AI is marking submissions' if en else 'AI正在批改作文'), subtitle=('Future running-state demo · No live marking queue is connected' if en else '未来运行态演示 · 当前没有连接实时批改队列'), kicker=('Marking progress' if en else '批改进度'), tone='active')
        for i, row in enumerate(state['rows']):
            row.update(status=('✓ Complete' if en else '✓ 已完成') if i < 17 else ('● In progress' if en else '● 处理中') if i == 17 else ('○ Waiting' if en else '○ 等待中'), tone='complete' if i < 17 else 'active' if i == 17 else 'neutral')
    elif key == 'handoff':
        state['hero'].update(title=('Next, review the results in Excel.' if en else '接下来，请在 Excel 中审核。'), subtitle=('31 readable results · 31 awaiting review · No feedback cards generated' if en else '31份结果可读取 · 31份待审核 · 体检卡尚未生成'))
    elif key == 'attention':
        state['hero'].update(title=('30 generated, 1 not generated.' if en else '30张已生成，1张未生成。'), subtitle=('Demo: the other 30 feedback cards were generated successfully; the original comments were not changed.' if en else '演示：其他30张体检卡已正常生成，原有评语没有被修改。'), tone='attention', kicker=('1 needs attention' if en else '1份需要处理'), action=('View the 30 generated cards' if en else '查看已生成的30张'))
    elif key == 'complete':
        state['hero'].update(title=('31 feedback cards are ready.' if en else '31张作文体检卡已备妥。'), subtitle=('Demo: the current reviewed version and its outputs were verified. Generated does not mean printed or sent to students.' if en else '演示：已核对当前审核版本与对应输出。已生成不代表已打印或发给学生。'), tone='card', action=('View output locations' if en else '查看输出位置'))
    elif key == 'unknown':
        state['hero'].update(title=('17 results found; 1 status needs checking.' if en else '已找到17份结果，另1份状态需要核对。'), subtitle=('The other 13 have no result. This inspection cannot prove that they are waiting in a queue.' if en else '其余13份尚无结果；当前检查不能证明它们正处于等待队列。'), tone='attention')
    elif key == 'generate':
        state['hero'].update(title=('28 approved; 4 feedback cards can be generated' if en else '28份已审核，本次可生成4张体检卡'), subtitle=('24 already have a current version; 3 await review. Text fit must be checked during generation.' if en else '24张已有当前版本，3份待审核。实际版面是否容纳文字，需要在生成时检查。'))
    elif key == 'stress':
        state['title'] = ('Composition 4 · When I Finally Understood Perseverance Through an Apparently Ordinary Event' if en else '作文四 · 当我终于明白坚持的意义——从一件看似平凡的小事说起')
        state['workbook'] = ('Higher_Chinese_Composition_4_Classes_207_211_Teacher_Reviewed_Term_3_2026.xlsx' if en else '中二高华作文四_207与211班_教师审核后保存版本_2026年第三学期_批改结果.xlsx')
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state
