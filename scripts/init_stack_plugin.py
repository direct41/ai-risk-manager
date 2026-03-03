from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from ai_risk_manager.collectors.plugins.scaffold import (  # noqa: E402
    PluginScaffoldSpec,
    default_class_name,
    render_plugin_scaffold,
    validate_stack_id,
)
from ai_risk_manager.schemas.types import AppliedSupportLevel  # noqa: E402
from ai_risk_manager.signals.types import SignalKind  # noqa: E402


def _parse_signal_csv(raw: str) -> tuple[SignalKind, ...]:
    if not raw.strip():
        return ()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    return tuple(cast(SignalKind, part) for part in parts if part)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a new collector plugin scaffold.")
    parser.add_argument("--stack-id", required=True, help="Stack id, for example: flask_pytest")
    parser.add_argument("--class-name", default="", help="Plugin class name. Defaults to <StackId>CollectorPlugin.")
    parser.add_argument(
        "--target-support-level",
        default="l1",
        choices=["l0", "l1", "l2"],
        help="Initial target support level for the plugin contract.",
    )
    parser.add_argument(
        "--extra-supported",
        default="",
        help="Comma-separated signal kinds to mark as supported in addition to required ones.",
    )
    parser.add_argument(
        "--explicit-unsupported",
        default="",
        help="Comma-separated signal kinds to mark as unsupported explicitly.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output file path. Defaults to src/ai_risk_manager/collectors/plugins/<stack_id>.py",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output file if it already exists.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    stack_id = str(args.stack_id).strip()
    validate_stack_id(stack_id)
    class_name = str(args.class_name).strip() or default_class_name(stack_id)
    target_support_level = cast(AppliedSupportLevel, str(args.target_support_level))
    output = str(args.output).strip() or f"src/ai_risk_manager/collectors/plugins/{stack_id}.py"
    output_path = (REPO_ROOT / output).resolve()
    if output_path.exists() and not args.force:
        raise SystemExit(f"Output file already exists: {output_path}. Use --force to overwrite.")

    spec = PluginScaffoldSpec(
        stack_id=stack_id,
        class_name=class_name,
        target_support_level=target_support_level,
        extra_supported=_parse_signal_csv(args.extra_supported),
        explicit_unsupported=_parse_signal_csv(args.explicit_unsupported),
    )
    content = render_plugin_scaffold(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Created plugin scaffold: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
