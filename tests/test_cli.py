import json
from pathlib import Path

from pytest_importcost.cli import main
from pytest_importcost.run import measured_collect

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "tiny_suite"


def test_measured_collect_on_tiny_suite():
    report, code = measured_collect([str(FIXTURE)], timeout=60)
    assert "pytest collection import cost" in report
    assert "json" in report or "pytest" in report
    assert code in (0, 5)


def test_cli_exit_zero(capsys):
    rc = main(["--", str(FIXTURE)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pytest collection import cost" in out


def test_budget_fail_when_limit_is_tiny():
    report, code = measured_collect(
        [str(FIXTURE)], timeout=60, budget_ms=0.001
    )
    assert code == 1
    assert "budget exceeded" in report


def test_budget_pass_when_limit_is_huge():
    report, code = measured_collect(
        [str(FIXTURE)], timeout=60, budget_ms=1_000_000
    )
    assert code == 0
    assert "budget exceeded" not in report


def test_json_output_is_object():
    report, code = measured_collect([str(FIXTURE)], timeout=60, as_json=True)
    payload = json.loads(report)
    assert code == 0
    assert payload["total_us"] > 0
    assert payload["rows"]
    assert payload["grouped_by"] == "package"


def test_cli_json_and_modules(capsys):
    rc = main(["--json", "--modules", "--", str(FIXTURE)])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["grouped_by"] == "module"
