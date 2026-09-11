import json
import tempfile
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


def test_save_and_compare_same_suite():
    with tempfile.TemporaryDirectory() as tmp:
        baseline = Path(tmp) / "before.json"
        report, code = measured_collect(
            [str(FIXTURE)], timeout=60, save_path=str(baseline)
        )
        assert code == 0
        assert baseline.is_file()
        report, code = measured_collect(
            [str(FIXTURE)],
            timeout=60,
            compare_path=str(baseline),
            slower_ms=1_000_000,
        )
        assert code == 0
        assert "compared with saved profile" in report


def test_cli_json_and_modules(capsys):
    rc = main(["--json", "--modules", "--", str(FIXTURE)])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["grouped_by"] == "module"


def test_forbid_unknown_package_passes():
    report, code = measured_collect(
        [str(FIXTURE)], timeout=60, forbid=["definitely_not_imported_xyz"]
    )
    assert code == 0
    assert "forbidden imports" not in report


def test_forbid_json_fails_because_pytest_imports_it():
    report, code = measured_collect(
        [str(FIXTURE)], timeout=60, forbid=["json"]
    )
    assert code == 1
    assert "forbidden imports" in report
    assert "json" in report


def test_repeat_median_json_fields():
    report, code = measured_collect(
        [str(FIXTURE)], timeout=60, as_json=True, repeat=2
    )
    payload = json.loads(report)
    assert code == 0
    assert payload["repeat"] == 2
    assert payload["min_us"] <= payload["total_us"] <= payload["max_us"]
    assert payload["total_us"] > 0


def test_cli_forbid_unknown_exits_zero(capsys):
    rc = main(["--forbid", "definitely_not_imported_xyz", "--", str(FIXTURE)])
    capsys.readouterr()
    assert rc == 0


BLAME = Path(__file__).resolve().parents[1] / "examples" / "blame_suite"


def test_suite_imports_survive_pytest_capture():
    """Child must disable capture or -X importtime never sees the suite."""
    report, code = measured_collect(
        [str(BLAME)], timeout=60, hide_stdlib=True, limit=50
    )
    assert code in (0, 5)
    assert "pkg_from_conf" in report
    assert "pkg_from_case" in report


def test_blame_pins_helpers_to_suite_files():
    report, code = measured_collect(
        [str(BLAME)], timeout=60, blame=True, hide_stdlib=True, limit=50
    )
    assert code in (0, 5)
    blob = report.replace("\\", "/")
    assert "pkg_from_conf" in blob
    assert "pkg_from_case" in blob
    assert "conftest.py" in blob
    assert "test_a.py" in blob
    assert "By file" in blob


def test_blame_json_importers():
    report, code = measured_collect(
        [str(BLAME)], timeout=60, blame=True, as_json=True, hide_stdlib=True
    )
    payload = json.loads(report)
    assert code in (0, 5)
    importers = {
        name: (path or "").replace("\\", "/")
        for name, path in (payload.get("importers") or {}).items()
    }
    assert "conftest.py" in importers.get("pkg_from_conf", "")
    assert "test_a.py" in importers.get("pkg_from_case", "")


def test_cli_blame(capsys):
    rc = main(["--blame", "--hide-stdlib", "--limit", "50", "--", str(BLAME)])
    out = capsys.readouterr().out.replace("\\", "/")
    assert rc == 0
    assert "pkg_from_conf" in out
    assert "conftest.py" in out
