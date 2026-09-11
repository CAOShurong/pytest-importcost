# pytest-importcost

**pytest collection took 4 seconds and `--durations` blamed nothing. This names the imports.**

```bash
pip install pytest-importcost
pytest --importcost
```

or, without installing as a plugin:

```bash
uvx --from pytest-importcost importcost
```

It re-runs `pytest --collect-only` under CPython `-X importtime` and prints package costs.
Real output on this repo's tiny example suite (no pandas — pytest itself dominates):

```text
pytest collection import cost  152 ms  across 149 packages

  _pytest    ████████████████████████████   40.6 ms  26.7%
  pygments   ██████░░░░░░░░░░░░░░░░░░░░░░   8.55 ms   5.6%
  importlib  █████░░░░░░░░░░░░░░░░░░░░░░░   7.43 ms   4.9%
```

If `conftest.py` imports pandas or torch, those names take the top rows.
That number is **import time during collection**, not test runtime. The usual
`python -X importtime -m pytest` dump is 900 nested lines; this is the table.

## Why it exists

Blog posts tell you to paste importtime into a visualizer. There was no
`pytest --flag` that just prints who paid. `--durations` ranks tests;
collection imports never show up there.

## Notes

- Child run is `--collect-only`. Tests are not executed in the measured process.
- Globally installed pytest plugins are **excluded** by default (`PYTEST_DISABLE_PLUGIN_AUTOLOAD`), so you see the suite, not hypothesis/xdist sitting in site-packages. Pass `importcost --plugins` to include them — that dump is often why "pytest is slow on my laptop".
- Pytest exit code 5 (no tests) is treated as a successful measurement.
- Requires CPython (uses `-X importtime`).
