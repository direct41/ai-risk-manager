from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import resource
import subprocess  # nosec B404
import sys
import tempfile
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUDGETS = REPO_ROOT / "performance" / "slo.json"


@dataclass(frozen=True)
class Workload:
    name: str
    source_files: int
    test_files: int

    @property
    def file_count(self) -> int:
        return self.source_files + self.test_files + 2


WORKLOADS = (
    Workload("small", source_files=40, test_files=8),
    Workload("medium", source_files=200, test_files=48),
    Workload("large", source_files=800, test_files=198),
)


@dataclass(frozen=True)
class Sample:
    wall_ms: float
    cpu_ms: float
    peak_rss_mb: float
    artifact_bytes: int
    graph_nodes: int
    findings: int


def _write_workload(root: Path, workload: Workload) -> None:
    app = root / "app"
    tests = root / "tests"
    app.mkdir(parents=True)
    tests.mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (tests / "__init__.py").write_text("", encoding="utf-8")
    for index in range(workload.source_files):
        method = "post" if index % 4 == 0 else "get"
        (app / f"route_{index:04d}.py").write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            f"@router.{method}('/items/{index}')\n"
            f"def item_{index}():\n"
            f"    return {{'id': {index}}}\n",
            encoding="utf-8",
        )
    for index in range(workload.test_files):
        (tests / f"test_route_{index:04d}.py").write_text(
            f"def test_route_{index}():\n    assert {index} >= 0\n",
            encoding="utf-8",
        )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one sample is required")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _peak_rss_mb(raw_peak_rss: int) -> float:
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return raw_peak_rss / divisor


def _worker(repo_path: Path, output_dir: Path) -> int:
    started = time.perf_counter()
    from ai_risk_manager.pipeline.run import run_pipeline
    from ai_risk_manager.pipeline.sinks import PipelineSinks
    from ai_risk_manager.schemas.types import RunContext

    class SilentProgress:
        def start(self, step: int, total: int, label: str) -> float:
            return time.perf_counter()

        def finish(self, step: int, total: int, label: str, started_at: float) -> float:
            return time.perf_counter() - started_at

    result, exit_code, notes = run_pipeline(
        RunContext(
            repo_path=repo_path,
            mode="full",
            base=None,
            output_dir=output_dir,
            provider="auto",
            no_llm=True,
            output_format="both",
            analysis_engine="deterministic",
        ),
        sinks=PipelineSinks(progress=SilentProgress()),
    )
    if result is None or exit_code != 0:
        print(json.dumps({"error": f"pipeline failed with exit code {exit_code}", "notes": notes}))
        return 1
    usage = resource.getrusage(resource.RUSAGE_SELF)
    artifact_bytes = sum(path.stat().st_size for path in output_dir.iterdir() if path.is_file())
    sample = Sample(
        wall_ms=(time.perf_counter() - started) * 1000,
        cpu_ms=(usage.ru_utime + usage.ru_stime) * 1000,
        peak_rss_mb=_peak_rss_mb(usage.ru_maxrss),
        artifact_bytes=artifact_bytes,
        graph_nodes=len(result.graph.nodes),
        findings=len(result.findings.findings),
    )
    print(json.dumps(asdict(sample), sort_keys=True))
    return 0


def _run_sample(repo_path: Path, output_dir: Path) -> Sample:
    started = time.perf_counter()
    proc = subprocess.run(  # nosec B603
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(repo_path), str(output_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    wall_ms = (time.perf_counter() - started) * 1000
    if proc.returncode != 0:
        raise RuntimeError(f"performance worker failed: {proc.stdout}{proc.stderr}")
    try:
        payload = json.loads(proc.stdout)
        worker_sample = Sample(**payload)
        return Sample(
            wall_ms=wall_ms,
            cpu_ms=worker_sample.cpu_ms,
            peak_rss_mb=worker_sample.peak_rss_mb,
            artifact_bytes=worker_sample.artifact_bytes,
            graph_nodes=worker_sample.graph_nodes,
            findings=worker_sample.findings,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(f"invalid performance worker output: {proc.stdout}") from exc


def _summarize(workload: Workload, samples: list[Sample]) -> dict[str, Any]:
    walls = [sample.wall_ms for sample in samples]
    cpus = [sample.cpu_ms for sample in samples]
    return {
        "file_count": workload.file_count,
        "repetitions": len(samples),
        "latency_ms": {
            "p50": round(_percentile(walls, 0.50), 2),
            "p95": round(_percentile(walls, 0.95), 2),
        },
        "cpu_ms": {
            "p50": round(_percentile(cpus, 0.50), 2),
            "p95": round(_percentile(cpus, 0.95), 2),
        },
        "peak_rss_mb": round(max(sample.peak_rss_mb for sample in samples), 2),
        "artifact_bytes": max(sample.artifact_bytes for sample in samples),
        "graph_nodes": samples[-1].graph_nodes,
        "findings": samples[-1].findings,
    }


def evaluate_budgets(report: dict[str, Any], budgets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for workload_name, limits in budgets["workloads"].items():
        metrics = report["workloads"].get(workload_name)
        if metrics is None:
            errors.append(f"missing workload result: {workload_name}")
            continue
        latency = metrics["latency_ms"]["p95"]
        memory = metrics["peak_rss_mb"]
        if latency > limits["p95_latency_ms"]:
            errors.append(
                f"{workload_name} p95 latency {latency:.2f}ms exceeds {limits['p95_latency_ms']:.2f}ms"
            )
        if memory > limits["peak_rss_mb"]:
            errors.append(f"{workload_name} peak RSS {memory:.2f}MB exceeds {limits['peak_rss_mb']:.2f}MB")
    return errors


def _load_budgets(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("workloads"), dict):
        raise ValueError("performance budget must contain a workloads object")
    return payload


def _run_suite(repetitions: int, budgets_path: Path, output_path: Path | None, enforce: bool) -> int:
    budgets = _load_budgets(budgets_path)
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="airisk-performance-") as raw_tmp:
        root = Path(raw_tmp)
        for workload in WORKLOADS:
            repo_path = root / workload.name / "repo"
            _write_workload(repo_path, workload)
            samples = [
                _run_sample(repo_path, root / workload.name / f"output-{index}")
                for index in range(repetitions)
            ]
            results[workload.name] = _summarize(workload, samples)

    report = {
        "schema_version": "1.0",
        "measurement": "cold Python process, deterministic full analysis, complete JSON and Markdown artifacts",
        "workloads": results,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    errors = evaluate_budgets(report, budgets) if enforce else []
    if errors:
        print("Performance gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if enforce:
        print("Performance gate passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic end-to-end performance workloads.")
    parser.add_argument("--worker", nargs=2, metavar=("REPO", "OUTPUT"), help=argparse.SUPPRESS)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--budgets", type=Path, default=DEFAULT_BUDGETS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(Path(args.worker[0]), Path(args.worker[1]))
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    try:
        return _run_suite(args.repetitions, args.budgets, args.output, args.enforce)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"Performance suite failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
