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

It re-runs `pytest --collect-only` under CPython `-X importtime` and prints package costs:

```text
pytest collection import cost  1.84 s  across 40 packages

  pandas   ████████████████████████████   412 ms  22.4%
  numpy    ███████████████████░░░░░░░░░   280 ms  15.2%
  json     ██░░░░░░░░░░░░░░░░░░░░░░░░░░    12 ms   0.7%
```

That number is **import time during collection**, not test runtime. The usual
`python -X importtime -m pytest` dump is 900 nested lines; this is the
actionable table.

## Why it exists

Blog posts tell you to paste importtime into a visualizer. There was no
`pytest --flag` that just prints who paid. `--durations` ranks tests;
collection imports never show up there.

## Notes

- Child run is `--collect-only`. Tests are not executed in the measured process.
- Pytest exit code 5 (no tests) is treated as a successful measurement.
- Requires CPython (uses `-X importtime`).
