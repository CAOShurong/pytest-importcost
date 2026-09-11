"""Run pytest --collect-only under -X importtime and parse the profile."""

from __future__ import annotations

import os
import subprocess
import sys

from .parse import ParseError, parse_package_self_us, render_report


def measured_collect(
    pytest_args: list[str] | None = None,
    *,
    python: str | None = None,
    timeout: float = 180.0,
) -> tuple[str, int]:
    """Return (report text, pytest exit code)."""
    exe = python or sys.executable
    args = ["--collect-only", "-q"]
    if pytest_args:
        args.extend(pytest_args)
    env = os.environ.copy()
    env["_PYTEST_IMPORTCOST_CHILD"] = "1"
    # Autoloaded site plugins (hypothesis, cov, xdist, …) dominate a
    # developer machine and hide the suite's own imports. Default off;
    # pass --importcost-plugins (CLI) / env IMPORTCOST_PLUGINS=1 to include.
    if os.environ.get("IMPORTCOST_PLUGINS") != "1":
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(
        [exe, "-X", "importtime", "-m", "pytest", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )
    blob = (proc.stderr or "") + "\n" + (proc.stdout or "")
    try:
        costs = parse_package_self_us(blob)
    except ParseError as exc:
        extra = (proc.stderr or proc.stdout or "").strip()
        msg = f"importcost: {exc}"
        if extra:
            msg += "\n" + extra[-2000:]
        return msg, proc.returncode or 1
    return render_report(costs), proc.returncode
