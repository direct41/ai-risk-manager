from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ai_risk_manager.schemas.types import PreflightResult

StackId = Literal["fastapi_pytest", "unknown"]


@dataclass
class ArtifactBundle:
    all_files: list[Path] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    write_endpoints: list[tuple[str, str]] = field(default_factory=list)  # (file, endpoint_name)
    endpoint_models: list[tuple[str, str, str]] = field(default_factory=list)  # (file, endpoint_name, model_name)
    pydantic_models: list[tuple[str, str]] = field(default_factory=list)  # (file, model_name)
    declared_transitions: list[tuple[str, str, str, str]] = field(default_factory=list)  # (file, machine, src, dst)
    handled_transitions: list[tuple[str, str, str, str]] = field(default_factory=list)  # (file, machine, src, dst)
    test_files: list[Path] = field(default_factory=list)
    test_cases: list[tuple[str, str]] = field(default_factory=list)  # (file, test_function_name)


class CollectorPlugin(Protocol):
    stack_id: StackId

    def preflight(self, repo_path: Path) -> PreflightResult:
        ...

    def collect(self, repo_path: Path) -> ArtifactBundle:
        ...
