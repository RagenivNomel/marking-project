"""The application boundary for one registered workflow."""
from .models import AssignmentSource


class WorkflowController:
    def __init__(self, workflow_id="sec2_hcl_composition_v1", *, project_dir=None,
                 pipeline_factory=None, render_pipeline_factory=None):
        from .workflows.registry import get_workflow
        from app_paths import data_root
        workflow_class = get_workflow(workflow_id).workflow_class
        self.workflow = workflow_class(
            project_dir=project_dir or data_root(),
            pipeline_factory=pipeline_factory,
            render_pipeline_factory=render_pipeline_factory,
        )

    def inspect(self, source: AssignmentSource):
        return self.workflow.inspect(source)

    def prepare_source(self, source: AssignmentSource):
        """Prepare a raw continuous scan before the read-only inspection."""
        return self.workflow.prepare_source(source)

    def bind_source(self, source: AssignmentSource):
        """Return deterministic app-owned result paths when they already exist."""
        return self.workflow.marking_source(source)

    def refresh_review_status(self, source: AssignmentSource):
        """Re-read saved evidence; does not save, approve, repair, or cache it."""
        return self.inspect(source)

    def execute(self, action, source: AssignmentSource, *, progress_callback=None,
                cancelled=None):
        from .models import Action
        try:
            action = action if isinstance(action, Action) else Action(str(action))
        except (TypeError, ValueError):
            raise NotImplementedError("Only the supported Stage 3B/3C actions are executable.") from None
        if action == Action.RUN_MARKING:
            return self.workflow.execute_marking(
                source, progress_callback=progress_callback,
                cancelled=cancelled,
            )
        if action == Action.RENDER_APPROVED:
            return self.workflow.execute_feedback_generation(
                source, progress_callback=progress_callback,
            )
        raise NotImplementedError(f"{action.value} has no execution path in the current stage.")
