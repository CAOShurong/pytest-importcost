"""Parse CPython ``-X importtime`` / PYTHONPROFILEIMPORTTIME stderr."""

from __future__ import annotations

import re
from collections import defaultdict

_LINE = re.compile(
    r"^import time:\s*(?P<self>\d+)\s*\|\s*(?P<cumulative>\d+)\s*\|(?P<name>.*)$"
)
_HEADER = re.compile(r"^import time:\s*self\s*\[us\]")


class ParseError(ValueError):
    """No import-time lines in the captured output."""


def parse_package_self_us(text: str) -> dict[str, int]:
    """Sum each module's *self* microseconds into its top-level package."""
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
        top = name.split(".", 1)[0]
        costs[top] += int(match.group("self"))
    if not seen:
        raise ParseError("no '-X importtime' lines found")
    return dict(costs)


def format_ms(us: int) -> str:
    ms = us / 1000.0
    if ms >= 100:
        return f"{ms:.0f} ms"
    if ms >= 10:
        return f"{ms:.1f} ms"
    return f"{ms:.2f} ms"


def render_report(costs: dict[str, int], *, limit: int = 12) -> str:
    total = sum(costs.values())
    ranked = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    width = max((len(name) for name, _ in ranked[:limit]), default=8)
    bar_w = 28
    lines = [
        f"pytest collection import cost  {format_ms(total)}  across {len(costs)} packages",
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
