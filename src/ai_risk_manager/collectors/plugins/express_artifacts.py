from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from ai_risk_manager.collectors.plugins.base import ArtifactBundle, IngressCoverageArtifact, IngressSurfaceArtifact
from ai_risk_manager.collectors.plugins.dependency_artifacts import extract_dependency_specs

WRITE_METHODS = ("post", "put", "patch", "delete")
JS_SUFFIXES = {".js", ".cjs", ".mjs", ".ts", ".tsx"}
CSS_SUFFIXES = {".css"}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".riskmap",
    "eval",
    "fixtures",
    "testdata",
    "dist",
    "build",
    "coverage",
}
_EXPRESS_IMPORT_RE = re.compile(r"(?:require\(\s*['\"]express['\"]\s*\))|(?:from\s+['\"]express['\"])", re.IGNORECASE)
_ROUTE_CALL_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_$][A-Za-z0-9_$]*)\.(?P<method>post|put|patch|delete)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<path>[^'\"`]+)(?P=quote)\s*(?:,\s*(?P<handler>[A-Za-z_$][A-Za-z0-9_$]*))?",
    re.IGNORECASE,
)
_TEST_CALL_RE = re.compile(
    r"\.(?P<method>post|put|patch|delete)\s*\(\s*(?P<quote>['\"`])(?P<path>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_TEST_CASE_RE = re.compile(
    r"\b(?:test|it)\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_TEST_HINT_RE = re.compile(r"\b(?:describe|it|test)\s*\(", re.IGNORECASE)
_APP_USE_PREFIX_RE = re.compile(r"\bapp\.use\s*\(\s*(?P<quote>['\"`])(?P<prefix>/[^'\"`]*)?(?P=quote)\s*,", re.IGNORECASE)
_AUTH_HINT_RE = re.compile(
    r"(req\.(?:header|get)\s*\(|authorization|x-session-token|x-api-key|bearer|token)",
    re.IGNORECASE,
)
_AUTH_DENY_RE = re.compile(r"(status\s*\(\s*(401|403)\s*\)|unauthori[sz]ed|forbidden)", re.IGNORECASE)
_DB_RUN_INSERT_RE = re.compile(
    r"db\.run\(\s*`(?P<sql>\s*INSERT[\s\S]*?)`\s*,\s*\[(?P<args>[\s\S]*?)\]\s*,?\s*\)",
    re.IGNORECASE,
)
_DB_RUN_UPDATE_RE = re.compile(
    r"db\.run\(\s*`(?P<sql>\s*UPDATE[\s\S]*?)`\s*,\s*\[(?P<args>[\s\S]*?)\]\s*,?\s*\)",
    re.IGNORECASE,
)
_FUNCTION_HEADER_RE = re.compile(
    r"\b(?:async\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\((?P<params>[^)]*)\)",
    re.IGNORECASE,
)
_INPUT_CHAR_SPLIT_RE = re.compile(
    r"input\.(?P<field>[A-Za-z_$][A-Za-z0-9_$]*)[^\n;]*?\.split\(\s*(?P<quote>['\"])\s*(?P=quote)\s*\)",
    re.IGNORECASE,
)
_ROW_FIELD_RE = re.compile(r"\b(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*[^,\n]*\brow\.", re.MULTILINE)
_NOTE_FIELD_RE = re.compile(r"\bnote\.(?P<field>[A-Za-z_][A-Za-z0-9_]*)")
_LOCAL_STORAGE_RE = re.compile(
    r"localStorage\.(?P<op>setItem|getItem|removeItem)\(\s*(?P<quote>['\"])(?P<key>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)
_INPUT_UPDATED_AT_VAR_RE = re.compile(
    r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*input\.updatedAt\b",
    re.IGNORECASE,
)
_READING_ROUND_RE = re.compile(
    r"Math\.round\(\s*(?P<numerator>[^)]+?)\s*/\s*(?P<divisor>\d+)\s*\)",
    re.IGNORECASE,
)
_PRIORITY_TERNARY_RE = re.compile(
    r"\(\s*(?P<flag>[A-Za-z_$][A-Za-z0-9_$]*)\s*\?\s*(?P<true_expr>[^:()]+)\s*:\s*(?P<false_expr>[^()]+)\)\s*\.toFixed\(",
    re.IGNORECASE,
)
_ISO_NOW_COMPARE_RE = re.compile(
    r"\b(?P<left>[A-Za-z_$][A-Za-z0-9_$.]*)\s*(?P<op><=|>=|<|>)\s*new\s+Date\(\)\.toISOString\(\)",
    re.IGNORECASE,
)
_ISO_NOW_COMPARE_RE_REVERSE = re.compile(
    r"new\s+Date\(\)\.toISOString\(\)\s*(?P<op><=|>=|<|>)\s*(?P<right>[A-Za-z_$][A-Za-z0-9_$.]*)",
    re.IGNORECASE,
)
_SAVE_BUTTON_OR_RE = re.compile(
    r"\b[A-Za-z0-9_$.]+\.disabled\s*=\s*!\(\s*title\s*\|\|\s*content\s*\)",
    re.IGNORECASE,
)
_APP_MIN_WIDTH_RE = re.compile(r"\.app\s*\{[\s\S]*?\bmin-width\s*:\s*(?P<value>\d+)px\s*;", re.IGNORECASE)
_JOB_PROCESS_RE = re.compile(
    r"\b(?:queue|worker|agenda)\.(?:process|define)\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)"
    r"(?:\s*,\s*(?P<handler>[A-Za-z_$][A-Za-z0-9_$]*))?",
    re.IGNORECASE,
)
_CLI_COMMAND_RE = re.compile(
    r"\b(?:program|cli|yargs)\.command\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)",
    re.IGNORECASE,
)
_RUN_JOB_TEST_RE = re.compile(
    r"\brunJob\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)\s*\)",
    re.IGNORECASE,
)
_RUN_CLI_TEST_RE = re.compile(
    r"\brunCli\s*\(\s*(?P<quote>['\"`])(?P<name>[^'\"`]+)(?P=quote)\s*\)",
    re.IGNORECASE,
)


@dataclass
class ExpressSignals:
    has_express_import: bool
    has_write_routes: bool
    has_test_framework: bool


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _iter_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        root_path = Path(root)
        for filename in filenames:
            files.append(root_path / filename)
    return files


def _iter_js_files(all_files: list[Path]) -> list[Path]:
    return [path for path in all_files if path.suffix.lower() in JS_SUFFIXES]


def _iter_css_files(all_files: list[Path]) -> list[Path]:
    return [path for path in all_files if path.suffix.lower() in CSS_SUFFIXES]


def _is_test_file(path: Path) -> bool:
    lowered_name = path.name.lower()
    lowered_parts = {part.lower() for part in path.parts}
    return (
        lowered_name.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts", ".test.mjs", ".spec.mjs"))
        or lowered_name.startswith("test_")
        or "__tests__" in lowered_parts
        or "tests" in lowered_parts
        or "test" in lowered_parts
    )


def _line_from_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_snippet(source_lines: list[str], line: int, *, window: int = 3) -> str:
    start = max(0, line - 1)
    end = min(len(source_lines), start + window)
    return "\n".join(part.rstrip() for part in source_lines[start:end]).strip()


def _normalize_endpoint_name(method: str, route_path: str, line: int, handler: str | None) -> str:
    if handler and handler not in {"async", "function"}:
        return handler
    normalized_path = re.sub(r"[^a-zA-Z0-9]+", "_", route_path).strip("_").lower() or "root"
    return f"{method.lower()}_{normalized_path}_{line}"


def _normalize_route_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        return "/"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    raw = re.sub(r"/{2,}", "/", raw)
    if len(raw) > 1:
        raw = raw.rstrip("/")
    return raw


def _path_has_prefix(route_path: str, prefix: str) -> bool:
    normalized_route = _normalize_route_path(route_path)
    normalized_prefix = _normalize_route_path(prefix)
    if normalized_prefix == "/":
        return True
    return normalized_route == normalized_prefix or normalized_route.startswith(f"{normalized_prefix}/")


def _extract_write_endpoints(path: Path, repo_path: Path, text: str, source_lines: list[str]) -> list[tuple[str, str, str, str, int, str]]:
    endpoints: list[tuple[str, str, str, str, int, str]] = []
    rel_path = str(path.relative_to(repo_path))

    for match in _ROUTE_CALL_RE.finditer(text):
        receiver = match.group("receiver").lower()
        if receiver not in {"app", "router"} and not receiver.endswith("router"):
            continue
        method = match.group("method").upper()
        route_path = match.group("path")
        line = _line_from_offset(text, match.start())
        handler = match.group("handler")
        endpoint_name = _normalize_endpoint_name(method, route_path, line, handler)
        endpoints.append(
            (
                rel_path,
                endpoint_name,
                method,
                route_path,
                line,
                _line_snippet(source_lines, line),
            )
        )
    return endpoints


def _extract_generic_ingress_surfaces(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[IngressSurfaceArtifact]:
    rel_path = str(path.relative_to(repo_path))
    surfaces: list[IngressSurfaceArtifact] = []

    for match in _JOB_PROCESS_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        name = match.group("name").strip()
        handler = (match.group("handler") or "").strip() or name
        surfaces.append(
            IngressSurfaceArtifact(
                file_path=rel_path,
                family="job",
                operation="execute",
                owner_name=handler,
                protocol="internal",
                target=name,
                method="RUN",
                line=line,
                snippet=_line_snippet(source_lines, line),
            )
        )

    for match in _CLI_COMMAND_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        name = match.group("name").strip()
        surfaces.append(
            IngressSurfaceArtifact(
                file_path=rel_path,
                family="cli_task",
                operation="execute",
                owner_name=name,
                protocol="cli",
                target=name,
                method="RUN",
                line=line,
                snippet=_line_snippet(source_lines, line),
            )
        )

    return surfaces


def _extract_test_ingress_calls(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[IngressCoverageArtifact]:
    rel_path = str(path.relative_to(repo_path))
    rows: list[IngressCoverageArtifact] = []

    for match in _RUN_JOB_TEST_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        rows.append(
            IngressCoverageArtifact(
                file_path=rel_path,
                family="job",
                operation="execute",
                test_name=f"runJob:{match.group('name').strip()}",
                protocol="internal",
                target=match.group("name").strip(),
                method="RUN",
                line=line,
                snippet=_line_snippet(source_lines, line),
            )
        )

    for match in _RUN_CLI_TEST_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        rows.append(
            IngressCoverageArtifact(
                file_path=rel_path,
                family="cli_task",
                operation="execute",
                test_name=f"runCli:{match.group('name').strip()}",
                protocol="cli",
                target=match.group("name").strip(),
                method="RUN",
                line=line,
                snippet=_line_snippet(source_lines, line),
            )
        )

    return rows


def _extract_auth_middleware(path: Path, repo_path: Path, text: str, source_lines: list[str]) -> list[tuple[str, int, str]]:
    matches: list[tuple[str, int, str]] = []
    for start_offset, block in _iter_app_use_blocks(text):
        prefix_match = _APP_USE_PREFIX_RE.search(block)
        if prefix_match is None:
            continue
        prefix = (prefix_match.group("prefix") or "/").strip() or "/"
        body = block[prefix_match.end() :]
        if not (_AUTH_HINT_RE.search(body) and _AUTH_DENY_RE.search(body)):
            continue
        line = _line_from_offset(text, start_offset)
        matches.append((prefix, line, _line_snippet(source_lines, line)))
    return matches


def _iter_app_use_blocks(text: str) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    for match in re.finditer(r"\bapp\.use\s*\(", text, re.IGNORECASE):
        start = match.start()
        open_idx = text.find("(", start)
        if open_idx == -1:
            continue
        end_idx = _balanced_paren_end(text, open_idx)
        if end_idx is None:
            continue
        blocks.append((start, text[start : end_idx + 1]))
    return blocks


def _balanced_paren_end(text: str, open_idx: int) -> int | None:
    depth = 0
    in_string: str | None = None
    escaped = False
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if in_string is not None:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == in_string:
                in_string = None
            continue

        if ch in {"'", '"', "`"}:
            in_string = ch
            continue
        if ch == "(":
            depth += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _extract_authorization_boundaries(
    write_endpoints: list[tuple[str, str, str, str, int | None, str]],
    auth_middleware_by_file: dict[str, list[tuple[str, int, str]]],
) -> list[tuple[str, str, str, str, int | None, str]]:
    boundaries: list[tuple[str, str, str, str, int | None, str]] = []
    for file_path, endpoint_name, _method, route_path, endpoint_line, _snippet in write_endpoints:
        candidates = auth_middleware_by_file.get(file_path, [])
        if not candidates:
            continue
        best: tuple[str, int, str] | None = None
        for prefix, line, snippet in candidates:
            if endpoint_line is not None and endpoint_line < line:
                # Express middleware order matters: middleware declared after route does not guard that route.
                continue
            if not _path_has_prefix(route_path, prefix):
                continue
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, line, snippet)
        if best is None:
            continue
        prefix, line, snippet = best
        boundaries.append((file_path, endpoint_name, "middleware", f"path:{prefix}", line, snippet))
    return boundaries


def _nearest_test_name(source_lines: list[str], line: int) -> str:
    start = max(0, line - 20)
    for idx in range(line - 1, start - 1, -1):
        match = _TEST_CASE_RE.search(source_lines[idx])
        if match:
            return match.group("name").strip() or f"test_line_{line}"
    return f"test_line_{line}"


def _extract_test_cases(path: Path, repo_path: Path, source_lines: list[str]) -> list[tuple[str, str, int, str]]:
    rel_path = str(path.relative_to(repo_path))
    rows: list[tuple[str, str, int, str]] = []
    for idx, line in enumerate(source_lines, start=1):
        match = _TEST_CASE_RE.search(line)
        if not match:
            continue
        rows.append((rel_path, match.group("name").strip(), idx, _line_snippet(source_lines, idx)))
    return rows


def _extract_test_http_calls(path: Path, repo_path: Path, text: str, source_lines: list[str]) -> list[tuple[str, str, str, str, int, str]]:
    rel_path = str(path.relative_to(repo_path))
    rows: list[tuple[str, str, str, str, int, str]] = []
    for match in _TEST_CALL_RE.finditer(text):
        method = match.group("method").upper()
        route_path = match.group("path")
        line = _line_from_offset(text, match.start())
        test_name = _nearest_test_name(source_lines, line)
        rows.append((rel_path, test_name, method, route_path, line, _line_snippet(source_lines, line)))
    return rows


def _normalize_key_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _to_snake_case(value: str) -> str:
    step = re.sub(r"([A-Z])", r"_\1", value).lower()
    return re.sub(r"[^a-z0-9_]+", "_", step).strip("_")


def _split_args(args_block: str) -> list[str]:
    return [part.strip() for part in args_block.split(",") if part.strip()]


def _indexed_functions(text: str) -> list[tuple[int, str, set[str]]]:
    rows: list[tuple[int, str, set[str]]] = []
    for match in _FUNCTION_HEADER_RE.finditer(text):
        params = {
            token.strip()
            for token in re.split(r"[\s,]+", match.group("params"))
            if token.strip()
        }
        rows.append((match.start(), match.group("name"), params))
    return rows


def _owner_for_offset(functions: list[tuple[int, str, set[str]]], offset: int) -> tuple[str, set[str]]:
    owner_name = "module_scope"
    owner_params: set[str] = set()
    for start, name, params in functions:
        if start > offset:
            break
        owner_name = name
        owner_params = params
    return owner_name, owner_params


def _extract_row_mapped_fields(text: str, source_lines: list[str]) -> dict[str, tuple[int, str]]:
    fields: dict[str, tuple[int, str]] = {}
    for match in _ROW_FIELD_RE.finditer(text):
        field_name = match.group("key")
        line = _line_from_offset(text, match.start())
        fields[field_name] = (line, _line_snippet(source_lines, line))
    return fields


def _extract_note_field_usages(text: str, source_lines: list[str]) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for match in _NOTE_FIELD_RE.finditer(text):
        field_name = match.group("field")
        line = _line_from_offset(text, match.start())
        rows.append((field_name, line, _line_snippet(source_lines, line)))
    return rows


def _extract_response_field_alias_issues(
    backend_fields: dict[str, tuple[str, int, str]],
    frontend_fields: list[tuple[str, str, int, str]],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    if not backend_fields:
        return issues

    backend_keys = set(backend_fields.keys())
    seen: set[tuple[str, str]] = set()
    for file_path, consumer_field, line, snippet in frontend_fields:
        if consumer_field in backend_keys:
            continue
        snake_field = _to_snake_case(consumer_field)
        candidates = [f"is_{consumer_field}", f"is_{snake_field}"]
        producer_field = next((field for field in candidates if field in backend_keys), "")
        if not producer_field:
            continue
        marker = (consumer_field, producer_field)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                file_path,
                "response_field_alias_mismatch",
                "response_contract",
                line,
                snippet,
                {
                    "consumer_field": consumer_field,
                    "producer_field": producer_field,
                },
            )
        )
    return issues


def _extract_write_contract_issues(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    rel_path = str(path.relative_to(repo_path))
    functions = _indexed_functions(text)
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    seen: set[tuple[str, str, int]] = set()

    for match in _INPUT_CHAR_SPLIT_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())
        field_name = match.group("field")
        marker = ("char_split_normalization", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "char_split_normalization",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {"field_name": field_name},
            )
        )

    for match in _DB_RUN_INSERT_RE.finditer(text):
        sql = match.group("sql")
        args = match.group("args")
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())

        col_match = re.search(r"INSERT\s+INTO\s+[^(]+\((?P<cols>[\s\S]*?)\)\s*VALUES", sql, re.IGNORECASE)
        if col_match is None:
            continue
        columns = [
            token.strip().strip("`\"' ")
            for token in col_match.group("cols").split(",")
            if token.strip()
        ]
        args_expr = _split_args(args)
        for idx, column in enumerate(columns):
            if idx >= len(args_expr):
                break
            expr = args_expr[idx]
            input_match = re.search(r"\binput\.(?P<field>[A-Za-z_$][A-Za-z0-9_$]*)\b", expr)
            if input_match is None:
                continue
            value_field = input_match.group("field")
            if _normalize_key_name(column) == _normalize_key_name(value_field):
                continue
            marker = ("db_insert_binding_mismatch", column, line)
            if marker in seen:
                continue
            seen.add(marker)
            issues.append(
                (
                    rel_path,
                    "db_insert_binding_mismatch",
                    owner_name,
                    line,
                    _line_snippet(source_lines, line),
                    {
                        "column": column,
                        "value_field": value_field,
                    },
                )
            )

    client_updated_vars = {
        match.group("name")
        for match in _INPUT_UPDATED_AT_VAR_RE.finditer(text)
    }
    for match in _DB_RUN_UPDATE_RE.finditer(text):
        sql = match.group("sql")
        args = match.group("args")
        line = _line_from_offset(text, match.start())
        owner_name, owner_params = _owner_for_offset(functions, match.start())
        sql_flat = " ".join(sql.lower().split())
        if " where " not in sql_flat:
            continue
        where_clause = sql_flat.split(" where ", 1)[1]

        has_entity_filter = bool(re.search(r"\bid\s*=", where_clause))
        if "id" in owner_params and not has_entity_filter and "user_id" in where_clause:
            marker = ("write_scope_missing_entity_filter", owner_name, line)
            if marker not in seen:
                seen.add(marker)
                issues.append(
                    (
                        rel_path,
                        "write_scope_missing_entity_filter",
                        owner_name,
                        line,
                        _line_snippet(source_lines, line),
                        {"missing_filter": "id"},
                    )
                )

        if "updated_at" not in sql_flat:
            continue
        has_conflict_guard = bool(re.search(r"\b(updated_at|version)\b\s*=", where_clause))
        if has_conflict_guard:
            continue
        args_expr = _split_args(args)
        client_updated_used = any("input.updatedAt" in expr for expr in args_expr)
        if not client_updated_used:
            client_updated_used = any(expr in client_updated_vars for expr in args_expr)
        if not client_updated_used:
            continue
        marker = ("stale_write_without_conflict_guard", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "stale_write_without_conflict_guard",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {},
            )
        )

    for match in _READING_ROUND_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())
        owner_lower = owner_name.lower()
        numerator = match.group("numerator")
        numerator_lower = numerator.lower()
        if "read" not in owner_lower and "minute" not in owner_lower:
            continue
        if "word" not in numerator_lower and "content" not in numerator_lower and "text" not in numerator_lower:
            continue
        marker = ("reading_time_rounding_floor_missing", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "reading_time_rounding_floor_missing",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {
                    "expression": match.group(0).strip(),
                    "divisor": match.group("divisor"),
                },
            )
        )

    for match in _PRIORITY_TERNARY_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())
        owner_lower = owner_name.lower()
        if "priority" not in owner_lower:
            continue
        false_expr = match.group("false_expr").strip()
        false_expr_lower = false_expr.lower()
        if "+" not in false_expr or "boost" not in false_expr_lower:
            continue
        marker = ("priority_ternary_constant_branch", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "priority_ternary_constant_branch",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {
                    "flag_name": match.group("flag").strip(),
                    "true_branch": match.group("true_expr").strip(),
                    "false_branch": false_expr,
                },
            )
        )

    for match in _ISO_NOW_COMPARE_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())
        compared_value = match.group("left").strip()
        owner_lower = owner_name.lower()
        compared_lower = compared_value.lower()
        if not any(token in owner_lower for token in {"overdue", "date", "deadline"}) and not any(
            token in compared_lower for token in {"due", "date", "deadline"}
        ):
            continue
        marker = ("date_string_compare_with_iso", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "date_string_compare_with_iso",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {
                    "compared_value": compared_value,
                    "operator": match.group("op"),
                },
            )
        )

    for match in _ISO_NOW_COMPARE_RE_REVERSE.finditer(text):
        line = _line_from_offset(text, match.start())
        owner_name, _owner_params = _owner_for_offset(functions, match.start())
        compared_value = match.group("right").strip()
        owner_lower = owner_name.lower()
        compared_lower = compared_value.lower()
        if not any(token in owner_lower for token in {"overdue", "date", "deadline"}) and not any(
            token in compared_lower for token in {"due", "date", "deadline"}
        ):
            continue
        marker = ("date_string_compare_with_iso", owner_name, line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "date_string_compare_with_iso",
                owner_name,
                line,
                _line_snippet(source_lines, line),
                {
                    "compared_value": compared_value,
                    "operator": match.group("op"),
                },
            )
        )

    return issues


def _extract_session_lifecycle_issues(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    rel_path = str(path.relative_to(repo_path))
    events: dict[str, list[tuple[str, str, int, str]]] = {"setItem": [], "getItem": [], "removeItem": []}
    for match in _LOCAL_STORAGE_RE.finditer(text):
        op = match.group("op")
        key = match.group("key")
        line = _line_from_offset(text, match.start())
        events[op].append((key, _normalize_key_name(key), line, _line_snippet(source_lines, line)))

    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    for set_key, set_norm, _set_line, _set_snippet in events["setItem"]:
        for remove_key, remove_norm, remove_line, remove_snippet in events["removeItem"]:
            if set_norm != remove_norm:
                continue
            if set_key == remove_key:
                continue
            marker = (set_key, remove_key)
            if marker in seen:
                continue
            seen.add(marker)
            issues.append(
                (
                    rel_path,
                    "storage_key_mismatch",
                    "localStorage",
                    remove_line,
                    remove_snippet,
                    {
                        "set_key": set_key,
                        "remove_key": remove_key,
                    },
                )
            )
    return issues


def _extract_html_render_issues(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    rel_path = str(path.relative_to(repo_path))
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    seen: set[tuple[str, int]] = set()
    for match in re.finditer(r"(?P<target>[A-Za-z0-9_$.]+)\.innerHTML\s*=\s*(?P<expr>[\s\S]*?);", text):
        expr = match.group("expr")
        if "${" not in expr or "note." not in expr:
            continue
        if "sanitize" in expr.lower():
            continue
        line = _line_from_offset(text, match.start())
        marker = (match.group("target"), line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "unsanitized_innerhtml",
                "renderNotes",
                line,
                _line_snippet(source_lines, line),
                {
                    "sink": f"{match.group('target')}.innerHTML",
                },
            )
        )
    return issues


def _extract_ui_ergonomics_issues(
    path: Path,
    repo_path: Path,
    text: str,
    source_lines: list[str],
) -> list[tuple[str, str, str, int | None, str, dict[str, str]]]:
    rel_path = str(path.relative_to(repo_path))
    issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    seen: set[tuple[str, int]] = set()
    lowered = text.lower()

    for match in _SAVE_BUTTON_OR_RE.finditer(text):
        line = _line_from_offset(text, match.start())
        marker = ("save_button_partial_form_enabled", line)
        if marker in seen:
            continue
        seen.add(marker)
        issues.append(
            (
                rel_path,
                "save_button_partial_form_enabled",
                "updateSaveButtonState",
                line,
                _line_snippet(source_lines, line),
                {"condition": "title || content"},
            )
        )

    if (
        "state.page" in lowered
        and "state.total = payload.total" in lowered
        and "action === 'delete'" in lowered
        and "await loadnotes()" in lowered
    ):
        has_normalization = any(
            token in lowered
            for token in (
                "math.min(state.page",
                "state.page = maxpage",
                "if (state.page > maxpage)",
                "if (payload.items.length === 0 && state.page > 1)",
                "if (state.notes.length === 0 && state.page > 1)",
            )
        )
        if not has_normalization:
            line = 1
            load_idx = text.find("async function loadNotes")
            if load_idx != -1:
                line = _line_from_offset(text, load_idx)
            marker = ("pagination_page_not_normalized_after_mutation", line)
            if marker not in seen:
                seen.add(marker)
                issues.append(
                    (
                        rel_path,
                        "pagination_page_not_normalized_after_mutation",
                        "loadNotes",
                        line,
                        _line_snippet(source_lines, line),
                        {"state_field": "state.page"},
                    )
                )

    if path.suffix.lower() == ".css":
        min_width_match = _APP_MIN_WIDTH_RE.search(text)
        if min_width_match is not None:
            min_width = int(min_width_match.group("value"))
            if min_width >= 900:
                line = _line_from_offset(text, min_width_match.start())
                marker = ("mobile_layout_min_width_overflow", line)
                if marker not in seen:
                    seen.add(marker)
                    issues.append(
                        (
                            rel_path,
                            "mobile_layout_min_width_overflow",
                            ".app",
                            line,
                            _line_snippet(source_lines, line),
                            {"min_width_px": str(min_width)},
                        )
                    )

    return issues


def scan_express_signals(repo_path: Path) -> ExpressSignals:
    all_files = _iter_files(repo_path)
    js_files = _iter_js_files(all_files)
    has_express_import = False
    has_write_routes = False
    has_test_framework = False

    for path in js_files:
        text = _read_text(path)
        if not text:
            continue
        if not has_express_import and _EXPRESS_IMPORT_RE.search(text):
            has_express_import = True
        if not has_write_routes and not _is_test_file(path):
            for match in _ROUTE_CALL_RE.finditer(text):
                receiver = match.group("receiver").lower()
                if receiver in {"app", "router"} or receiver.endswith("router"):
                    has_write_routes = True
                    break
        if not has_test_framework and _is_test_file(path) and _TEST_HINT_RE.search(text):
            has_test_framework = True

    return ExpressSignals(
        has_express_import=has_express_import,
        has_write_routes=has_write_routes,
        has_test_framework=has_test_framework,
    )


def collect_express_artifacts(repo_path: Path) -> ArtifactBundle:
    all_files = _iter_files(repo_path)
    js_files = _iter_js_files(all_files)
    css_files = _iter_css_files(all_files)
    test_files = [path for path in js_files if _is_test_file(path)]

    ingress_surfaces: list[IngressSurfaceArtifact] = []
    write_endpoints: list[tuple[str, str, str, str, int | None, str]] = []
    test_cases: list[tuple[str, str, int | None, str]] = []
    test_ingress_calls: list[IngressCoverageArtifact] = []
    test_http_calls: list[tuple[str, str, str, str, int | None, str]] = []
    auth_middleware_by_file: dict[str, list[tuple[str, int, str]]] = {}
    write_contract_issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    session_lifecycle_issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    html_render_issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    ui_ergonomics_issues: list[tuple[str, str, str, int | None, str, dict[str, str]]] = []
    backend_row_fields: dict[str, tuple[str, int, str]] = {}
    frontend_note_fields: list[tuple[str, str, int, str]] = []
    for path in js_files:
        text = _read_text(path)
        if not text:
            continue
        source_lines = text.splitlines()
        if _is_test_file(path):
            test_cases.extend(_extract_test_cases(path, repo_path, source_lines))
            test_ingress_calls.extend(_extract_test_ingress_calls(path, repo_path, text, source_lines))
            test_http_calls.extend(_extract_test_http_calls(path, repo_path, text, source_lines))
            continue
        file_endpoints = _extract_write_endpoints(path, repo_path, text, source_lines)
        write_endpoints.extend(file_endpoints)
        ingress_surfaces.extend(_extract_generic_ingress_surfaces(path, repo_path, text, source_lines))
        rel_path = str(path.relative_to(repo_path))
        auth_middleware_by_file[rel_path] = _extract_auth_middleware(path, repo_path, text, source_lines)
        write_contract_issues.extend(_extract_write_contract_issues(path, repo_path, text, source_lines))
        session_lifecycle_issues.extend(_extract_session_lifecycle_issues(path, repo_path, text, source_lines))
        html_render_issues.extend(_extract_html_render_issues(path, repo_path, text, source_lines))
        ui_ergonomics_issues.extend(_extract_ui_ergonomics_issues(path, repo_path, text, source_lines))

        for key, (line, snippet) in _extract_row_mapped_fields(text, source_lines).items():
            backend_row_fields[key] = (rel_path, line, snippet)
        for field_name, line, snippet in _extract_note_field_usages(text, source_lines):
            frontend_note_fields.append((rel_path, field_name, line, snippet))

    for path in css_files:
        text = _read_text(path)
        if not text:
            continue
        source_lines = text.splitlines()
        ui_ergonomics_issues.extend(_extract_ui_ergonomics_issues(path, repo_path, text, source_lines))

    authorization_boundaries = _extract_authorization_boundaries(write_endpoints, auth_middleware_by_file)
    write_contract_issues.extend(
        _extract_response_field_alias_issues(
            backend_row_fields,
            frontend_note_fields,
        )
    )

    return ArtifactBundle(
        all_files=all_files,
        ingress_surfaces=ingress_surfaces,
        write_endpoints=write_endpoints,
        test_files=test_files,
        test_cases=test_cases,
        test_ingress_calls=test_ingress_calls,
        test_http_calls=test_http_calls,
        dependency_specs=extract_dependency_specs(repo_path, all_files),
        authorization_boundaries=authorization_boundaries,
        write_contract_issues=write_contract_issues,
        session_lifecycle_issues=session_lifecycle_issues,
        html_render_issues=html_render_issues,
        ui_ergonomics_issues=ui_ergonomics_issues,
    )


__all__ = ["ExpressSignals", "collect_express_artifacts", "scan_express_signals"]
