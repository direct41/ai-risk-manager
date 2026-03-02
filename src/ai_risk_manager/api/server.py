from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_risk_manager import __version__
from ai_risk_manager.pipeline.context_builder import build_run_context
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.sample_repo import resolve_sample_repo_path
from ai_risk_manager.schemas.types import to_dict

_API_INSTALL_HINT = "Install API dependencies with: pip install -e '.[api]'."
_API_IMPORT_ERROR: Exception | None = None
_FastAPI: Any = None
_HTTPException: Any = None
_AnalyzeRequest: Any = None
_AnalyzeResponse: Any = None
_HealthResponse: Any = None

if TYPE_CHECKING:
    from fastapi import FastAPI as FastAPIApp
else:
    FastAPIApp = Any

try:
    from fastapi import FastAPI as FastAPIImport
    from fastapi import HTTPException as HTTPExceptionImport
    from ai_risk_manager.api.models import AnalyzeRequest as AnalyzeRequestImport
    from ai_risk_manager.api.models import AnalyzeResponse as AnalyzeResponseImport
    from ai_risk_manager.api.models import HealthResponse as HealthResponseImport
    _FastAPI = FastAPIImport
    _HTTPException = HTTPExceptionImport
    _AnalyzeRequest = AnalyzeRequestImport
    _AnalyzeResponse = AnalyzeResponseImport
    _HealthResponse = HealthResponseImport
except Exception as exc:  # pragma: no cover - exercised in minimal installs without API extras.
    _API_IMPORT_ERROR = exc

_ARTIFACT_FILES = (
    "graph.json",
    "graph.analysis.json",
    "graph.deterministic.json",
    "findings.raw.json",
    "findings.json",
    "test_plan.json",
    "run_metrics.json",
    "report.md",
    "pr_summary.md",
)


class ApiDependencyError(RuntimeError):
    """Raised when optional API dependencies are unavailable."""


def _missing_dependency_error(exc: Exception) -> ApiDependencyError:
    return ApiDependencyError(f"API adapter is unavailable ({exc.__class__.__name__}: {exc}). {_API_INSTALL_HINT}")


def _load_api_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    if _API_IMPORT_ERROR is not None:
        raise _missing_dependency_error(_API_IMPORT_ERROR) from _API_IMPORT_ERROR
    return _FastAPI, _HTTPException, _AnalyzeRequest, _AnalyzeResponse, _HealthResponse


def _resolve_repo_path(path: str, sample: bool) -> Path:
    if sample:
        return resolve_sample_repo_path()

    repo_path = Path(path).resolve()
    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo_path}")
    return repo_path


def _collect_artifacts(output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for filename in _ARTIFACT_FILES:
        path = output_dir / filename
        if path.is_file():
            artifacts[filename] = str(path)
    return artifacts


def create_app() -> FastAPIApp:
    FastAPI, HTTPException, AnalyzeRequest, AnalyzeResponse, HealthResponse = _load_api_dependencies()
    app = FastAPI(title="AI Risk Manager API", version=__version__)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> Any:
        return HealthResponse(status="ok", version=__version__)

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    def analyze(request: Any) -> Any:
        try:
            repo_path = _resolve_repo_path(request.path, request.sample)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        output_dir = Path(request.output_dir).resolve()
        baseline_graph = Path(request.baseline_graph).resolve() if request.baseline_graph else None
        suppress_file = Path(request.suppress_file).resolve() if request.suppress_file else None

        ctx = build_run_context(
            repo_path=repo_path,
            mode=request.mode,
            base=request.base,
            output_dir=output_dir,
            provider=request.provider,
            no_llm=request.no_llm,
            output_format=request.output_format,
            fail_on_severity=request.fail_on_severity,
            suppress_file=suppress_file,
            baseline_graph=baseline_graph,
            analysis_engine=request.analysis_engine,
            only_new=request.only_new,
            min_confidence=request.min_confidence,
            ci_mode=request.ci_mode,
            support_level=request.support_level,
            risk_policy=request.risk_policy,
        )

        result, exit_code, notes = run_pipeline(ctx)
        return AnalyzeResponse(
            exit_code=exit_code,
            notes=notes,
            output_dir=str(output_dir),
            artifacts=_collect_artifacts(output_dir),
            result=to_dict(result) if result is not None else None,
            summary=to_dict(result.summary) if result is not None else None,
        )

    return app


try:
    app = create_app()
except ApiDependencyError:
    app = None


def app_entry() -> None:
    try:
        import uvicorn
    except Exception as exc:
        raise SystemExit(str(_missing_dependency_error(exc))) from exc

    try:
        api_app = app if app is not None else create_app()
    except ApiDependencyError as exc:
        raise SystemExit(str(exc)) from exc

    host = os.getenv("AIRISK_API_HOST", "127.0.0.1")
    port = int(os.getenv("AIRISK_API_PORT", "8000"))
    uvicorn.run(api_app, host=host, port=port)
