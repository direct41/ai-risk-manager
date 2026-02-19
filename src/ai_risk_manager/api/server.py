from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from ai_risk_manager import __version__
from ai_risk_manager.api.models import AnalyzeRequest, AnalyzeResponse, HealthResponse
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.schemas.types import RunContext, to_dict

_ARTIFACT_FILES = (
    "graph.json",
    "findings.raw.json",
    "findings.json",
    "test_plan.json",
    "report.md",
    "pr_summary.md",
)


def _resolve_sample_repo() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "eval" / "repos" / "milestone2_fastapi"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("Bundled sample repository not found")


def _resolve_repo_path(request: AnalyzeRequest) -> Path:
    if request.sample:
        try:
            return _resolve_sample_repo().resolve()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo_path = Path(request.path).resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Repository path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Repository path is not a directory: {repo_path}")
    return repo_path


def _collect_artifacts(output_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for filename in _ARTIFACT_FILES:
        path = output_dir / filename
        if path.is_file():
            artifacts[filename] = str(path)
    return artifacts


def create_app() -> FastAPI:
    app = FastAPI(title="AI Risk Manager API", version=__version__)

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
        repo_path = _resolve_repo_path(request)
        output_dir = Path(request.output_dir).resolve()
        baseline_graph = Path(request.baseline_graph).resolve() if request.baseline_graph else None
        suppress_file = Path(request.suppress_file).resolve() if request.suppress_file else None

        ctx = RunContext(
            repo_path=repo_path,
            mode=request.mode,
            base=request.base if request.mode == "pr" else None,
            output_dir=output_dir,
            provider=request.provider,
            no_llm=request.no_llm,
            output_format=request.output_format,
            fail_on_severity=request.fail_on_severity,
            suppress_file=suppress_file,
            baseline_graph=baseline_graph,
        )

        result, exit_code, notes = run_pipeline(ctx)
        return AnalyzeResponse(
            exit_code=exit_code,
            notes=notes,
            output_dir=str(output_dir),
            artifacts=_collect_artifacts(output_dir),
            result=to_dict(result) if result is not None else None,
        )

    return app


app = create_app()


def app_entry() -> None:
    import uvicorn

    host = os.getenv("AIRISK_API_HOST", "127.0.0.1")
    port = int(os.getenv("AIRISK_API_PORT", "8000"))
    uvicorn.run("ai_risk_manager.api.server:app", host=host, port=port)
