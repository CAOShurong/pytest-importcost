# pytest-importcost

**pytest collection took 4 seconds and `--durations` blamed nothing. This names the imports.**

[![CI](https://github.com/CAOShurong/pytest-importcost/actions/workflows/ci.yml/badge.svg)](https://github.com/CAOShurong/pytest-importcost/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
pip install "git+https://github.com/CAOShurong/pytest-importcost.git"
pytest --importcost
```

It re-runs `pytest --collect-only` under CPython `-X importtime` and prints package costs.
Real output on this repo's tiny example suite (no pandas — pytest itself dominates):

```text
pytest collection import cost  166 ms  across 149 packages

  _pytest    ████████████████████████████   47.9 ms  28.8%
  pygments   ██████░░░░░░░░░░░░░░░░░░░░░░   9.72 ms   5.8%
  importlib  █████░░░░░░░░░░░░░░░░░░░░░░░   8.63 ms   5.2%
```

If `conftest.py` imports pandas or torch, those names take the top rows.
That number is **import time during collection**, not test runtime. The usual
`python -X importtime -m pytest` dump is 900 nested lines; this is the table.

## CI budget

Fail the job when collection imports grow, or when a named package appears
(someone added pandas to `conftest.py` — a 500 ms budget still passes on a
fast runner):

```bash
pytest --importcost --importcost-budget-ms 500
pytest --importcost --importcost-forbid pandas,torch
pytest --importcost --importcost-repeat 5 --importcost-budget-ms 500
```

`--importcost-repeat 5` runs collection five times and ranks the **median**.
Import-time is wall-clock; a single run will flake a tight CI budget.

`--importcost-json` prints `{total_ms, rows, budget_ok}` instead of the table.
`--importcost-modules` ranks `pandas.core` rather than rolling it into `pandas`.
`--importcost-hide-stdlib` drops `json`/`os` from the rows (the total still includes them).
`--importcost-forbid pandas,torch` fails if those packages appear at all — a
budget of 800 ms still passes when someone puts `import torch` in `conftest.py`
on a fast CI runner; a forbid list does not.
`--importcost-blame` adds the conftest or test file that **first imported**
each package, plus a by-file rollup. That is the difference between "pandas
is expensive" and "tests/test_ml.py imported pandas at collection time":

```text
By file (new packages first seen there)
  (collection startup)               74.0 ms  _pytest, pygments
  examples/blame_suite/conftest.py    0.38 ms  pkg_from_conf
  examples/blame_suite/test_a.py      0.34 ms  pkg_from_case
```

`(collection startup)` is pytest itself. The next rows are the files you can edit.

The CLI is the same flags without the `importcost-` prefix:

```bash
importcost --budget-ms 500 --json -- examples/
importcost --repeat 5 --budget-ms 500 -- examples/
importcost --forbid pandas,torch -- examples/
importcost --blame --hide-stdlib -- examples/blame_suite/
importcost --save before.json -- examples/
importcost --compare before.json --slower-ms 50 -- examples/
```

`--compare` prints newly imported packages **and** packages that got slower or
faster (ignoring sub-millisecond jitter). `--slower-ms` fails the job if total
collection import cost grew by more than that many milliseconds.

## Why it exists

Blog posts tell you to paste importtime into a visualizer. There was no
`pytest --flag` that just prints who paid. `--durations` ranks tests;
collection imports never show up there.

## Notes

- Child run is `--collect-only --capture=no`. Tests are not executed in the measured process. pytest capture otherwise redirects fd 2 and hides `-X importtime` for the suite.
- Globally installed pytest plugins are **excluded** by default (`PYTEST_DISABLE_PLUGIN_AUTOLOAD`), so you see the suite, not hypothesis/xdist sitting in site-packages. Pass `importcost --plugins` to include them — that dump is often why "pytest is slow on my laptop".
- Pytest exit code 5 (no tests) is treated as a successful measurement.
- Requires CPython (uses `-X importtime`).
- Not on PyPI yet; the install line above is the git URL. `uvx --from git+https://github.com/CAOShurong/pytest-importcost.git importcost` is the no-install equivalent.
