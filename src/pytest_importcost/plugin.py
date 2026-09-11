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
    "--importcost-blame",
    "--importcost-plugins",
    "--importcost-suite",
    "--importcost-new",
}
_VALUE_FLAGS = {
    "--importcost-budget-ms",
    "--importcost-limit",
    "--importcost-save",
    "--importcost-compare",
    "--importcost-slower-ms",
    "--importcost-forbid",
    "--importcost-repeat",
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
    group.addoption(
        "--importcost-save",
        action="store",
        default=None,
        help="write the import-cost JSON for later --importcost-compare",
    )
    group.addoption(
        "--importcost-compare",
        action="store",
        default=None,
        help="diff against a profile saved with --importcost-save",
    )
    group.addoption(
        "--importcost-slower-ms",
        action="store",
        type=float,
        default=None,
        help="with --importcost-compare, fail if total cost grew by more than this",
    )
    group.addoption(
        "--importcost-forbid",
        action="store",
        default=None,
        help="fail if these packages are imported during collection (comma-separated)",
    )
    group.addoption(
        "--importcost-repeat",
        action="store",
        type=int,
        default=1,
        help="run collection N times and rank the median (default: 1)",
    )
    group.addoption(
        "--importcost-blame",
        action="store_true",
        default=False,
        help="show which conftest/test file first imported each package",
    )
    group.addoption(
        "--importcost-plugins",
        action="store_true",
        default=False,
        help="include globally installed pytest plugins in the measured child",
    )
    group.addoption(
        "--importcost-suite",
        action="store_true",
        default=False,
        help="rank only packages first imported by conftest.py / test files",
    )
    group.addoption(
        "--importcost-new",
        action="store_true",
        default=False,
        help="with --importcost-compare, fail if new packages were imported",
    )


def _requested(config: pytest.Config) -> bool:
    return bool(
        config.getoption("importcost")
        or config.getoption("importcost_budget_ms") is not None
        or config.getoption("importcost_json")
        or config.getoption("importcost_modules")
        or config.getoption("importcost_hide_stdlib")
        or config.getoption("importcost_save")
        or config.getoption("importcost_compare")
        or config.getoption("importcost_forbid")
        or int(config.getoption("importcost_repeat") or 1) > 1
        or config.getoption("importcost_blame")
        or config.getoption("importcost_plugins")
        or config.getoption("importcost_suite")
        or config.getoption("importcost_new")
    )


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> int | None:
    if not _requested(config):
        return None
    if os.environ.get("_PYTEST_IMPORTCOST_CHILD") == "1":
        return None

    from .parse import parse_forbid_names
    from .run import measured_collect

    if config.getoption("importcost_plugins"):
        os.environ["IMPORTCOST_PLUGINS"] = "1"

    child_args = strip_importcost_args(list(config.invocation_params.args))
    report, code = measured_collect(
        child_args,
        python=sys.executable,
        limit=int(config.getoption("importcost_limit") or 12),
        hide_stdlib=bool(config.getoption("importcost_hide_stdlib")),
        modules=bool(config.getoption("importcost_modules")),
        budget_ms=config.getoption("importcost_budget_ms"),
        as_json=bool(config.getoption("importcost_json")),
        save_path=config.getoption("importcost_save"),
        compare_path=config.getoption("importcost_compare"),
        slower_ms=config.getoption("importcost_slower_ms"),
        forbid=parse_forbid_names(config.getoption("importcost_forbid")),
        repeat=max(1, int(config.getoption("importcost_repeat") or 1)),
        blame=bool(config.getoption("importcost_blame")),
        suite=bool(config.getoption("importcost_suite")),
        fail_on_new=bool(config.getoption("importcost_new")),
    )
    sys.stdout.write(report + "\n")
    # 5 = pytest "no tests collected"; still a successful measurement.
    return 0 if code in (0, 5) else code


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    from .blame import tracker

    state = tracker()
    if state is None:
        yield
        return
    # Anything already imported is pytest itself, not the suite.
    state.mark_seen()
    state.watch_conftest(True)
    try:
        yield
    finally:
        state.watch_conftest(False)
        # Swallow pytest's own imports during this window; conftest-caused
        # names were recorded by the meta_path finder.
        state.mark_seen()


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_make_collect_report(collector: object):
    from .blame import tracker

    state = tracker()
    if state is None:
        yield
        return
    yield
    state.snap(collector)


def pytest_unconfigure(config: pytest.Config) -> None:
    from .blame import tracker

    state = tracker()
    if state is not None:
        state.emit()
