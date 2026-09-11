"""Run pytest --collect-only under -X importtime and parse the profile."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .parse import (
    ParseError,
    costs_from_saved,
    diff_profiles,
    drop_stdlib,
    forbidden_hits,
    format_ms,
    median_cost_map,
    median_us,
    parse_self_us,
    render_compare,
    render_forbid,
    render_json,
    render_report,
)


def _collect_once(
    pytest_args: list[str] | None,
    *,
    python: str | None,
    timeout: float,
    modules: bool,
) -> tuple[dict[str, int] | None, int, str]:
    """One ``pytest --collect-only`` under ``-X importtime``.

    Returns ``(costs, child_exit, error_text)``. ``costs`` is None on parse failure.
    """
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
        return None, proc.returncode or 1, msg
    return costs, proc.returncode, ""


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
    save_path: str | None = None,
    compare_path: str | None = None,
    slower_ms: float | None = None,
    forbid: list[str] | None = None,
    repeat: int = 1,
) -> tuple[str, int]:
    """Return (report text, exit code). Exit 1 on budget / forbid / --slower-ms."""
    n = max(1, int(repeat))
    maps: list[dict[str, int]] = []
    totals: list[int] = []
    child_code = 0
    for _ in range(n):
        costs, code, err = _collect_once(
            pytest_args,
            python=python,
            timeout=timeout,
            modules=modules,
        )
        if costs is None:
            return err, code
        maps.append(costs)
        totals.append(sum(costs.values()))
        if code not in (0, 5):
            child_code = code

    costs = maps[0] if n == 1 else median_cost_map(maps)
    raw_total = totals[0] if n == 1 else median_us(totals)
    min_total = min(totals)
    max_total = max(totals)
    display = drop_stdlib(costs) if hide_stdlib else costs
    unit = "modules" if modules else "packages"
    if save_path:
        try:
            Path(save_path).write_text(
                render_json(display, limit=0, total_us=raw_total, unit=unit),
                encoding="utf-8",
            )
        except OSError as exc:
            return f"importcost: could not write {save_path}: {exc}", 1

    compare_blob = None
    compare_diff = None
    slower = False
    if compare_path:
        try:
            saved = json.loads(Path(compare_path).read_text(encoding="utf-8"))
            before_total, before = costs_from_saved(saved)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return f"importcost: could not read {compare_path}: {exc}", 1
        compare_diff = diff_profiles(
            display, before, now_total=raw_total, before_total=before_total
        )
        compare_blob = render_compare(
            display, before, now_total=raw_total, before_total=before_total
        )
        if slower_ms is not None and (raw_total - before_total) / 1000.0 > slower_ms:
            slower = True
            compare_blob += (
                f"\nimportcost: slower than saved by more than {slower_ms:g} ms"
            )

    hits = forbidden_hits(costs, forbid or [])
    if as_json:
        report = render_json(
            display,
            limit=limit,
            total_us=raw_total,
            unit=unit,
            budget_ms=budget_ms,
            forbid=forbid,
            forbidden=hits,
            repeat=n,
            min_us=min_total if n > 1 else None,
            max_us=max_total if n > 1 else None,
        )
        if compare_blob:
            payload = json.loads(report)
            payload["compare"] = compare_blob
            payload["diff"] = compare_diff
            report = json.dumps(payload, indent=2)
    else:
        report = render_report(
            display,
            limit=limit,
            total_us=raw_total,
            unit=unit,
            repeat=n,
            min_us=min_total if n > 1 else None,
            max_us=max_total if n > 1 else None,
        )
        if hide_stdlib:
            report += "\nStdlib names omitted from rows; total still includes them."
        if save_path:
            report += f"\nsaved to {save_path}"
        if compare_blob:
            report = report.rstrip() + "\n\n" + compare_blob

    code = child_code
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
    if hits:
        line = render_forbid(hits)
        if as_json:
            sys.stderr.write(line + "\n")
        else:
            report = report.rstrip() + "\n\n" + line
        if code == 0:
            code = 1
    if slower and code == 0:
        code = 1
        if as_json:
            sys.stderr.write(
                f"importcost: slower than saved by more than {slower_ms:g} ms\n"
            )
    return report, code
