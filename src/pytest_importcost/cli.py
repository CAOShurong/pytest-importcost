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
    args = parser.parse_args(argv)
    rest = list(args.pytest_args)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if args.plugins:
        import os

        os.environ["IMPORTCOST_PLUGINS"] = "1"
    try:
        report, code = measured_collect(rest, python=args.python)
    except subprocess.TimeoutExpired as exc:
        print(f"importcost: timed out: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0 if code in (0, 5) else code  # 5 = no tests collected


if __name__ == "__main__":
    raise SystemExit(main())
