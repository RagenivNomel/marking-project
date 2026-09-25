"""Transient bilingual presentation of Stage 1 models; no new assessment authority."""
from application.models import Inspection, AssignmentSource
from desktop.teacher_flow import derive_teacher_flow
from application.workflows.task_storage import teacher_output_paths

SECTIONS = {
    'zh': ('作文准备', 'AI批改', '教师审核', '反馈输出'),
    'en': ('Preparation', 'AI Marking', 'Teacher Review', 'Feedback Output'),
}
DISABLED_REASONS = {
    'zh': '此操作目前尚未在当前界面开放。',
    'en': 'This action is not available from this screen yet.',
}
DISABLED_REASON = DISABLED_REASONS['zh']


def _language(language):
    return 'en' if language == 'en' else 'zh'


def project(inspection: Inspection, source: AssignmentSource | None = None,
            title='作文任务', language='zh'):
    language = _language(language)
    en = language == 'en'
    rows, attention = [], []
    summary = dict(inspection.summary)
    summary['identities'] = len({(s.class_name, s.student_id) for s in inspection.submissions
                                 if s.class_name and s.student_id})
    summary['identity_confirmed'] = sum(s.identity_confirmed for s in inspection.submissions)
    for index, item in enumerate(inspection.submissions, 1):
        if item.attention:
            status, tone = ('△ Needs attention' if en else '△ 需要处理'), 'attention'
        elif item.workbook_valid and item.review_status == 'PENDING':
            status, tone = ('○ Awaiting review' if en else '○ 待审核'), 'pending'
        elif item.rendered:
            status, tone = ('✓ Generated' if en else '✓ 已生成'), 'complete'
        elif item.workbook_valid and item.review_status == 'APPROVED':
            status, tone = ('✓ Approved' if en else '✓ 已审核'), 'complete'
        elif item.grading_available:
            status, tone = ('✓ Results available' if en else '✓ 结果可读取'), 'complete'
        elif not item.identity_confirmed:
            status, tone = ('○ Check identity' if en else '○ 待核对身份'), 'neutral'
        else:
            status, tone = ('○ No result yet' if en else '○ 尚无结果'), 'neutral'
        identity = ' · '.join(v for v in (item.class_name, item.student_id, item.student_name) if v) or ('Identity to check' if en else '身份待核对')
        facets = []
        if item.grading_available:
            facets.append('Marking result available' if en else '批改结果可读取')
        if item.workbook_valid and item.review_status in ('PENDING', 'APPROVED'):
            facets.append(('Awaiting teacher review' if item.review_status == 'PENDING' else 'Approved') if en else ('待教师审核' if item.review_status == 'PENDING' else '已审核'))
        if item.rendered:
            facets.append('Current feedback card verified' if en else '当前体检卡已核对')
        if item.ready_to_render:
            facets.append('Passes pre-generation checks' if en else '符合生成前检查')
        submission_label = 'Submission ID' if en else '作文标识'
        record_label = 'Saved record' if en else '保存记录'
        none_label = 'None' if en else '无'
        separator = ': ' if en else '：'
        technical = '\n'.join([f'{submission_label}{separator}{item.submission_id}', *item.evidence,
                               f'{record_label}{separator}{item.checkpoint_state or none_label}',
                               *[f'{a.code}: {a.technical_details}' for a in item.attention]])
        essay = f'Submission {index:03}' if en else f'作文 {index:03}'
        rows.append(dict(id=item.submission_id, ordinal=f'{index:03}', identity=identity,
                         label=essay, status=status, tone=tone, details=technical,
                         facets=facets))
        for a in item.attention:
            message = a.message
            if a.code == 'MARKING_RETRY_AVAILABLE':
                message = ('The previous attempt did not finish. Retry is available for this essay.' if en
                           else '上一次批改未完成，可以安全重试这份作文。')
            elif en and a.code == 'UNCERTAIN_ATTEMPT':
                message = 'This essay has an incomplete marking attempt that cannot be safely retried automatically.'
            elif en and a.code == 'SAVED_FAILURE':
                message = 'The previous marking attempt did not finish. Its saved work is still available for inspection.'
            elif en and a.code == 'BRIDGE_EVIDENCE_MISSING':
                message = 'Some saved marking evidence is missing. This essay is paused until the records can be checked.'
            attention.append(dict(title=f'{identity} · {essay}', message=message,
                                  details=f'{a.code}\n{a.technical_details}'))
    task_title = 'This assignment' if en else '这次任务'
    global_messages = {
        'MARKING_STARTUP_FAILED': 'Marking could not start. Your essays are still ready. Check the details or try again.',
        'SOURCE_ASSOCIATION_MISMATCH': 'The selected workbook and submission folder belong to different tasks. Choose one source and read it again.',
    }
    attention = [dict(title=task_title,
                      message=global_messages.get(a.code, a.message) if en else a.message,
                      details=f'{a.code}\n{a.technical_details}')
                 for a in inspection.attention] + attention
    references = []
    results_workbook = None
    feedback_cards_dir = None
    if source:
        # Keep implementation IDs, receipts, and checkpoints out of the normal
        # teacher details. The teacher's input references remain inspectable.
        references = [str(p) for p in (source.split_pile, source.roster) if p]
        if source.workbook is not None:
            results_workbook = source.workbook.resolve()
        elif source.results_directory is not None:
            results_workbook = source.results_directory / "results.xlsx"
        elif source.split_pile is not None:
            results_workbook = teacher_output_paths(source.split_pile).workbook
        feedback_cards_dir = source.feedback_cards_directory
        if feedback_cards_dir is None and results_workbook is not None:
            feedback_cards_dir = results_workbook.parent / "Feedback Cards"
    results_available = bool(
        results_workbook is not None and results_workbook.is_file()
        and not (source and source.output_location_conflict)
    )
    feedback_available = bool(
        summary.get("rendered", 0) > 0
        and feedback_cards_dir is not None
        and feedback_cards_dir.is_dir()
        and any(path.is_file() for path in feedback_cards_dir.glob("*-作文体检卡.png"))
    )
    subtitle = (f'{inspection.display_name} · {summary["submissions"]} submissions / {summary["identities"]} students'
                if en else f'{inspection.display_name} · {summary["submissions"]}份作文 / {summary["identities"]}名学生')
    notice = ('Local assignment · Saved files were checked; marking is not running.'
              if en else '本地作文任务 · 已检查保存的资料；当前没有运行批改。')
    state = dict(demo=False, scenario='real', view='workspace', section=2, title=title,
                subtitle=subtitle, notice=notice,
                 workbook=(results_workbook.name if results_available and results_workbook else ''),
                 resultsWorkbookPath=str(results_workbook) if results_workbook else '',
                 resultsWorkbookAvailable=results_available,
                 feedbackCardsDirectory=str(feedback_cards_dir) if feedback_cards_dir else '',
                 feedbackCardsAvailable=feedback_available,
                fileReferences=references, summary=summary, rows=rows, attention=attention,
                hero={}, progress={}, reducedMotion=False, hasSource=source is not None,
                inspectedAt='', disabledReason=DISABLED_REASONS[language], sections=list(SECTIONS[language]),
                language=language,
                actionAdvice=[dict(action=a.action.value, submissionIds=list(a.submission_ids),
                                   executionWired=a.execution_wired) for a in inspection.available_actions])
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state


def set_section(state, section, language=None):
    """Choose presentation wording only; retain overlapping Stage 1 counts."""
    language = _language(language or state.get('language', 'zh'))
    en = language == 'en'
    state['language'] = language
    state['sections'] = list(SECTIONS[language])
    state['disabledReason'] = DISABLED_REASONS[language]
    state['section'] = section
    s = state['summary']
    if section == 0:
        title = (f'{s["identity_confirmed"]} identities confirmed; {s["submissions"] - s["identity_confirmed"]} to check'
                 if en else f'{s["identity_confirmed"]}份身份已确认，还有{s["submissions"] - s["identity_confirmed"]}份需要核对')
        subtitle = ('Sources stay attached to each submission. Matching names are never merged automatically.'
                    if en else '按每份作文保留来源。姓名相同的作文不会自动合并。')
        action, tone = ('Start marking' if en else '开始批改'), 'pending'
    elif section == 1:
        title = (f'{s["grading_results_available"]} readable marking results found'
                 if en else f'已找到{s["grading_results_available"]}份可读取的批改结果')
        subtitle = ('This reflects saved files. Live progress, queue state, and remaining time are unavailable.'
                    if en else '这是已保存文件的检查结果。当前无法判断实时进度、等待队列或剩余时间。')
        action, tone = ('Start marking' if en else '开始批改'), 'active'
    elif section == 2:
        title = (f'{s["approved"]} approved, {s["awaiting_review"]} awaiting review'
                 if en else f'{s["approved"]}份已审核，{s["awaiting_review"]}份待审核')
        subtitle = ('Review in Excel, save, then read again. This view never approves submissions automatically.'
                    if en else '请在 Excel 中审核。保存后重新读取；这里只检查保存的内容，不会自动批准作文。')
        action, tone = ('Open marking results in Excel' if en else '打开批改结果 Excel'), 'pending'
    else:
        title = (f'{s["rendered"]} current feedback cards verified'
                 if en else f'{s["rendered"]}张当前体检卡已核对')
        subtitle = (f'{s["ready_to_render"]} pass pre-generation checks. Approved and generated counts may overlap and must not be added.'
                    if en else f'{s["ready_to_render"]}份符合生成前检查。已审核与已生成可能重叠，不能相加作为作文总数。')
        action = (f'Generate {s["ready_to_render"]} feedback cards' if en else f'生成{s["ready_to_render"]}张作文体检卡')
        tone = 'complete' if s['rendered'] else 'pending'
    state['hero'] = dict(title=title, subtitle=subtitle, action=action, tone=tone,
                         kicker=SECTIONS[language][section])
    state['teacherFlow'] = derive_teacher_flow(state, language)
    return state
