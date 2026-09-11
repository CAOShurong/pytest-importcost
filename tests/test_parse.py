from pytest_importcost.parse import parse_package_self_us, render_report


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


def test_render_includes_total_and_ranking():
    text = render_report({"pandas": 400_000, "json": 50_000, "os": 1_000})
    assert "pytest collection import cost" in text
    assert "pandas" in text
    assert "json" in text
    assert text.index("pandas") < text.index("json")
