from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_risk_manager.schemas.types import Severity


class AnalyzeRequest(BaseModel):
    path: str = "."
    mode: Literal["full", "pr"] = "full"
    base: str = "main"
    no_llm: bool = False
    provider: Literal["auto", "api", "cli"] = "auto"
    baseline_graph: str | None = None
    output_dir: str = ".riskmap"
    output_format: Literal["md", "json", "both"] = Field(default="both", alias="format")
    fail_on_severity: Severity | None = None
    suppress_file: str | None = None
    sample: bool = False

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class AnalyzeResponse(BaseModel):
    exit_code: int
    notes: list[str]
    output_dir: str
    artifacts: dict[str, str]
    result: dict[str, Any] | None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
