from collections import deque
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any, cast
import uuid

from ai_risk_manager import __version__
from ai_risk_manager.pipeline.context_builder import build_run_context
from ai_risk_manager.pipeline.run import run_pipeline
from ai_risk_manager.sample_repo import resolve_sample_repo_path
from ai_risk_manager.schemas.types import to_dict

_API_INSTALL_HINT = "Install API dependencies with: pip install -e '.[api]'."
_API_IMPORT_ERROR: Exception | None = None
_FastAPI: Any = None
_HTTPException: Any = None
_Body: Any = None
_Header: Any = None
_AnalyzeRequest: Any = None
_AnalyzeResponse: Any = None
_HealthResponse: Any = None
_RATE_LIMIT_STATE: dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_AUDIT_LOCK = threading.Lock()

if TYPE_CHECKING:
    from fastapi import FastAPI as FastAPIApp
else:
    FastAPIApp = Any

try:
    from fastapi import FastAPI as FastAPIImport
    from fastapi import HTTPException as HTTPExceptionImport
    from fastapi import Body as BodyImport
    from fastapi import Header as HeaderImport
    from ai_risk_manager.api.models import AnalyzeRequest as AnalyzeRequestImport
    from ai_risk_manager.api.models import AnalyzeResponse as AnalyzeResponseImport
    from ai_risk_manager.api.models import HealthResponse as HealthResponseImport
    _FastAPI = FastAPIImport
    _HTTPException = HTTPExceptionImport
    _Body = BodyImport
    _Header = HeaderImport
    _AnalyzeRequest = AnalyzeRequestImport
    _AnalyzeResponse = AnalyzeResponseImport
    _HealthResponse = HealthResponseImport
except Exception as exc:  # pragma: no cover - exercised in minimal installs without API extras.
    _API_IMPORT_ERROR = exc

_ARTIFACT_FILES = (
    "api_audit.json",
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


def _load_api_dependencies() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    if _API_IMPORT_ERROR is not None:
        raise _missing_dependency_error(_API_IMPORT_ERROR) from _API_IMPORT_ERROR
    return _FastAPI, _HTTPException, _Body, _Header, _AnalyzeRequest, _AnalyzeResponse, _HealthResponse


def _configured_api_token() -> str | None:
    token = os.getenv("AIRISK_API_TOKEN", "").strip()
    return token or None


def _configured_rate_limit_per_minute() -> int:
    raw = os.getenv("AIRISK_API_RATE_LIMIT_PER_MINUTE", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def _configured_max_body_bytes() -> int:
    raw = os.getenv("AIRISK_API_MAX_BODY_BYTES", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def _configured_audit_log_path() -> Path | None:
    raw = os.getenv("AIRISK_API_AUDIT_LOG", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _rate_limit_key(x_forwarded_for: str | None) -> str:
    if not x_forwarded_for:
        return "anonymous"
    first = x_forwarded_for.split(",", 1)[0].strip()
    return first or "anonymous"


def _enforce_rate_limit(*, limit_per_minute: int, x_forwarded_for: str | None, http_exception_cls: Any) -> None:
    if limit_per_minute <= 0:
        return
    key = _rate_limit_key(x_forwarded_for)
    now = time.monotonic()
    window_seconds = 60.0
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_STATE.setdefault(key, deque())
        while bucket and (now - bucket[0]) >= window_seconds:
            bucket.popleft()
        if len(bucket) >= limit_per_minute:
            raise http_exception_cls(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)


def _enforce_payload_size(*, max_body_bytes: int, payload: dict[str, Any], http_exception_cls: Any) -> None:
    if max_body_bytes <= 0:
        return
    body_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if body_size > max_body_bytes:
        raise http_exception_cls(status_code=413, detail="Payload too large")


def _resolve_correlation_id(x_correlation_id: str | None, x_request_id: str | None) -> str:
    raw = (x_correlation_id or x_request_id or "").strip()
    if raw:
        normalized = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_", "."})
        if normalized:
            return normalized[:64]
    return uuid.uuid4().hex


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_failure_diagnostics(exc: Exception, correlation_id: str) -> dict[str, str]:
    seed = f"{exc.__class__.__name__}:{exc}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return {
        "diagnostic_id": f"diag-{digest}",
        "correlation_id": correlation_id,
        "error_type": exc.__class__.__name__,
    }


def _diagnostic_error_detail(exc: Exception) -> str:
    tb = "".join(traceback.format_exception(exc.__class__, exc, exc.__traceback__, limit=8))
    return tb[:2000]


def _sanitize_error_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail[:500]
    try:
        return json.dumps(detail, ensure_ascii=False, separators=(",", ":"))[:500]
    except TypeError:
        return str(detail)[:500]


def _write_audit_event(
    *,
    started_at: float,
    correlation_id: str,
    status: str,
    http_status: int,
    request_payload: dict[str, Any],
    output_dir: Path | None,
    exit_code: int | None = None,
    error_detail: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    request_view = {
        "path": request_payload.get("path", "."),
        "mode": request_payload.get("mode", "full"),
        "provider": request_payload.get("provider", "auto"),
        "analysis_engine": request_payload.get("analysis_engine", "ai_first"),
        "no_llm": bool(request_payload.get("no_llm", False)),
    }
    payload = {
        "timestamp": _utc_now_iso(),
        "correlation_id": correlation_id,
        "status": status,
        "http_status": http_status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "request": request_view,
        "output_dir": str(output_dir) if output_dir is not None else None,
    }
    if error_detail:
        payload["error_detail"] = error_detail
    if diagnostics:
        payload["diagnostics"] = diagnostics

    if output_dir is not None:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "api_audit.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            pass

    audit_log_path = _configured_audit_log_path()
    if audit_log_path is None:
        return
    try:
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with _AUDIT_LOCK:
            with audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{line}\n")
    except OSError:
        pass


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def _enforce_api_auth(
    *,
    expected_token: str | None,
    x_api_key: str | None,
    authorization: str | None,
    http_exception_cls: Any,
) -> None:
    if expected_token is None:
        return
    provided_token = (x_api_key or "").strip() or (_extract_bearer_token(authorization) or "")
    if provided_token != expected_token:
        raise http_exception_cls(status_code=401, detail="Unauthorized")


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
    FastAPI, HTTPException, Body, Header, AnalyzeRequestModel, AnalyzeResponseModel, HealthResponseModel = (
        _load_api_dependencies()
    )
    app = FastAPI(title="AI Risk Manager API", version=__version__)

    @app.get("/healthz", response_model=HealthResponseModel)
    def healthz() -> Any:
        return HealthResponseModel(status="ok", version=__version__)

    @app.post("/v1/analyze", response_model=AnalyzeResponseModel)
    def analyze(
        request_payload: dict[str, Any] = Body(...),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_forwarded_for: str | None = Header(default=None, alias="X-Forwarded-For"),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
        x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> Any:
        started_at = time.perf_counter()
        correlation_id = _resolve_correlation_id(x_correlation_id, x_request_id)

        try:
            request = cast(Any, AnalyzeRequestModel.model_validate(request_payload))
        except Exception as exc:
            errors = getattr(exc, "errors", None)
            if callable(errors):
                detail = errors()
                _write_audit_event(
                    started_at=started_at,
                    correlation_id=correlation_id,
                    status="validation_error",
                    http_status=422,
                    request_payload=request_payload,
                    output_dir=None,
                    error_detail=_sanitize_error_detail(detail),
                )
                raise HTTPException(status_code=422, detail=detail) from exc
            raise

        try:
            _enforce_api_auth(
                expected_token=_configured_api_token(),
                x_api_key=x_api_key,
                authorization=authorization,
                http_exception_cls=HTTPException,
            )
            _enforce_rate_limit(
                limit_per_minute=_configured_rate_limit_per_minute(),
                x_forwarded_for=x_forwarded_for,
                http_exception_cls=HTTPException,
            )
            _enforce_payload_size(
                max_body_bytes=_configured_max_body_bytes(),
                payload=request_payload,
                http_exception_cls=HTTPException,
            )
        except HTTPException as exc:
            _write_audit_event(
                started_at=started_at,
                correlation_id=correlation_id,
                status="request_rejected",
                http_status=exc.status_code,
                request_payload=request_payload,
                output_dir=None,
                error_detail=_sanitize_error_detail(exc.detail),
            )
            raise

        try:
            repo_path = _resolve_repo_path(request.path, request.sample)
        except (FileNotFoundError, ValueError) as exc:
            _write_audit_event(
                started_at=started_at,
                correlation_id=correlation_id,
                status="invalid_repo_path",
                http_status=400,
                request_payload=request_payload,
                output_dir=None,
                error_detail=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        output_dir = Path(request.output_dir).resolve()
        baseline_graph = Path(request.baseline_graph).resolve() if request.baseline_graph else None
        suppress_file = Path(request.suppress_file).resolve() if request.suppress_file else None

        try:
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
        except Exception as exc:
            diagnostics = _build_failure_diagnostics(exc, correlation_id)
            _write_audit_event(
                started_at=started_at,
                correlation_id=correlation_id,
                status="internal_error",
                http_status=500,
                request_payload=request_payload,
                output_dir=output_dir,
                diagnostics=diagnostics,
                error_detail=_diagnostic_error_detail(exc),
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Internal server error",
                    "correlation_id": correlation_id,
                    "diagnostic_id": diagnostics["diagnostic_id"],
                },
            ) from exc

        success_diagnostics: dict[str, Any] = {
            "status": "completed",
            "duration_ms": int((time.perf_counter() - started_at) * 1000),
        }
        notes = [f"correlation_id={correlation_id}", *notes]
        _write_audit_event(
            started_at=started_at,
            correlation_id=correlation_id,
            status="completed",
            http_status=200,
            request_payload=request_payload,
            output_dir=output_dir,
            exit_code=exit_code,
            diagnostics=success_diagnostics,
        )
        return AnalyzeResponseModel(
            exit_code=exit_code,
            notes=notes,
            output_dir=str(output_dir),
            artifacts=_collect_artifacts(output_dir),
            result=to_dict(result) if result is not None else None,
            summary=to_dict(result.summary) if result is not None else None,
            correlation_id=correlation_id,
            diagnostics=success_diagnostics,
        )

    return app


app: Any

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
