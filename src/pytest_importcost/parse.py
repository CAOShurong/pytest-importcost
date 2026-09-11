"""Parse CPython ``-X importtime`` / PYTHONPROFILEIMPORTTIME stderr."""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

_LINE = re.compile(
    r"^import time:\s*(?P<self>\d+)\s*\|\s*(?P<cumulative>\d+)\s*\|(?P<name>.*)$"
)
_HEADER = re.compile(r"^import time:\s*self\s*\[us\]")


class ParseError(ValueError):
    """No import-time lines in the captured output."""


def parse_self_us(text: str, *, group: str = "package") -> dict[str, int]:
    """Sum each module's *self* microseconds.

    ``group="package"`` rolls ``pandas.core`` into ``pandas``.
    ``group="module"`` keeps the full imported name.
    """
    if group not in ("package", "module"):
        raise ValueError(f"unknown group {group!r}")
    costs: dict[str, int] = defaultdict(int)
    seen = False
    for line in text.splitlines():
        if _HEADER.match(line):
            continue
        match = _LINE.match(line)
        if match is None:
            continue
        name = match.group("name").strip()
        if not name:
            continue
        seen = True
        key = name.split(".", 1)[0] if group == "package" else name
        costs[key] += int(match.group("self"))
    if not seen:
        raise ParseError("no '-X importtime' lines found")
    return dict(costs)


def parse_package_self_us(text: str) -> dict[str, int]:
    """Sum each module's *self* microseconds into its top-level package."""
    return parse_self_us(text, group="package")


def stdlib_top_names() -> frozenset[str]:
    """Top-level names that belong to the measuring interpreter's stdlib."""
    names = {n.split(".")[0] for n in sys.builtin_module_names}
    std = getattr(sys, "stdlib_module_names", None)
    if std:
        names.update(n.split(".")[0] for n in std)
        return frozenset(names)
    try:
        from sysconfig import get_path

        root = get_path("stdlib")
        if root and os.path.isdir(root):
            for entry in os.listdir(root):
                if entry.endswith(".py"):
                    names.add(entry[:-3])
                elif os.path.isdir(os.path.join(root, entry)) and not entry.startswith(
                    "__"
                ):
                    names.add(entry)
    except OSError:
        pass
    return frozenset(names)


def drop_stdlib(costs: dict[str, int]) -> dict[str, int]:
    """Drop CPython stdlib / builtin top-level names from a cost map."""
    std = stdlib_top_names()
    return {k: v for k, v in costs.items() if k.split(".", 1)[0] not in std}


def format_ms(us: int) -> str:
    ms = us / 1000.0
    if ms >= 100:
        return f"{ms:.0f} ms"
    if ms >= 10:
        return f"{ms:.1f} ms"
    return f"{ms:.2f} ms"


def render_report(
    costs: dict[str, int],
    *,
    limit: int = 12,
    total_us: int | None = None,
    unit: str = "packages",
) -> str:
    shown_total = sum(costs.values())
    total = shown_total if total_us is None else total_us
    ranked = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    width = max((len(name) for name, _ in ranked[:limit]), default=8)
    bar_w = 28
    lines = [
        f"pytest collection import cost  {format_ms(total)}  across {len(costs)} {unit}",
        "",
    ]
    top = ranked[:limit]
    peak = top[0][1] if top else 1
    for name, us in top:
        frac = us / peak if peak else 0.0
        filled = int(round(frac * bar_w))
        bar = "█" * filled + "░" * (bar_w - filled)
        share = (us / total * 100.0) if total else 0.0
        lines.append(f"  {name:{width}s}  {bar}  {format_ms(us):>8s}  {share:4.1f}%")
    leftover = ranked[limit:]
    if leftover:
        other = sum(us for _, us in leftover)
        lines.append(
            f"  {'(others)':{width}s}  {'':{bar_w}s}  {format_ms(other):>8s}  "
            f"{other / total * 100.0:4.1f}%"
        )
    lines.append("")
    lines.append(
        "This is CPython import-time of `pytest --collect-only`, not test runtime."
    )
    return "\n".join(lines)


def render_json(
    costs: dict[str, int],
    *,
    limit: int = 12,
    total_us: int | None = None,
    unit: str = "packages",
    budget_ms: float | None = None,
) -> str:
    shown_total = sum(costs.values())
    total = shown_total if total_us is None else total_us
    ranked = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    total_ms = total / 1000.0
    top = ranked if limit <= 0 else ranked[:limit]
    payload = {
        "total_us": total,
        "total_ms": round(total_ms, 3),
        "count": len(costs),
        "grouped_by": "module" if unit == "modules" else "package",
        "budget_ms": budget_ms,
        "budget_ok": None if budget_ms is None else total_ms <= budget_ms,
        "rows": [
            {
                "name": name,
                "self_us": us,
                "self_ms": round(us / 1000.0, 3),
                "share": (us / total) if total else 0.0,
            }
            for name, us in top
        ],
    }
    return json.dumps(payload, indent=2)


def costs_from_saved(data: dict) -> tuple[int, dict[str, int]]:
    """Read a --json / --save payload (or a plain name→us map)."""
    if "rows" in data:
        costs = {str(row["name"]): int(row["self_us"]) for row in data["rows"]}
        total = int(data.get("total_us") or sum(costs.values()))
        return total, costs
    costs = {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}
    return sum(costs.values()), costs


def render_compare(
    now: dict[str, int],
    before: dict[str, int],
    *,
    now_total: int | None = None,
    before_total: int | None = None,
) -> str:
    now_us = sum(now.values()) if now_total is None else now_total
    before_us = sum(before.values()) if before_total is None else before_total
    delta = now_us - before_us
    if delta < 0:
        arrow = "faster"
    elif delta > 0:
        arrow = "slower"
    else:
        arrow = "unchanged"
    lines = [
        f"compared with saved profile  before {format_ms(before_us)}  "
        f"now {format_ms(now_us)}  {format_ms(abs(delta))} {arrow}",
        "",
    ]
    added = sorted(set(now) - set(before), key=lambda n: now[n], reverse=True)
    gone = sorted(set(before) - set(now), key=lambda n: before[n], reverse=True)
    if added:
        lines.append("  newly imported:")
        for name in added[:8]:
            lines.append(f"    {name:<24} +{format_ms(now[name])}")
    if gone:
        lines.append("  no longer imported:")
        for name in gone[:8]:
            lines.append(f"    {name:<24} -{format_ms(before[name])}")
    if not added and not gone:
        lines.append("  same package set")
    return "\n".join(lines)
