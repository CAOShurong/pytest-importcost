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


def median_us(values: list[int]) -> int:
    """Integer median. Even length uses the lower middle (no float ms)."""
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) // 2


def median_cost_map(maps: list[dict[str, int]]) -> dict[str, int]:
    """Per-name median; missing keys count as 0."""
    keys: set[str] = set()
    for mapping in maps:
        keys.update(mapping)
    return {name: median_us([mapping.get(name, 0) for mapping in maps]) for name in keys}


def format_ms(us: int) -> str:
    ms = us / 1000.0
    if ms >= 100:
        return f"{ms:.0f} ms"
    if ms >= 10:
        return f"{ms:.1f} ms"
    return f"{ms:.2f} ms"


def short_importer(path: str, width: int = 40) -> str:
    text = path.replace("\\", "/")
    if len(text) <= width:
        return text
    return "…" + text[-(width - 1) :]


def render_report(
    costs: dict[str, int],
    *,
    limit: int = 12,
    total_us: int | None = None,
    unit: str = "packages",
    repeat: int = 1,
    min_us: int | None = None,
    max_us: int | None = None,
    importers: dict[str, str] | None = None,
) -> str:
    shown_total = sum(costs.values())
    total = shown_total if total_us is None else total_us
    ranked = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    width = max((len(name) for name, _ in ranked[:limit]), default=8)
    bar_w = 28
    head = f"pytest collection import cost  {format_ms(total)}  across {len(costs)} {unit}"
    if repeat > 1:
        head += f"  (median of {repeat})"
    lines = [head, ""]
    if repeat > 1 and min_us is not None and max_us is not None:
        lines.append(f"  runs  min {format_ms(min_us)}  max {format_ms(max_us)}")
        lines.append("")
    top = ranked[:limit]
    peak = top[0][1] if top else 1
    show_blame = bool(importers)
    for name, us in top:
        frac = us / peak if peak else 0.0
        filled = int(round(frac * bar_w))
        bar = "█" * filled + "░" * (bar_w - filled)
        share = (us / total * 100.0) if total else 0.0
        row = f"  {name:{width}s}  {bar}  {format_ms(us):>8s}  {share:4.1f}%"
        if show_blame:
            who = (importers or {}).get(name, "(collection startup)")
            row += f"  {short_importer(who)}"
        lines.append(row)
    leftover = ranked[limit:]
    if leftover:
        other = sum(us for _, us in leftover)
        lines.append(
            f"  {'(others)':{width}s}  {'':{bar_w}s}  {format_ms(other):>8s}  "
            f"{other / total * 100.0:4.1f}%"
        )
    if show_blame:
        lines.append("")
        lines.extend(_render_by_file(costs, importers or {}, total=total, limit=limit))
    lines.append("")
    lines.append(
        "This is CPython import-time of `pytest --collect-only`, not test runtime."
    )
    if show_blame:
        lines.append(
            "The last column is the conftest/test file that first imported that package."
        )
    return "\n".join(lines)


def _render_by_file(
    costs: dict[str, int],
    importers: dict[str, str],
    *,
    total: int,
    limit: int,
) -> list[str]:
    from .blame import file_costs

    ranked = file_costs(costs, importers)
    if not ranked:
        return []
    width = max(len(label) for label, _, _ in ranked[:limit])
    width = min(max(width, 8), 48)
    lines = ["By file (new packages first seen there)", ""]
    for label, us, names in ranked[:limit]:
        share = (us / total * 100.0) if total else 0.0
        hint = ", ".join(names[:3])
        extra = f"  {hint}" if hint else ""
        lines.append(
            f"  {short_importer(label, width):{width}s}  {format_ms(us):>8s}  "
            f"{share:4.1f}%{extra}"
        )
    if len(ranked) > limit:
        other = sum(us for _, us, _ in ranked[limit:])
        lines.append(
            f"  {'(others)':{width}s}  {format_ms(other):>8s}  "
            f"{other / total * 100.0:4.1f}%"
        )
    return lines


def parse_forbid_names(raw: str | None) -> list[str]:
    """Split ``pandas,torch`` into distinct top-level names."""
    if not raw:
        return []
    seen: list[str] = []
    for part in raw.split(","):
        name = part.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def forbidden_hits(costs: dict[str, int], names: list[str]) -> list[tuple[str, int]]:
    """Packages (or modules) that match a ``--forbid`` name.

    ``pandas`` matches both the top-level package and ``pandas.core``.
    """
    wanted = {n.strip() for n in names if n and n.strip()}
    if not wanted:
        return []
    hits: dict[str, int] = {}
    for name, us in costs.items():
        top = name.split(".", 1)[0]
        if name in wanted or top in wanted:
            key = name if name in wanted else top
            hits[key] = hits.get(key, 0) + us
    return sorted(hits.items(), key=lambda item: item[1], reverse=True)


def render_forbid(hits: list[tuple[str, int]]) -> str:
    if not hits:
        return ""
    lines = ["importcost: forbidden imports during collection:"]
    width = max(len(name) for name, _ in hits)
    for name, us in hits:
        lines.append(f"  {name:<{width}s}  {format_ms(us)}")
    return "\n".join(lines)


def render_json(
    costs: dict[str, int],
    *,
    limit: int = 12,
    total_us: int | None = None,
    unit: str = "packages",
    budget_ms: float | None = None,
    forbid: list[str] | None = None,
    forbidden: list[tuple[str, int]] | None = None,
    repeat: int = 1,
    min_us: int | None = None,
    max_us: int | None = None,
    importers: dict[str, str] | None = None,
) -> str:
    shown_total = sum(costs.values())
    total = shown_total if total_us is None else total_us
    ranked = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    total_ms = total / 1000.0
    top = ranked if limit <= 0 else ranked[:limit]
    hits = list(forbidden or [])
    who = importers or {}
    payload = {
        "total_us": total,
        "total_ms": round(total_ms, 3),
        "count": len(costs),
        "grouped_by": "module" if unit == "modules" else "package",
        "budget_ms": budget_ms,
        "budget_ok": None if budget_ms is None else total_ms <= budget_ms,
        "forbid": list(forbid or []),
        "forbidden": [
            {"name": name, "self_us": us, "self_ms": round(us / 1000.0, 3)}
            for name, us in hits
        ],
        "forbid_ok": None if not (forbid or []) else not hits,
        "repeat": repeat,
        "min_us": min_us,
        "max_us": max_us,
        "importers": who or None,
        "rows": [
            {
                "name": name,
                "self_us": us,
                "self_ms": round(us / 1000.0, 3),
                "share": (us / total) if total else 0.0,
                "importer": who.get(name),
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


# Ignore sub-millisecond jitter when ranking shared packages.
_DELTA_FLOOR_US = 1000


def diff_profiles(
    now: dict[str, int],
    before: dict[str, int],
    *,
    now_total: int | None = None,
    before_total: int | None = None,
) -> dict:
    """Structured before/after: added, removed, and per-package deltas."""
    now_us = sum(now.values()) if now_total is None else now_total
    before_us = sum(before.values()) if before_total is None else before_total
    added = sorted(set(now) - set(before), key=lambda n: now[n], reverse=True)
    gone = sorted(set(before) - set(now), key=lambda n: before[n], reverse=True)
    slower: list[dict] = []
    faster: list[dict] = []
    for name in set(now) & set(before):
        delta_us = now[name] - before[name]
        if abs(delta_us) < _DELTA_FLOOR_US:
            continue
        row = {
            "name": name,
            "delta_us": delta_us,
            "before_us": before[name],
            "now_us": now[name],
        }
        if delta_us > 0:
            slower.append(row)
        else:
            faster.append(row)
    slower.sort(key=lambda row: row["delta_us"], reverse=True)
    faster.sort(key=lambda row: row["delta_us"])
    return {
        "before_us": before_us,
        "now_us": now_us,
        "delta_us": now_us - before_us,
        "added": [{"name": n, "self_us": now[n]} for n in added],
        "removed": [{"name": n, "self_us": before[n]} for n in gone],
        "slower": slower,
        "faster": faster,
    }


def render_compare(
    now: dict[str, int],
    before: dict[str, int],
    *,
    now_total: int | None = None,
    before_total: int | None = None,
) -> str:
    diff = diff_profiles(
        now, before, now_total=now_total, before_total=before_total
    )
    delta = diff["delta_us"]
    if delta < 0:
        arrow = "faster"
    elif delta > 0:
        arrow = "slower"
    else:
        arrow = "unchanged"
    lines = [
        f"compared with saved profile  before {format_ms(diff['before_us'])}  "
        f"now {format_ms(diff['now_us'])}  {format_ms(abs(delta))} {arrow}",
        "",
    ]
    added = diff["added"]
    gone = diff["removed"]
    if added:
        lines.append("  newly imported:")
        for row in added[:8]:
            lines.append(f"    {row['name']:<24} +{format_ms(row['self_us'])}")
    if gone:
        lines.append("  no longer imported:")
        for row in gone[:8]:
            lines.append(f"    {row['name']:<24} -{format_ms(row['self_us'])}")
    if diff["slower"]:
        lines.append("  slower:")
        for row in diff["slower"][:8]:
            lines.append(f"    {row['name']:<24} +{format_ms(row['delta_us'])}")
    if diff["faster"]:
        lines.append("  faster:")
        for row in diff["faster"][:8]:
            lines.append(f"    {row['name']:<24} -{format_ms(-row['delta_us'])}")
    if not added and not gone and not diff["slower"] and not diff["faster"]:
        lines.append("  same package set")
    return "\n".join(lines)
