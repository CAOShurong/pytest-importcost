"""pytest plugin: ``pytest --importcost`` re-runs collection under importtime."""

from __future__ import annotations

import os
import sys

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("importcost")
    group.addoption(
        "--importcost",
        action="store_true",
        default=False,
        help="profile import cost of pytest collection (separate measured run)",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> int | None:
    if not config.getoption("importcost"):
        return None
    if os.environ.get("_PYTEST_IMPORTCOST_CHILD") == "1":
        return None

    from .run import measured_collect

    # Drop our flag so the child is a normal collect-only session.
    child_args = [a for a in config.invocation_params.args if a != "--importcost"]
    report, code = measured_collect(child_args, python=sys.executable)
    sys.stdout.write(report + "\n")
    # 5 = pytest "no tests collected"; still a successful measurement.
    return 0 if code in (0, 5) else code
