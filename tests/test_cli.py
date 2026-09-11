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
