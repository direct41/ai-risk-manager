from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from shutil import which
import subprocess  # nosec B404
import time
from typing import Protocol

from ai_risk_manager import __version__
from ai_risk_manager.reports.generator import (
    build_github_check_payload,
    build_pr_summary,
    render_pr_summary_md,
    render_report_md,
    write_report,
)
from ai_risk_manager.schemas.types import PipelineResult, RunContext, to_dict, write_json
from ai_risk_manager.triage.merge import render_merge_triage_md


class ProgressSink(Protocol):
    def start(self, step: int, total: int, label: str) -> float:
        ...

    def finish(self, step: int, total: int, label: str, started_at: float) -> float:
        ...


class ChangedFilesSink(Protocol):
    def resolve(self, repo_path: Path, base: str | None) -> set[str] | None:
        ...


class EnvironmentSink(Protocol):
    def is_ci(self) -> bool:
        ...


class ArtifactSink(Protocol):
    def write(
        self,
        *,
        ctx: RunContext,
        result: PipelineResult,
        notes: list[str],
        changed_files: set[str] | None = None,
    ) -> list[str]:
        ...


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _with_metadata(payload: dict, generated_at: str) -> dict:
    return {
        **payload,
        "schema_version": "1.1",
        "generated_at": generated_at,
        "tool_version": __version__,
    }


def _git_executable() -> str | None:
    return which("git")


def _safe_diff_base(base: str) -> str | None:
    normalized = base.strip()
    if not normalized or normalized.startswith("-") or "\x00" in normalized:
        return None
    return normalized


class ConsoleProgressSink:
    def start(self, step: int, total: int, label: str) -> float:
        print(f"[{step}/{total}] {label} ...", flush=True)
        return time.perf_counter()

    def finish(self, step: int, total: int, label: str, started_at: float) -> float:
        elapsed = time.perf_counter() - started_at
        print(f"[{step}/{total}] {label} ... done ({elapsed:.1f}s)", flush=True)
        return elapsed


class GitChangedFilesSink:
    def resolve(self, repo_path: Path, base: str | None) -> set[str] | None:
        env_override = os.getenv("AIRISK_CHANGED_FILES", "").strip()
        if env_override:
            return {_normalize_path(part.strip()) for part in env_override.split(",") if part.strip()}

        if not base:
            return None

        safe_base = _safe_diff_base(base)
        git = _git_executable()
        if safe_base is None or git is None:
            return None

        candidate_refs = [f"{safe_base}...HEAD", f"origin/{safe_base}...HEAD"]
        for ref in candidate_refs:
            try:
                # Git path is resolved and shell=False; ref is sanitized.
                proc = subprocess.run(  # nosec B603
                    [git, "-C", str(repo_path), "diff", "--name-only", "--diff-filter=ACMRTUXB", ref, "--"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode == 0:
                lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
                return {_normalize_path(line) for line in lines}
        return None


class OsEnvironmentSink:
    def is_ci(self) -> bool:
        return bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS"))


class LocalArtifactSink:
    def write(
        self,
        *,
        ctx: RunContext,
        result: PipelineResult,
        notes: list[str],
        changed_files: set[str] | None = None,
    ) -> list[str]:
        output_notes: list[str] = []
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if ctx.output_format in {"json", "both"}:
            write_json(ctx.output_dir / "graph.json", _with_metadata(to_dict(result.graph), generated_at))
            write_json(ctx.output_dir / "graph.analysis.json", _with_metadata(to_dict(result.graph), generated_at))
            write_json(
                ctx.output_dir / "graph.deterministic.json",
                _with_metadata(to_dict(result.deterministic_graph), generated_at),
            )
            if result.analysis_scope != "full":
                output_notes.append("graph.json contains analysis graph for current scope (not full repository graph).")
            if result.summary.graph_mode_applied == "enriched":
                output_notes.append(
                    "graph.json/graph.analysis.json are enriched by semantic signals; "
                    "graph.deterministic.json preserves the deterministic graph."
                )
            write_json(ctx.output_dir / "findings.raw.json", _with_metadata(to_dict(result.findings_raw), generated_at))
            write_json(ctx.output_dir / "findings.json", _with_metadata(to_dict(result.findings), generated_at))
            write_json(ctx.output_dir / "test_plan.json", _with_metadata(to_dict(result.test_plan), generated_at))
            write_json(ctx.output_dir / "merge_triage.json", _with_metadata(to_dict(result.merge_triage), generated_at))
            write_json(ctx.output_dir / "run_metrics.json", _with_metadata(to_dict(result.run_metrics), generated_at))
            if ctx.mode == "pr":
                pr_summary = build_pr_summary(
                    result,
                    notes + output_notes,
                    only_new=ctx.only_new,
                    changed_files=changed_files,
                )
                write_json(ctx.output_dir / "pr_summary.json", _with_metadata(to_dict(pr_summary), generated_at))
                github_check = build_github_check_payload(pr_summary)
                write_json(ctx.output_dir / "github_check.json", _with_metadata(to_dict(github_check), generated_at))

        if ctx.output_format in {"md", "both"}:
            report = render_report_md(result, notes + output_notes)
            write_report(ctx.output_dir / "report.md", report)
            write_report(ctx.output_dir / "merge_triage.md", render_merge_triage_md(result.merge_triage))
            if ctx.mode == "pr":
                pr_summary = build_pr_summary(
                    result,
                    notes + output_notes,
                    only_new=ctx.only_new,
                    changed_files=changed_files,
                )
                write_report(ctx.output_dir / "pr_summary.md", render_pr_summary_md(pr_summary))

        return output_notes


@dataclass
class PipelineSinks:
    progress: ProgressSink = field(default_factory=ConsoleProgressSink)
    changed_files: ChangedFilesSink = field(default_factory=GitChangedFilesSink)
    environment: EnvironmentSink = field(default_factory=OsEnvironmentSink)
    artifacts: ArtifactSink = field(default_factory=LocalArtifactSink)
