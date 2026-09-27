"""QML bridge for guided inspection and roster-backed identity confirmation."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import threading
import time
import traceback
from PySide6.QtCore import QObject, Property, QRunnable, QThreadPool, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from application import AssignmentSource, WorkflowController
from application.models import Action
from application.workflows.registry import WORKFLOWS, get_workflow
from application.workflows.sec2_hcl_composition_v1 import WORKFLOW_ID as ORIGINAL_WORKFLOW_ID
from desktop.fixtures import demo_state
from desktop.identity_confirmation import (
    DEFAULT_ROSTER,
    build_identity_review,
    prepare_identity_suggestions,
    resolve_identity_companions,
    save_identity_confirmations,
    with_decisions_dir,
)
from desktop.projection import project, set_section
from desktop.teacher_flow import derive_teacher_flow


def _committed_results(summary):
    """Count only authoritative workbook commits as saved progress."""
    if not isinstance(summary, dict):
        return 0
    for key in ("committed_results", "workbook_valid", "grading_results_available"):
        value = summary.get(key)
        if value is not None:
            try:
                return max(0, int(value))
            except (TypeError, ValueError):
                return 0
    return 0

def task_title(source, language):
    """Teacher-facing task name; never the app's internal scan workspace folder."""
    if source.continuous_scan is not None:
        return Path(source.continuous_scan).parent.name
    if source.workbook is not None:
        return source.workbook.stem
    if source.split_pile is not None:
        return source.split_pile.name
    return 'Local composition materials' if language == 'en' else '本地作文资料'

class ReadSignals(QObject):
    finished = Signal(object, object, str)

class ReadTask(QRunnable):
    def __init__(self, controller, source, refresh, identity_matcher=None, decisions_dir=None):
        super().__init__()
        self.controller, self.source, self.refresh = controller, source, refresh
        self.identity_matcher, self.decisions_dir = identity_matcher, decisions_dir
        self.signals = ReadSignals()

    def run(self):
        try:
            source = (self.controller.prepare_source(self.source)
                      if hasattr(self.controller, 'prepare_source') else self.source)
            source = with_decisions_dir(source, self.decisions_dir)
            # A continuous scan has its workspace only now: reattach its saved confirmations.
            source = resolve_identity_companions(source)
            # Only scans the app splits itself; pre-built piles are already labelled.
            if self.identity_matcher is not None and self.source.continuous_scan is not None:
                try:
                    prepare_identity_suggestions(source, self.identity_matcher)
                except Exception:
                    # Guessing is a convenience: the teacher can still pick by hand.
                    traceback.print_exc()
            source = (self.controller.bind_source(source)
                      if hasattr(self.controller, 'bind_source') else source)
            method = self.controller.refresh_review_status if self.refresh else self.controller.inspect
            result = method(source)
            self.signals.finished.emit(result, source, '')
        except Exception as exc:
            self.signals.finished.emit(None, self.source, str(exc))

class MarkingSignals(QObject):
    progress = Signal(object)
    finished = Signal(object, object, object, str)

class MarkingTask(QRunnable):
    """Run the existing production batch away from the Qt GUI thread."""
    def __init__(self, controller, source):
        super().__init__()
        self.controller, self.source = controller, source
        self.stop_event = threading.Event()
        self.signals = MarkingSignals()

    def request_stop(self):
        """Stop before the next student's model call; let the current one save."""
        self.stop_event.set()

    def run(self):
        try:
            outcome = self.controller.execute(
                Action.RUN_MARKING, self.source,
                progress_callback=self.signals.progress.emit,
                cancelled=self.stop_event.is_set,
            )
            source = outcome["source"]
            inspection = self.controller.inspect(source)
            self.signals.finished.emit(inspection, source, outcome.get("result", {}), "")
        except Exception as exc:
            traceback.print_exc()
            try:
                inspection = self.controller.inspect(self.source)
            except Exception:
                inspection = None
            self.signals.finished.emit(inspection, self.source, {}, str(exc))

class RenderingSignals(QObject):
    progress = Signal(object)
    finished = Signal(object, object, object, str)

class RenderingTask(QRunnable):
    """Generate approved feedback cards away from the Qt GUI thread."""
    def __init__(self, controller, source):
        super().__init__()
        self.controller, self.source = controller, source
        self.signals = RenderingSignals()

    def run(self):
        try:
            outcome = self.controller.execute(
                Action.RENDER_APPROVED, self.source,
                progress_callback=self.signals.progress.emit,
            )
            source = outcome["source"]
            inspection = self.controller.inspect(source)
            self.signals.finished.emit(inspection, source, outcome.get("result", {}), "")
        except Exception as exc:
            try:
                inspection = self.controller.inspect(self.source)
            except Exception:
                inspection = None
            self.signals.finished.emit(inspection, self.source, {}, str(exc))

class DesktopBridge(QObject):
    changed = Signal()
    busyChanged = Signal()

    def __init__(self, controller=None, parent=None, *, open_url=None, identity_matcher=None,
                 identity_decisions_dir=None, controller_factory=None):
        super().__init__(parent)
        # Builds the controller for the workflow the teacher selects.
        self._controller_factory = controller_factory or (
            (lambda workflow_id: controller) if controller is not None else WorkflowController)
        # The developer UI and command-line sources predate workflow selection
        # and keep using the original workflow until one is selected.
        self._controller = controller or self._controller_factory(ORIGINAL_WORKFLOW_ID)
        self._selected_workflow = None
        self._identity_matcher = identity_matcher
        self._identity_decisions_dir = identity_decisions_dir
        self._open_url = open_url or QDesktopServices.openUrl
        self._language = 'zh'
        self._state = demo_state('home', self._language)
        self._source = None
        self._inspection = None
        self._real_state = None
        self._busy = False
        self._task = None
        self._marking_started = None
        self._cancel_requested = False
        self._rendering_started = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)

    @Property('QVariantMap', notify=changed)
    def state(self):
        return deepcopy(self._state)

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=changed)
    def hasInspection(self):
        return self._real_state is not None

    @Property(str, notify=changed)
    def language(self):
        return self._language

    @Property(str, constant=True)
    def defaultRosterPath(self):
        return str(DEFAULT_ROSTER) if DEFAULT_ROSTER.is_file() else ''

    @Property('QVariantList', constant=True)
    def workflows(self):
        return [info.to_dict() for info in WORKFLOWS]

    @Property('QVariantMap', notify=changed)
    def selectedWorkflow(self):
        """Empty until the teacher chooses a workflow on the start page."""
        return self._selected_workflow.to_dict() if self._selected_workflow else {}

    def _clear_session(self):
        """Forget the loaded task in memory only; saved results stay on disk."""
        reduced = self._state['reducedMotion']
        self._source = None
        self._inspection = None
        self._real_state = None
        self._state = demo_state('home', self._language)
        self._state['reducedMotion'] = reduced

    @Slot(str)
    def selectWorkflow(self, workflow_id):
        """Choose a workflow; no task is read until the teacher chooses submissions."""
        if self._busy:
            return
        try:
            info = get_workflow(workflow_id)
        except ValueError:
            return
        controller = self._controller_factory(info.workflow_id)
        self._clear_session()
        self._controller = controller
        self._selected_workflow = info
        self.changed.emit()

    @Slot()
    def showWorkflowList(self):
        if self._busy:
            return
        self._clear_session()
        self._selected_workflow = None
        self.changed.emit()

    def _attach_identity_review(self, state, source, inspection):
        try:
            state['identityReview'] = build_identity_review(source, inspection, self._language)
        except Exception as exc:
            state['identityReview'] = {
                'visible': True,
                'requiresRoster': source.roster is None,
                'rows': [],
                'roster': [],
                'confirmedCount': 0,
                'totalCount': state.get('summary', {}).get('submissions', 0),
                'message': ('Student information could not be prepared. Check the roster and try again.'
                            if self._language == 'en' else '学生资料无法准备，请检查名册后重试。'),
            }
            state['notice'] = str(exc)
        return state

    @Slot(str)
    def setLanguage(self, language):
        language = 'en' if language == 'en' else 'zh'
        if language == self._language or self._busy:
            return
        previous = self._state
        self._language = language
        reduced = previous['reducedMotion']
        if not previous['demo'] and self._inspection is not None and self._source is not None:
            title = task_title(self._source, language)
            state = project(self._inspection, self._source, title, language)
            self._attach_identity_review(state, self._source, self._inspection)
            state = set_section(state, previous['section'], language)
            state['view'] = previous['view']
            state['inspectedAt'] = previous.get('inspectedAt', '')
            if (previous.get('progress', {}).get('operation') == 'render'
                    and previous.get('progress', {}).get('running') is False):
                state['progress'] = deepcopy(previous['progress'])
            if previous.get('renderResult') is not None:
                state['renderResult'] = deepcopy(previous['renderResult'])
            if state['inspectedAt']:
                state['notice'] += (f' Inspection completed at {state["inspectedAt"]}.' if language == 'en' else ' 本次检查完成于 ' + state['inspectedAt'])
            self._real_state = deepcopy(state)
        else:
            state = demo_state(previous.get('scenario', 'home'), language)
            state['view'] = previous['view']
            if state['view'] == 'workspace' and state['section'] != previous['section']:
                set_section(state, previous['section'], language)
        state['reducedMotion'] = reduced
        self._state = state
        self.changed.emit()

    @Slot(str)
    def selectDemo(self, key):
        if self._busy:
            return
        if key == 'real' and self._real_state is not None:
            reduced = self._state['reducedMotion']
            self._state = deepcopy(self._real_state)
            self._state['reducedMotion'] = reduced
        else:
            try:
                state = demo_state(key, self._language)
            except ValueError:
                return
            state['reducedMotion'] = self._state['reducedMotion']
            self._state = state
        self.changed.emit()

    @Slot(str)
    def navigate(self, view):
        if view not in ('home', 'workspace', 'create', 'system', 'empty'):
            return
        self._state['view'] = view
        if view == 'workspace':
            set_section(self._state, self._state['section'], self._language)
        self.changed.emit()

    @Slot(int)
    def selectSection(self, section):
        if section not in range(4):
            return
        self._state['view'] = 'workspace'
        self._state['progress'] = {}
        set_section(self._state, section, self._language)
        self.changed.emit()

    @Slot(bool)
    def setReducedMotion(self, value):
        self._state['reducedMotion'] = value
        self.changed.emit()

    @Slot(str, str, str, str, str, str)
    def inspectPaths(self, workbook, jobs, receipts, split_pile, roster, continuous_scan):
        def one(value):
            value = value.strip().strip('"')
            if value.startswith('file:'):
                value = QUrl(value).toLocalFile()
            return Path(value).expanduser().resolve() if value else None
        def many(value):
            return tuple(one(p) for p in value.split(';') if p.strip())
        source = AssignmentSource(workbook=one(workbook), job_roots=many(jobs),
                                  receipt_roots=many(receipts), split_pile=one(split_pile),
                                  roster=one(roster), continuous_scan=one(continuous_scan))
        source = resolve_identity_companions(source)
        if not any((source.workbook, source.job_roots, source.receipt_roots,
                    source.split_pile, source.continuous_scan)):
            self._state['notice'] = ('Specify an existing workbook, composition folder, or continuous-scan PDF, then read it.'
                                     if self._language == 'en' else '请指定已有工作簿、作文资料文件夹或连续扫描 PDF，然后读取。')
            self.changed.emit()
            return
        self.inspect_source(source)

    def inspect_source(self, source, refresh=False):
        if self._busy:
            return
        source = resolve_identity_companions(source)
        if hasattr(self._controller, 'bind_source'):
            source = self._controller.bind_source(source)
        self._busy = True
        self.busyChanged.emit()
        preparing = source.continuous_scan is not None and source.split_pile is None
        self._state['notice'] = (
            'Preparing the continuous scan and reading the selected local materials.'
            if preparing and self._language == 'en' else
            '正在整理连续扫描并读取指定的本地资料。'
            if preparing else
            'Reading the selected local materials without changing them.'
            if self._language == 'en' else
            '正在读取指定的本地资料；不会更改文件。'
        )
        self.changed.emit()
        task = ReadTask(self._controller, source, refresh, self._identity_matcher,
                        self._identity_decisions_dir)
        task.signals.finished.connect(self._finished)
        self._task = task
        self.pool.start(task)

    @Slot()
    def refresh(self):
        # A demo never refreshes a previously selected real source accidentally.
        if self._source is not None and not self._state['demo']:
            self.inspect_source(self._source, refresh=True)

    def _open_managed_path(self, value, *, folder):
        path = Path(value).expanduser() if value else None
        valid = bool(path and (path.is_dir() if folder else path.is_file()))
        label = ("Feedback-card folder" if folder else "Results workbook")
        label_zh = ("体检卡文件夹" if folder else "批改结果工作簿")
        if not valid:
            self._state["notice"] = (
                f"{label} could not be found." if self._language == "en"
                else f"找不到{label_zh}。"
            )
            self.changed.emit()
            return False
        try:
            opened = bool(self._open_url(QUrl.fromLocalFile(str(path.resolve()))))
        except Exception:
            opened = False
        if not opened:
            self._state["notice"] = (
                f"{label} could not be opened." if self._language == "en"
                else f"无法打开{label_zh}。"
            )
            self.changed.emit()
            return False
        self._state["notice"] = (
            f"Opened {label.lower()}." if self._language == "en"
            else f"已打开{label_zh}。"
        )
        self.changed.emit()
        return True

    @Slot()
    def openResults(self):
        """Open the one resolved authoritative workbook in the OS default app."""
        return self._open_managed_path(self._state.get("resultsWorkbookPath"), folder=False)

    @Slot()
    def openFeedbackCards(self):
        """Open this task's teacher-facing feedback-card folder."""
        return self._open_managed_path(self._state.get("feedbackCardsDirectory"), folder=True)

    @Slot(object, object, str)
    def _finished(self, inspection, source, error):
        reduced = self._state['reducedMotion']
        if error:
            self._state['notice'] = ('This read did not complete. The previous content remains below; check the location and try again.' if self._language == 'en' else '本次读取未完成。下方仍为上次显示的内容，请检查文件位置后重试。')
            self._state['attention'] = [dict(title=('Read did not complete' if self._language == 'en' else '资料读取未完成'), message=('Check that the selected file or folder is available. No file was changed.' if self._language == 'en' else '请检查所选文件或文件夹是否可用；文件未被修改。'), details=error)]
        else:
            title = task_title(source, self._language)
            self._state = set_section(project(inspection, source, title, self._language), 2, self._language)
            self._attach_identity_review(self._state, source, inspection)
            self._state['inspectedAt'] = datetime.now().strftime('%H:%M:%S')
            self._state['notice'] += (f' Inspection completed at {self._state["inspectedAt"]}.' if self._language == 'en' else ' 本次检查完成于 ' + self._state['inspectedAt'])
            self._source = source
            self._inspection = inspection
            self._state['reducedMotion'] = reduced
            self._real_state = deepcopy(self._state)
        self._busy = False
        self._task = None
        self.busyChanged.emit()
        self.changed.emit()

    @Slot('QVariantList')
    def confirmIdentitySelections(self, selections):
        """Persist explicit roster selections, then re-inspect the same source."""
        if self._busy or self._source is None:
            return
        try:
            source, saved = save_identity_confirmations(self._source, list(selections or ()))
        except Exception as exc:
            self._state['notice'] = (f'Could not save the student confirmations: {exc}' if self._language == 'en'
                                     else f'学生资料确认无法保存：{exc}')
            self.changed.emit()
            return
        self._source = source
        self._state['notice'] = (f'{saved} student confirmation records saved. Checking the task again…'
                                 if self._language == 'en' else f'已保存{saved}份学生确认记录，正在重新检查任务…')
        self.changed.emit()
        self.inspect_source(source, refresh=True)

    @Slot()
    def startMarking(self):
        if (self._busy or self._source is None or self._state.get("demo")
                or not self._state.get("teacherFlow", {}).get("primaryActionEnabled")
                or self._state.get("teacherFlow", {}).get("primaryAction") != Action.RUN_MARKING.value):
            return
        self._busy = True
        self._cancel_requested = False
        self.busyChanged.emit()
        self._marking_started = time.monotonic()
        summary = (self._inspection.summary if self._inspection is not None else {})
        committed = _committed_results(summary)
        self._state["progress"] = {
            "total": summary.get("submissions", 0),
            "completed": committed,
            "active": 0,
            "waiting": summary.get("submissions", 0) - committed,
            "finishing": 0,
            "remaining_not_started": max(0, summary.get("submissions", 0) - committed),
            "attention": 0,
            "current": "",
            "elapsed": "0:00",
            "running": True,
            "saved": "Saved results are checked before any unfinished essay is marked." if self._language == "en" else "开始前先核对已保存结果。",
        }
        self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
        self._state["notice"] = ("Marking has started. Each essay is handled separately." if self._language == "en"
                                  else "已开始批改；每份作文会分别处理。")
        self.changed.emit()
        task = MarkingTask(self._controller, self._source)
        task.signals.progress.connect(self._marking_progress)
        task.signals.finished.connect(self._marking_finished)
        self._task = task
        self.pool.start(task)

    @Slot()
    def cancelMarking(self):
        """Stop scheduling essays; let in-flight work finish and save safely."""
        if not self._busy or not isinstance(self._task, MarkingTask) or self._cancel_requested:
            return
        self._cancel_requested = True
        self._task.request_stop()
        current_progress = self._state.get("progress", {})
        active = max(0, int(current_progress.get("active", 0) or 0))
        remaining = max(0, int(current_progress.get("remaining_not_started", 0) or 0))
        self._state["progress"] = {
            **current_progress,
            "cancelRequested": True,
            "finishing": active,
            "remaining_not_started": remaining,
            "saved": ("Finishing current essays before stopping. Essays not started will remain."
                      if self._language == "en" else "先完成当前作文再停止；尚未开始的作文会保留。"),
        }
        self._state["notice"] = ("Finishing current essays before stopping."
                                  if self._language == "en" else "先完成当前作文再停止批改。")
        self.changed.emit()

    @Slot(object)
    def _marking_progress(self, progress):
        if not isinstance(progress, dict):
            return
        state = dict(progress)
        state["running"] = True
        state["cancelRequested"] = self._cancel_requested
        elapsed = max(0, int(time.monotonic() - (self._marking_started or time.monotonic())))
        state["elapsed"] = f"{elapsed // 60}:{elapsed % 60:02d}"
        state["saved"] = (("Finishing current essays before stopping. Essays not started will remain."
                           if self._language == "en" else "先完成当前作文再停止；尚未开始的作文会保留。")
                          if self._cancel_requested else
                          (f"{state.get('completed', 0)} committed result(s) are saved." if self._language == "en"
                           else f"{state.get('completed', 0)}份已提交结果已保存。"))
        self._state["progress"] = state
        self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
        self.changed.emit()

    @Slot(object, object, object, str)
    def _marking_finished(self, inspection, source, outcome, error):
        reduced = self._state["reducedMotion"]
        elapsed = self._state.get("progress", {}).get("elapsed", "—")
        if inspection is not None:
            title = task_title(source, self._language)
            self._state = set_section(project(inspection, source, title, self._language), 2, self._language)
            self._attach_identity_review(self._state, source, inspection)
            self._source, self._inspection = source, inspection
            # MarkingTask emits the batch result itself, not its controller wrapper.
            result = outcome if isinstance(outcome, dict) else {}
            failures = len(result.get("failed", ()))
            self._state["markingResult"] = result
            self._state["reducedMotion"] = reduced
            summary = inspection.summary
            saved = _committed_results(summary)
            attention = summary["submissions_needing_attention"]
            remaining_not_started = max(0, int(result.get("remaining_not_started", 0) or 0))
            self._state["progress"] = {
                "total": summary["submissions"],
                "completed": saved,
                "active": 0,
                "waiting": remaining_not_started,
                "finishing": 0,
                "remaining_not_started": remaining_not_started,
                "attention": attention,
                "current": "",
                "elapsed": elapsed,
                "running": False,
                "saved": (f"{saved} committed result(s) are saved." if self._language == "en"
                          else f"已保存{saved}份已提交结果。"),
            }
            startup_problem = error
            if not error and failures and not result.get("validated"):
                # Every essay failed and nothing was saved: report it as a
                # failed start rather than quietly returning to "ready".
                first = result["failed"][0].get("error")
                startup_problem = first.get("message") if isinstance(first, dict) else str(first)
            if startup_problem and not self._state["attention"] and summary["marking_available"] > 0:
                self._state["attention"].append(dict(
                    title="This assignment" if self._language == "en" else "这次任务",
                    message=("Marking could not start. Your essays are still ready; check the details before continuing."
                             if self._language == "en" else "批改未能开始，作文仍已准备好；请查看详情后继续。"),
                    details=f"MARKING_STARTUP_FAILED\n{startup_problem}",
                ))
            self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
            step = self._state["teacherFlow"]["step"]
            if error and step == "marking_start_failed":
                self._state["notice"] = ("Marking could not start. Your essays are still ready; check the details before continuing." if self._language == "en"
                                          else "批改未能开始；作文仍已准备好。请查看详情后继续。")
                self._state["executionError"] = "The marking run did not start. Check the details before continuing." if self._language == "en" else "批改未能开始，请查看详情后继续。"
            elif error:
                self._state["notice"] = ("Marking stopped before the batch finished. Read the task again to continue safely." if self._language == "en"
                                          else "批改未能完成。请重新读取任务后安全地继续。")
                self._state["executionError"] = "The marking run did not finish. Check the selected task before continuing." if self._language == "en" else "批改未能完成，请先检查任务再继续。"
            elif failures and step == "marking_start_failed":
                self._state["notice"] = ("Marking could not start. Your essays are still ready; check the details before continuing." if self._language == "en"
                                          else "批改未能开始；作文仍已准备好。请查看详情后继续。")
            elif failures:
                self._state["notice"] = ((f"{failures} essay(s) could not be marked. {saved} committed result(s) remain saved." if saved else
                                           f"{failures} essay(s) could not be marked. Check the task details before continuing.") if self._language == "en"
                                          else (f"有{failures}份作文未完成批改；已保存{saved}份已提交结果。" if saved else
                                                f"有{failures}份作文未完成批改；请先检查任务详情。"))
            elif result.get("interrupted"):
                self._state["notice"] = ("Marking paused. Essays not started will remain for Continue marking." if self._language == "en"
                                          else "批改已暂停；尚未开始的作文会保留，继续批改即可处理。")
            elif step == "review":
                self._state["notice"] = ("Teacher review is ready. The results workbook is saved." if self._language == "en"
                                          else "教师审核已就绪，批改结果工作簿已保存。")
            elif step == "resume_marking":
                self._state["notice"] = ("Saved progress was checked. The unfinished essays remain ready to mark." if self._language == "en"
                                          else "已核对保存进度；未完成的作文仍可继续批改。")
            elif step == "ready_to_mark":
                self._state["notice"] = ("The essays remain ready for marking." if self._language == "en"
                                          else "作文仍已准备好，可以开始批改。")
            else:
                self._state["notice"] = ("Saved marking records need attention before teacher review." if self._language == "en"
                                          else "保存的批改记录需要核对，暂不能进入教师审核。")
            self._real_state = deepcopy(self._state)
        else:
            self._state["notice"] = error or ("Marking could not start." if self._language == "en" else "无法开始批改。")
        self._busy = False
        self._task = None
        self._marking_started = None
        self._cancel_requested = False
        self.busyChanged.emit()
        self.changed.emit()

    @Slot()
    def generateFeedback(self):
        """Run only the currently advertised approved-row renderer action."""
        flow = self._state.get("teacherFlow", {})
        if (self._busy or self._source is None or self._state.get("demo")
                or not flow.get("primaryActionEnabled")
                or flow.get("primaryAction") != Action.RENDER_APPROVED.value):
            return
        total = max(0, int((self._state.get("summary") or {}).get("ready_to_render", 0)))
        if total == 0:
            return
        self._busy = True
        self.busyChanged.emit()
        self._rendering_started = time.monotonic()
        self._state["progress"] = {
            "operation": "render", "total": total, "completed": 0,
            "active": 0, "waiting": total, "attention": 0,
            "current": "", "elapsed": "0:00", "running": True,
            "saved": ("Approved Excel values are used. No grading or model call is made."
                      if self._language == "en" else "将使用已审核的 Excel 内容；不会批改作文或调用模型。"),
        }
        self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
        self._state["notice"] = ("Feedback-card generation has started." if self._language == "en"
                                  else "已开始生成作文体检卡。")
        self.changed.emit()
        task = RenderingTask(self._controller, self._source)
        task.signals.progress.connect(self._rendering_progress)
        task.signals.finished.connect(self._rendering_finished)
        self._task = task
        self.pool.start(task)

    @Slot(object)
    def _rendering_progress(self, progress):
        if not isinstance(progress, dict):
            return
        state = dict(progress)
        state["running"] = True
        elapsed = max(0, int(time.monotonic() - (self._rendering_started or time.monotonic())))
        state["elapsed"] = f"{elapsed // 60}:{elapsed % 60:02d}"
        count = int(state.get("completed", 0))
        state["saved"] = ((f"{count} verified feedback card(s) saved; no grading or model call is made."
                            if self._language == "en" else f"已核对并保存{count}张作文体检卡；没有批改作文或调用模型。"))
        self._state["progress"] = state
        self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
        self.changed.emit()

    @Slot(object, object, object, str)
    def _rendering_finished(self, inspection, source, outcome, error):
        reduced = self._state.get("reducedMotion", False)
        previous_progress = self._state.get("progress", {})
        elapsed = previous_progress.get("elapsed", "—")
        result = outcome if isinstance(outcome, dict) else {}
        if inspection is not None:
            title = task_title(source, self._language)
            self._state = set_section(project(inspection, source, title, self._language), 3, self._language)
            self._attach_identity_review(self._state, source, inspection)
            self._source, self._inspection = source, inspection
            successful_ids = {item.get("submission_id") for item in result.get("successes", ())}
            verified_ids = {item.submission_id for item in inspection.submissions if item.rendered}
            completed = len(successful_ids & verified_ids)
            failures = list(result.get("failed", ()))
            if error:
                failures.append({
                    "identity": {},
                    "message": ("Feedback generation did not complete. Approved Excel results remain unchanged; check the details and try again."
                                if self._language == "en" else "体检卡生成未完成；已审核的 Excel 内容保持不变。请查看详情后重试。"),
                    "error": error,
                })
            if failures:
                self._state["renderResult"] = {**result, "failed": failures}
            else:
                self._state["renderResult"] = result
            total = int(result.get("requested", previous_progress.get("total", 0)) or 0)
            attention_count = len(result.get("failed", ())) + (1 if error else 0)
            self._state["progress"] = {
                "operation": "render", "total": total, "completed": completed,
                "active": 0, "waiting": max(0, total - completed - attention_count),
                "attention": attention_count, "current": "", "elapsed": elapsed,
                "running": False,
                "saved": (f"{completed} feedback card(s) passed output checks."
                          if self._language == "en" else f"{completed}张体检卡已通过输出检查。"),
            }
            self._state["reducedMotion"] = reduced
            self._state["teacherFlow"] = derive_teacher_flow(self._state, self._language)
            if error:
                self._state["notice"] = ("Feedback generation did not finish. The approved workbook was not changed."
                                          if self._language == "en" else "体检卡生成未完成；审核工作簿没有被修改。")
            elif failures:
                self._state["notice"] = ((f"{completed} card(s) are saved. {len(failures)} still need attention; generated cards remain safe."
                                           if self._language == "en" else f"已保存{completed}张体检卡；还有{len(failures)}张未完成，已生成的卡片会保留。"))
            else:
                self._state["notice"] = ("Feedback cards are generated and verified." if self._language == "en"
                                          else "作文体检卡已生成并核对。")
            self._real_state = deepcopy(self._state)
        else:
            self._state["notice"] = error or ("Feedback generation could not be checked." if self._language == "en"
                                               else "体检卡生成结果无法核对。")
        self._busy = False
        self._task = None
        self._rendering_started = None
        self.busyChanged.emit()
        self.changed.emit()

    def shutdown(self):
        if isinstance(self._task, MarkingTask):
            self._task.request_stop()
        self.pool.waitForDone()
