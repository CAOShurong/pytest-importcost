import os
import subprocess
import sys
from pathlib import Path

from pytest_importcost.plugin import strip_importcost_args

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "tiny_suite"
SRC = Path(__file__).resolve().parents[1] / "src"


def test_strip_importcost_args_drops_flags_and_values():
    leftover = strip_importcost_args(
        [
            "--importcost",
            "--importcost-json",
            "--importcost-modules",
            "--importcost-hide-stdlib",
            "--importcost-budget-ms",
            "200",
            "--importcost-limit=5",
            "--importcost-save",
            "before.json",
            "--importcost-compare=before.json",
            "--importcost-slower-ms",
            "50",
            "--importcost-forbid",
            "pandas,torch",
            "--importcost-repeat",
            "3",
            "--importcost-blame",
            "--importcost-plugins",
            "--importcost-suite",
            "--importcost-new",
            "tests",
            "-q",
        ]
    )
    assert leftover == ["tests", "-q"]


def test_plugin_budget_fails_via_pytest():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_importcost.plugin",
            "--importcost",
            "--importcost-budget-ms",
            "0.001",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        check=False,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 1, blob[-2000:]
    assert "budget exceeded" in blob


def test_plugin_forbid_fails_via_pytest():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_importcost.plugin",
            "--importcost",
            "--importcost-forbid",
            "json",
            str(FIXTURE),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        check=False,
    )
    blob = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 1, blob[-2000:]
    assert "forbidden imports" in blob
