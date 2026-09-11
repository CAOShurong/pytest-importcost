"""Run pytest --collect-only under -X importtime and parse the profile."""

from __future__ import annotations

import os
import subprocess
import sys

from .parse import (
    ParseError,
    drop_stdlib,
    format_ms,
    parse_self_us,
    render_json,
    render_report,
)


def measured_collect(
    pytest_args: list[str] | None = None,
    *,
    python: str | None = None,
    timeout: float = 180.0,
    limit: int = 12,
    hide_stdlib: bool = False,
    modules: bool = False,
    budget_ms: float | None = None,
    as_json: bool = False,
) -> tuple[str, int]:
    """Return (report text, exit code). Exit 1 if ``budget_ms`` is exceeded."""
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
        costs = parse_self_us(blob, group="module" if modules else "package")
    except ParseError as exc:
        extra = (proc.stderr or proc.stdout or "").strip()
        msg = f"importcost: {exc}"
        if extra:
            msg += "\n" + extra[-2000:]
        return msg, proc.returncode or 1

    raw_total = sum(costs.values())
    display = drop_stdlib(costs) if hide_stdlib else costs
    unit = "modules" if modules else "packages"
    if as_json:
        report = render_json(
            display,
            limit=limit,
            total_us=raw_total,
            unit=unit,
            budget_ms=budget_ms,
        )
    else:
        report = render_report(
            display, limit=limit, total_us=raw_total, unit=unit
        )
        if hide_stdlib:
            report += "\nStdlib names omitted from rows; total still includes them."

    code = 0 if proc.returncode in (0, 5) else proc.returncode
    if budget_ms is not None and raw_total / 1000.0 > budget_ms:
        line = (
            f"importcost: budget exceeded: {format_ms(raw_total)} > {budget_ms:g} ms"
        )
        if as_json:
            sys.stderr.write(line + "\n")
        else:
            report = report.rstrip() + "\n\n" + line
        if code == 0:
            code = 1
    return report, code
