import json

from pytest_importcost.parse import (
    drop_stdlib,
    parse_package_self_us,
    parse_self_us,
    render_json,
    render_report,
)


SAMPLE = """
import time: self [us] | cumulative | imported package
import time:        10 |         10 |   _frozen_importlib
import time:      4000 |       4010 | pandas
import time:       800 |        800 |   pandas.core
import time:      1200 |       1200 | json
hello from the program
"""


def test_groups_by_top_level_and_sums_self():
    costs = parse_package_self_us(SAMPLE)
    assert costs["pandas"] == 4800
    assert costs["json"] == 1200
    assert costs["_frozen_importlib"] == 10


def test_module_group_keeps_full_name():
    costs = parse_self_us(SAMPLE, group="module")
    assert costs["pandas"] == 4000
    assert costs["pandas.core"] == 800
    assert costs["json"] == 1200


def test_render_includes_total_and_ranking():
    text = render_report({"pandas": 400_000, "json": 50_000, "os": 1_000})
    assert "pytest collection import cost" in text
    assert "pandas" in text
    assert "json" in text
    assert text.index("pandas") < text.index("json")


def test_drop_stdlib_keeps_third_party():
    filtered = drop_stdlib({"json": 100, "pandas": 5000, "os": 20})
    assert "pandas" in filtered
    assert "json" not in filtered
    assert "os" not in filtered


def test_render_json_budget_fields():
    payload = json.loads(
        render_json({"pandas": 400_000, "json": 50_000}, budget_ms=100.0)
    )
    assert payload["total_us"] == 450_000
    assert payload["budget_ms"] == 100.0
    assert payload["budget_ok"] is False
    assert payload["rows"][0]["name"] == "pandas"
