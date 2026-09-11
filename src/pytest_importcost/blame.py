"""Attribute collection imports to the conftest / test file that first pulled them in.

Child-only: enabled with ``_PYTEST_IMPORTCOST_BLAME=1``. Snapshots ``sys.modules``
around pytest collectors so import-time measurement is not wrapped.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

BLAME_MARK = "pytest-importcost-blame:"

class _ConftestBlameFinder:
    """Temporary meta_path entry: record imports whose stack includes conftest.py."""

    def __init__(self, tracker: "BlameTracker") -> None:
        self.tracker = tracker

    def find_spec(self, fullname: str, path: object = None, target: object = None):
        top = (fullname or "").split(".", 1)[0]
        if not top or top in self.tracker.first_importer:
            return None
        frame = sys._getframe(1)
        while frame is not None:
            fn = frame.f_code.co_filename
            if os.path.basename(fn) == "conftest.py":
                self.tracker.first_importer[top] = _rel(fn)
                break
            frame = frame.f_back
        return None


_TRACK_COLLECTORS = frozenset(
    {
        "Module",
        "Package",
        "Dir",
        "Directory",
        "PytestDir",
        "Session",
        "File",
    }
)


def _rel(path: str) -> str:
    try:
        rel = os.path.relpath(path, os.getcwd())
    except ValueError:
        rel = path
    return rel.replace("\\", "/")


def _is_suite_file(path: str) -> bool:
    base = os.path.basename(path)
    return (
        base == "conftest.py"
        or (base.startswith("test_") and base.endswith(".py"))
        or base.endswith("_test.py")
    )


def _noise_label(path: str) -> bool:
    n = path.replace("\\", "/").lower()
    return "/_pytest/" in n or "/site-packages/" in n or n.endswith("/pytest/__init__.py")


class BlameTracker:
    """First-seen top-level package → suite file (or a coarse bucket)."""

    def __init__(self) -> None:
        self.first_importer: dict[str, str] = {}
        self._seen: set[str] = set(sys.modules)
        self._emitted = False

    def mark_seen(self) -> None:
        """Treat currently loaded modules as already explained (pytest internals)."""
        self._seen = set(sys.modules)

    def watch_conftest(self, on: bool) -> None:
        """Install/remove a short-lived importer that blames conftest.py frames."""
        finder = getattr(self, "_finder", None)
        if on:
            if finder is None:
                finder = _ConftestBlameFinder(self)
                self._finder = finder
            if finder not in sys.meta_path:
                sys.meta_path.insert(0, finder)
            return
        if finder is not None:
            try:
                sys.meta_path.remove(finder)
            except ValueError:
                pass

    def snap(self, collector: object | None = None, *, label: str | None = None) -> None:
        if collector is not None and type(collector).__name__ not in _TRACK_COLLECTORS:
            return
        now = set(sys.modules)
        new = now - self._seen
        self._seen = now
        if not new:
            return
        if collector is not None:
            label = self._label(collector, new)
        elif label is None:
            label = self._label_from_new(new)
        for name in new:
            top = name.split(".", 1)[0]
            if not top or top in self.first_importer:
                continue
            self.first_importer[top] = label

    def note(self, collector: object, new_names: set[str]) -> None:
        # Kept for tests; collection path uses snap().
        if not new_names:
            return
        kind = type(collector).__name__
        if kind not in _TRACK_COLLECTORS:
            return
        label = self._label(collector, new_names)
        for name in new_names:
            top = name.split(".", 1)[0]
            if not top or top in self.first_importer:
                continue
            self.first_importer[top] = label

    def _label_from_new(self, new_names: set[str]) -> str:
        for name in new_names:
            mod = sys.modules.get(name)
            path = getattr(mod, "__file__", None) if mod is not None else None
            if path and os.path.basename(path) == "conftest.py":
                return _rel(path)
        return "(collection startup)"

    def _label(self, collector: object, new_names: set[str]) -> str:
        path = getattr(collector, "path", None) or getattr(collector, "fspath", None)
        if path is not None:
            text = _rel(str(path))
            if _is_suite_file(text) and not _noise_label(text):
                return text
        return self._label_from_new(new_names)

    def dump(self) -> dict[str, str]:
        return dict(self.first_importer)

    def emit(self) -> None:
        if self._emitted:
            return
        self._emitted = True
        sys.stderr.write(BLAME_MARK + json.dumps(self.dump(), separators=(",", ":")) + "\n")


_tracker: BlameTracker | None = None


def enabled() -> bool:
    return (
        os.environ.get("_PYTEST_IMPORTCOST_CHILD") == "1"
        and os.environ.get("_PYTEST_IMPORTCOST_BLAME") == "1"
    )


def tracker() -> BlameTracker | None:
    global _tracker
    if not enabled():
        return None
    if _tracker is None:
        _tracker = BlameTracker()
    return _tracker


def extract_blame(text: str) -> dict[str, str]:
    """Parse the ``pytest-importcost-blame:`` line out of child output."""
    for line in text.splitlines():
        raw = line.strip()
        if not raw.startswith(BLAME_MARK):
            continue
        payload = raw[len(BLAME_MARK) :].strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    return {}


def file_costs(
    costs: dict[str, int], importers: dict[str, str]
) -> list[tuple[str, int, list[str]]]:
    """Sum package self-us by first-importer file. Ranked expensive-first."""
    us_by_file: dict[str, int] = defaultdict(int)
    names_by_file: dict[str, list[str]] = defaultdict(list)
    for name, us in costs.items():
        label = importers.get(name, "(collection startup)")
        us_by_file[label] += us
        names_by_file[label].append(name)
    ranked = sorted(us_by_file.items(), key=lambda item: item[1], reverse=True)
    return [
        (label, us, sorted(names_by_file[label], key=lambda n: costs.get(n, 0), reverse=True))
        for label, us in ranked
    ]
