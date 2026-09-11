"""``importcost`` — profile pytest collection without extra flags."""

from __future__ import annotations

import argparse
import subprocess
import sys

from .run import measured_collect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="importcost",
        description="Show which imports make pytest collection slow.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="extra args passed to pytest --collect-only (use -- to disambiguate)",
    )
    parser.add_argument("--python", default=None, help="interpreter to measure")
    parser.add_argument(
        "--plugins",
        action="store_true",
        help="include globally installed pytest plugins (autoload)",
    )
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=None,
        help="fail if collection import cost exceeds this many milliseconds",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="print machine-readable JSON instead of the table",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="how many ranked rows to print (default: 12)",
    )
    parser.add_argument(
        "--modules",
        action="store_true",
        help="rank full module names instead of top-level packages",
    )
    parser.add_argument(
        "--hide-stdlib",
        action="store_true",
        help="omit CPython stdlib names from the ranked rows",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        help="write the profile JSON for later --compare",
    )
    parser.add_argument(
        "--compare",
        metavar="FILE",
        help="diff against a profile saved with --save",
    )
    parser.add_argument(
        "--slower-ms",
        type=float,
        default=None,
        help="with --compare, fail if total import cost grew by more than this",
    )
    args = parser.parse_args(argv)
    rest = list(args.pytest_args)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if args.plugins:
        import os

        os.environ["IMPORTCOST_PLUGINS"] = "1"
    try:
        report, code = measured_collect(
            rest,
            python=args.python,
            limit=args.limit,
            hide_stdlib=args.hide_stdlib,
            modules=args.modules,
            budget_ms=args.budget_ms,
            as_json=args.as_json,
            save_path=args.save,
            compare_path=args.compare,
            slower_ms=args.slower_ms,
        )
    except subprocess.TimeoutExpired as exc:
        print(f"importcost: timed out: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0 if code in (0, 5) else code  # 5 = no tests collected


if __name__ == "__main__":
    raise SystemExit(main())
