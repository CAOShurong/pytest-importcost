"""pytest plugin: ``pytest --importcost`` re-runs collection under importtime."""

from __future__ import annotations

import os
import sys

import pytest

_BOOL_FLAGS = {
    "--importcost",
    "--importcost-json",
    "--importcost-modules",
    "--importcost-hide-stdlib",
}
_VALUE_FLAGS = {
    "--importcost-budget-ms",
    "--importcost-limit",
}


def strip_importcost_args(args: list[str]) -> list[str]:
    """Drop this plugin's flags so the measured child is a normal collect."""
    out: list[str] = []
    skip_next = False
    prefixes = tuple(f"{flag}=" for flag in _BOOL_FLAGS | _VALUE_FLAGS)
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in _BOOL_FLAGS:
            continue
        if arg in _VALUE_FLAGS:
            skip_next = True
            continue
        if arg.startswith(prefixes):
            continue
        out.append(arg)
    return out


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("importcost")
    group.addoption(
        "--importcost",
        action="store_true",
        default=False,
        help="profile import cost of pytest collection (separate measured run)",
    )
    group.addoption(
        "--importcost-budget-ms",
        action="store",
        type=float,
        default=None,
        help="fail if collection import cost exceeds this many milliseconds",
    )
    group.addoption(
        "--importcost-json",
        action="store_true",
        default=False,
        help="print import cost as JSON instead of the table",
    )
    group.addoption(
        "--importcost-limit",
        action="store",
        type=int,
        default=12,
        help="how many ranked import-cost rows to print (default: 12)",
    )
    group.addoption(
        "--importcost-modules",
        action="store_true",
        default=False,
        help="rank full module names instead of top-level packages",
    )
    group.addoption(
        "--importcost-hide-stdlib",
        action="store_true",
        default=False,
        help="omit CPython stdlib names from the ranked rows",
    )


def _requested(config: pytest.Config) -> bool:
    return bool(
        config.getoption("importcost")
        or config.getoption("importcost_budget_ms") is not None
        or config.getoption("importcost_json")
        or config.getoption("importcost_modules")
        or config.getoption("importcost_hide_stdlib")
    )


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> int | None:
    if not _requested(config):
        return None
    if os.environ.get("_PYTEST_IMPORTCOST_CHILD") == "1":
        return None

    from .run import measured_collect

    child_args = strip_importcost_args(list(config.invocation_params.args))
    report, code = measured_collect(
        child_args,
        python=sys.executable,
        limit=int(config.getoption("importcost_limit") or 12),
        hide_stdlib=bool(config.getoption("importcost_hide_stdlib")),
        modules=bool(config.getoption("importcost_modules")),
        budget_ms=config.getoption("importcost_budget_ms"),
        as_json=bool(config.getoption("importcost_json")),
    )
    sys.stdout.write(report + "\n")
    # 5 = pytest "no tests collected"; still a successful measurement.
    return 0 if code in (0, 5) else code
