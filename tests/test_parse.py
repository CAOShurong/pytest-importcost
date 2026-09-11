import json

from pytest_importcost.parse import (
    costs_from_saved,
    diff_profiles,
    drop_stdlib,
    forbidden_hits,
    median_cost_map,
    median_us,
    parse_forbid_names,
    parse_package_self_us,
    parse_self_us,
    render_compare,
    render_forbid,
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


def test_compare_reports_new_and_gone_packages():
    text = render_compare({"pandas": 4000, "json": 100}, {"json": 100, "os": 50})
    assert "newly imported" in text
    assert "pandas" in text
    assert "no longer imported" in text
    assert "os" in text


def test_costs_from_saved_json_payload():
    payload = json.loads(render_json({"pandas": 4000, "json": 100}, limit=0))
    total, costs = costs_from_saved(payload)
    assert total == 4100
    assert costs["pandas"] == 4000


def test_compare_reports_slower_and_faster_packages():
    text = render_compare(
        {"pandas": 8000, "json": 100, "pygments": 1500},
        {"pandas": 4000, "json": 100, "pygments": 4000},
    )
    assert "slower:" in text
    assert "pandas" in text
    assert "faster:" in text
    assert "pygments" in text


def test_diff_profiles_ignores_sub_ms_jitter():
    diff = diff_profiles({"pandas": 4050, "json": 100}, {"pandas": 4000, "json": 100})
    assert diff["slower"] == []
    assert diff["faster"] == []
    assert diff["added"] == []


def test_parse_forbid_names_splits_and_dedupes():
    assert parse_forbid_names(" pandas, torch,pandas ") == ["pandas", "torch"]
    assert parse_forbid_names("") == []
    assert parse_forbid_names(None) == []


def test_forbidden_hits_matches_top_level_and_submodule():
    hits = forbidden_hits(
        {"pandas": 4000, "pandas.core": 800, "json": 100},
        ["pandas", "torch"],
    )
    assert hits[0][0] == "pandas"
    assert hits[0][1] == 4800
    assert all(name != "json" for name, _ in hits)
    assert "forbidden imports" in render_forbid(hits)


def test_median_us_odd_and_even():
    assert median_us([3, 1, 2]) == 2
    assert median_us([4, 1, 2, 3]) == 2
    assert median_us([]) == 0


def test_median_cost_map_fills_missing_with_zero():
    merged = median_cost_map([{"pandas": 100, "json": 10}, {"pandas": 300}])
    assert merged["pandas"] == 200
    assert merged["json"] == 5


def test_render_json_forbid_fields():
    payload = json.loads(
        render_json(
            {"pandas": 400_000, "json": 50_000},
            budget_ms=100.0,
            forbid=["pandas"],
            forbidden=[("pandas", 400_000)],
        )
    )
    assert payload["forbid"] == ["pandas"]
    assert payload["forbid_ok"] is False
    assert payload["forbidden"][0]["name"] == "pandas"
