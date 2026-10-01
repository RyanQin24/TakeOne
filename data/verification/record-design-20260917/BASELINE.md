# Baseline before prompt 16 (Record dual-frame, iPhone capture, one design system)

Recorded 2026-09-17 against `b615d77`. Host: Linux VM with the Windows checkout
mounted read/write; Python 3.10.12 with a `StrEnum`/`datetime.UTC` shim on
`PYTHONPATH` (the repo requires >=3.12); `PYTHONPATH` also carries `packages/`
in place of an editable install. No `mujoco`, no `scipy`, no network egress to
the robot, no phone, no runnable `ruff` (the pinned binary in `.venv` is not for
this architecture).

The server cannot boot here: `apps/rehearsal/server.py:17` reaches
`takeone.direct` which imports `mujoco`, and `:35` imports
`takeone.simulation.robot.visual_model`. Every claim below is therefore about
files and tests, never about a served route.

## Commands and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p "test_[a-l]*.py"` | 215 tests, 0 failures, 17 errors |
| `python3 -m unittest discover -s tests -p "test_[m-z]*.py"` | 362 tests, 0 failures, 47 errors, 9 skipped |
| combined | **577 tests, 0 failures, 64 errors, 9 skipped** |
| `cd apps/rehearsal && npm test` | **279 tests, 277 pass, 2 fail** |
| `cd apps/rehearsal && npm run check` | exit 0 |
| `python3 scripts/check_integrity.py` | exit 0, `"passed": true` |

Split into two patterns only because each shell call here is capped at 180 s;
the two batches are disjoint and their union is the full discovery set.

## Error breakdown (all missing-dependency, none an assertion)

- 37 `No module named 'scipy'`
- 26 `No module named 'mujoco'` (25 direct, 1 through a nested subprocess)
- 1 `module 'sqlite3' has no attribute 'SQLITE_BUSY'` (added in Python 3.11)

`grep -c "^FAIL:"` over both logs returns 0.

## Node failures (2, one shared cause)

- `tests/voice-boundary.test.mjs`
- `tests/voice-view.test.mjs`

Both go through `tests/fixtures/voice-wire.mjs`, which hardcodes `.venv/bin/python`
with no environment override. Pre-existing and unrelated to this work.

## Comparison rule

Compare failing-test *name sets*, never counts against zero. The baseline name
set is `python-error-name-set.txt` beside this file.
