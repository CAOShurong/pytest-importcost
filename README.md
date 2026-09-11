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
pytest collection import cost  153 ms  across 149 packages

  _pytest    ████████████████████████████   40.3 ms  26.4%
  pygments   ██████░░░░░░░░░░░░░░░░░░░░░░   8.59 ms   5.6%
  importlib  █████░░░░░░░░░░░░░░░░░░░░░░░   6.83 ms   4.5%
```

If `conftest.py` imports pandas or torch, those names take the top rows.
That number is **import time during collection**, not test runtime. The usual
`python -X importtime -m pytest` dump is 900 nested lines; this is the table.

## CI budget

Fail the job when collection imports grow (someone added pandas to `conftest.py`):

```bash
pytest --importcost --importcost-budget-ms 500
```

`--importcost-json` prints `{total_ms, rows, budget_ok}` instead of the table.
`--importcost-modules` ranks `pandas.core` rather than rolling it into `pandas`.
`--importcost-hide-stdlib` drops `json`/`os` from the rows (the total still includes them).

The CLI is the same flags without the `importcost-` prefix:

```bash
importcost --budget-ms 500 --json -- examples/
importcost --save before.json -- examples/
importcost --compare before.json --slower-ms 50 -- examples/
```

`--compare` prints newly imported packages. `--slower-ms` fails the job if
total collection import cost grew by more than that many milliseconds.

## Why it exists

Blog posts tell you to paste importtime into a visualizer. There was no
`pytest --flag` that just prints who paid. `--durations` ranks tests;
collection imports never show up there.

## Notes

- Child run is `--collect-only`. Tests are not executed in the measured process.
- Globally installed pytest plugins are **excluded** by default (`PYTEST_DISABLE_PLUGIN_AUTOLOAD`), so you see the suite, not hypothesis/xdist sitting in site-packages. Pass `importcost --plugins` to include them — that dump is often why "pytest is slow on my laptop".
- Pytest exit code 5 (no tests) is treated as a successful measurement.
- Requires CPython (uses `-X importtime`).
- Not on PyPI yet; the install line above is the git URL. `uvx --from git+https://github.com/CAOShurong/pytest-importcost.git importcost` is the no-install equivalent.
