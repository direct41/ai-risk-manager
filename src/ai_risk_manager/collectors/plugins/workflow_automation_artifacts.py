from __future__ import annotations

from pathlib import Path
import re

_WORKFLOW_SUFFIXES = {".yml", ".yaml"}
_UNTRUSTED_CONTEXT_RE = re.compile(
    r"\$\{\{\s*github\.event\.(?:pull_request|issue|comment|discussion)"
    r"\.(?:title|body|message|.*body)\s*\}\}",
    re.IGNORECASE,
)
_USES_RE = re.compile(r"^\s*uses:\s*(?P<value>\S+)\s*$")
_STEP_NAME_RE = re.compile(r"^\s*-\s*name:\s*(?P<name>.+?)\s*$")
_RUN_START_RE = re.compile(r"^\s*run:\s*(?P<inline>.*)$")
_SHA_PIN_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _line_snippet(source_lines: list[str], line: int, *, window: int = 4) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _workflow_files(all_files: list[Path]) -> list[Path]:
    return [
        path
        for path in all_files
        if path.suffix.lower() in _WORKFLOW_SUFFIXES and ".github" in path.parts and "workflows" in path.parts
    ]


def _step_name_before(lines: list[str], idx: int) -> str | None:
    for offset in range(idx, max(-1, idx - 6), -1):
        match = _STEP_NAME_RE.match(lines[offset])
        if match:
            return match.group("name").strip().strip("'\"")
    return None


def _is_external_action_ref(ref: str) -> bool:
    if ref.startswith("./") or ref.startswith("docker://"):
        return False
    return "@" in ref and "/" in ref


def collect_workflow_automation_issues(
    repo_path: Path,
    all_files: list[Path],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    workflow_files = _workflow_files(all_files)

    for path in workflow_files:
        text = _read_text(path)
        if not text:
            continue
        lines = text.splitlines()
        relative = str(path.relative_to(repo_path))

        for idx, raw_line in enumerate(lines):
            line_no = idx + 1
            uses_match = _USES_RE.match(raw_line)
            if uses_match:
                raw_ref = uses_match.group("value").strip().strip("'\"")
                if _is_external_action_ref(raw_ref):
                    _, ref = raw_ref.rsplit("@", 1)
                    if not _SHA_PIN_RE.fullmatch(ref):
                        step_name = _step_name_before(lines, idx) or "workflow step"
                        issues.append(
                            (
                                relative,
                                "external_action_not_pinned",
                                step_name,
                                line_no,
                                _line_snippet(lines, line_no),
                                {
                                    "action_ref": raw_ref,
                                },
                            )
                        )
                continue

            run_match = _RUN_START_RE.match(raw_line)
            if run_match is None:
                continue

            block_lines = [run_match.group("inline")] if run_match.group("inline").strip() else []
            base_indent = len(raw_line) - len(raw_line.lstrip(" "))
            j = idx + 1
            while j < len(lines):
                candidate = lines[j]
                if not candidate.strip():
                    block_lines.append(candidate)
                    j += 1
                    continue
                indent = len(candidate) - len(candidate.lstrip(" "))
                if indent <= base_indent:
                    break
                block_lines.append(candidate)
                j += 1

            body = "\n".join(block_lines)
            if not _UNTRUSTED_CONTEXT_RE.search(body):
                continue
            step_name = _step_name_before(lines, idx) or "workflow step"
            issues.append(
                (
                    relative,
                    "untrusted_context_to_shell",
                    step_name,
                    line_no,
                    _line_snippet(lines, line_no),
                    {
                        "context_ref": _UNTRUSTED_CONTEXT_RE.search(body).group(0),
                    },
                )
            )

    return issues


__all__ = ["collect_workflow_automation_issues"]
