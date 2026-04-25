from __future__ import annotations

import re
import subprocess  # nosec B404
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = REPO_ROOT / ".github" / "public-artifacts-allowlist.txt"
MANIFEST_PATH = REPO_ROOT / "MANIFEST.in"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"

DISALLOWED_EXACT_PATHS = {
    "ALPHA.md",
    "RELEASE.md",
    "docs/roadmap.md",
    "docs/ui-flow-pilots.md",
    "uv.lock",
}
DISALLOWED_PREFIXES = (
    ".riskmap/",
    ".venv/",
    ".venv-min/",
    ".venv-min-local/",
    "build/",
    "dist/",
    "docs/launch/",
    "eval/.history/",
    "eval/results/",
    "htmlcov/",
)
GENERATED_ARTIFACT_BASENAMES = {
    "api_audit.json",
    "findings.json",
    "findings.raw.json",
    "github_check.json",
    "graph.analysis.json",
    "graph.deterministic.json",
    "graph.json",
    "merge_triage.json",
    "merge_triage.md",
    "pr_summary.json",
    "pr_summary.md",
    "report.md",
    "run_metrics.json",
    "test_plan.json",
}
REQUIRED_MANIFEST_LINES = {
    "prune docs",
    "prune eval",
    "prune examples",
    "prune scripts",
    "prune tests",
}
REQUIRED_GITIGNORE_LINES = {
    ".riskmap/",
    "eval/results/",
    "eval/.history/",
    "ALPHA.md",
    "RELEASE.md",
    "docs/roadmap.md",
    "docs/ui-flow-pilots.md",
    "docs/launch/",
}
TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_SCAN_SUFFIXES = TEXT_SUFFIXES | {
    ".crt",
    ".env",
    ".key",
    ".pem",
}
SECRET_SCAN_BASENAMES = {
    ".env",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
SECRET_PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)?PRIVATE KEY-----")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


def _repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _candidate_paths() -> list[str]:
    proc = subprocess.run(  # nosec B603
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(part.decode("utf-8") for part in proc.stdout.split(b"\0") if part)


def _load_allowlist(path: Path | None = None) -> set[str]:
    resolved_path = path or ALLOWLIST_PATH
    allowed: set[str] = set()
    for raw_line in resolved_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        allowed.add(line)
    return allowed


def _is_disallowed_path(path: str) -> bool:
    return path in DISALLOWED_EXACT_PATHS or any(path.startswith(prefix) for prefix in DISALLOWED_PREFIXES)


def _is_generated_artifact(path: str) -> bool:
    return Path(path).name in GENERATED_ARTIFACT_BASENAMES


def _is_guarded_public_doc(path: str) -> bool:
    return path.startswith("docs/") and path.endswith(".md")


def _read_required_lines(path: Path, required: set[str]) -> list[str]:
    lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines()}
    return sorted(item for item in required if item not in lines)


def _should_scan_for_secrets(path: str) -> bool:
    candidate = Path(path)
    name = candidate.name.lower()
    return (
        candidate.suffix.lower() in SECRET_SCAN_SUFFIXES
        or name in SECRET_SCAN_BASENAMES
        or name.startswith(".env.")
        or "/" not in path
    )


def _scan_for_secrets(path: str) -> list[str]:
    if not _should_scan_for_secrets(path):
        return []

    full_path = REPO_ROOT / path
    try:
        text = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(f"{path}: contains {label}")
    return findings


def check_public_artifacts() -> list[str]:
    failures: list[str] = []
    candidate_paths = _candidate_paths()
    allowlist = _load_allowlist()

    missing_manifest = _read_required_lines(MANIFEST_PATH, REQUIRED_MANIFEST_LINES)
    if missing_manifest:
        failures.append(f"MANIFEST.in is missing package-prune guard(s): {', '.join(missing_manifest)}")

    missing_gitignore = _read_required_lines(GITIGNORE_PATH, REQUIRED_GITIGNORE_LINES)
    if missing_gitignore:
        failures.append(f".gitignore is missing local/private artifact guard(s): {', '.join(missing_gitignore)}")

    unknown_allowlist_entries = sorted(path for path in allowlist if path not in candidate_paths)
    if unknown_allowlist_entries:
        failures.append("public artifact allowlist contains non-tracked path(s): " + ", ".join(unknown_allowlist_entries))

    for path in candidate_paths:
        if _is_disallowed_path(path):
            failures.append(f"{path}: local-only artifact is tracked")
        if _is_generated_artifact(path):
            failures.append(f"{path}: generated risk-analysis artifact is tracked")
        if _is_guarded_public_doc(path) and path not in allowlist:
            failures.append(f"{path}: public docs file is not listed in {_repo_relative(ALLOWLIST_PATH)}")
        failures.extend(_scan_for_secrets(path))

    return failures


def main() -> int:
    failures = check_public_artifacts()
    if not failures:
        print("Public artifact gate passed.")
        return 0

    print("Public artifact gate failed:")
    for failure in failures:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
