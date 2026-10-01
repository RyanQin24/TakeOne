"""Every editor failure names the stage that produced it. Nothing fails silently."""


class EditorError(Exception):
    """Base class. `stage` is the pipeline stage, `code` is stable for the UI."""

    stage = "editor"
    code = "editor_error"

    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = detail or {}

    def wire(self):
        return {"stage": self.stage, "code": self.code, "message": str(self), "detail": self.detail}


class ValidationError(EditorError, ValueError):
    stage = "validation"
    code = "invalid_input"


class OperationError(EditorError):
    stage = "reducer"
    code = "operation_rejected"


class GraphError(EditorError):
    stage = "graph"
    code = "invalid_graph"


class CompileError(EditorError):
    stage = "compile"
    code = "compile_failed"


class RenderError(EditorError):
    stage = "render"
    code = "render_failed"


class AnalysisError(EditorError):
    stage = "analysis"
    code = "analysis_failed"


class PlanError(EditorError):
    stage = "plan"
    code = "plan_rejected"


class RegistryError(EditorError):
    stage = "registry"
    code = "registry_conflict"


class MigrationError(EditorError):
    stage = "project"
    code = "unsupported_schema"
