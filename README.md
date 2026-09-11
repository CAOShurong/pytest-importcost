# pytest-importcost

**pytest collection took 4 seconds and `--durations` blamed nothing. This names the imports.**

[![CI](https://github.com/CAOShurong/pytest-importcost/actions/workflows/ci.yml/badge.svg)](https://github.com/CAOShurong/pytest-importcost/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
pip install "git+https://github.com/CAOShurong/pytest-importcost.git"
pytest --importcost --importcost-suite
```

`--importcost-suite` ranks packages **your** `conftest.py` / `test_*.py` first
imported, not pytest itself. Measured on this repo (`examples/blame_suite`):

```text
pytest collection import cost  156 ms  across 18 packages

  suite-imported  2 packages  0.57 ms  (pytest/startup omitted from rows)

  pkg_from_conf  ████████████████████████████   0.29 ms   0.2%  examples/blame_suite/conftest.py
  pkg_from_case  ████████████████████████████   0.29 ms   0.2%  examples/blame_suite/test_a.py

By file (new packages first seen there)
  examples/blame_suite/conftest.py   0.29 ms   0.2%  pkg_from_conf
  examples/blame_suite/test_a.py     0.29 ms   0.2%  pkg_from_case
```

Without `--suite`, pytest dominates the same machine (tiny example suite):

```text
pytest collection import cost  156 ms  across 149 packages

  _pytest    ████████████████████████████   44.2 ms  28.3%
  pygments   ██████░░░░░░░░░░░░░░░░░░░░░░   8.92 ms   5.7%
  importlib  ████░░░░░░░░░░░░░░░░░░░░░░░░   6.85 ms   4.4%
```

If `conftest.py` imports pandas or torch, those names take the top `--suite` rows.
That number is **import time during collection**, not test runtime. The usual
`python -X importtime -m pytest` dump is 900 nested lines; this is the table.

## CI budget

Fail the job when collection imports grow, when a named package appears, or
when the suite starts importing something that was not in the saved profile
(someone added pandas to `conftest.py` — a 500 ms budget still passes on a
fast runner):

```bash
pytest --importcost --importcost-budget-ms 500
pytest --importcost --importcost-forbid pandas,torch
pytest --importcost --importcost-repeat 5 --importcost-budget-ms 500
pytest --importcost --importcost-compare before.json --importcost-new
pytest --importcost --importcost-suite --importcost-compare before.json --importcost-new
```

`--importcost-repeat 5` runs collection five times and ranks the **median**.
Import-time is wall-clock; a single run will flake a tight CI budget.

`--importcost-new` (needs `--importcost-compare`) fails if any **new** package
showed up. With `--importcost-suite`, only new suite-imported packages fail —
a pytest upgrade that pulls in another helper does not.

On GitHub Actions, a markdown table is appended to `$GITHUB_STEP_SUMMARY`
automatically. `--suite` also emits `::notice file=conftest.py::…` annotations
on the files that first imported each package.

`--importcost-json` prints `{total_ms, rows, budget_ok, suite_count}` instead of the table.
`--importcost-modules` ranks `pandas.core` rather than rolling it into `pandas`.
`--importcost-hide-stdlib` drops `json`/`os` from the rows (the total still includes them).
`--importcost-forbid pandas,torch` fails if those packages appear at all — a
budget of 800 ms still passes when someone puts `import torch` in `conftest.py`
on a fast CI runner; a forbid list does not.
`--importcost-blame` adds the conftest or test file that **first imported**
each package, plus a by-file rollup (implied by `--importcost-suite`).

The CLI is the same flags without the `importcost-` prefix:

```bash
importcost --budget-ms 500 --json -- examples/
importcost --repeat 5 --budget-ms 500 -- examples/
importcost --forbid pandas,torch -- examples/
importcost --suite --hide-stdlib -- examples/blame_suite/
importcost --save before.json -- examples/
importcost --compare before.json --new --slower-ms 50 -- examples/
```

`--compare` prints newly imported packages **and** packages that got slower or
faster (ignoring sub-millisecond jitter). `--slower-ms` fails the job if total
collection import cost grew by more than that many milliseconds. `--new` fails
if the package set grew.

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
