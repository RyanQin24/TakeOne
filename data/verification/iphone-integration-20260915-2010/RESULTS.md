# iPhone integration attempt — 2026-09-15

Status: NOT INTEGRATED. Remote tool code-write requests were blocked.
No application integration edits were applied by this attempt.
Do not use the incomplete client staged under data/recovery/iphone-integration-20260915-2010/proposed.
The supplied standalone bundle remains a separate, uninstalled implementation.
Other development changes were present and continued during verification; this was not a frozen release tree.

## Observed checks
- Product baseline: 755 tests, 2 failures and 3 errors, 651.796 seconds (baseline/check-0.txt).
- Targeted existing camera/playback/clock regression: 27 tests passed, 21.968 seconds.
- Simulation pass: deliberately stopped this attempt's duplicate subprocess; NOT a passing result.
- Browser tests: 249 passed (baseline/check-2.txt).
- Browser syntax checks: passed (baseline/check-3.txt).
- Preservation integrity audit: passed (baseline/check-4.txt).
- Ruff lint: 1 import-order error in tests/test_performers.py (baseline/check-5.txt).
- Ruff format: 9 files require formatting, including the earlier phone drafts (baseline/check-6.txt).
- Chrome rendered the existing Shot Studio; screenshot is baseline-studio.png.
- Live /api/health reported C:\TakeOne, healthy, hardware disconnected, robot idle.
- Interactive browser automation was blocked; no scripted zoom-control assertion was completed.
- All 6 calibration file hashes matched the before snapshot when rechecked.
- The iPhone configuration remained disabled; no endpoint was supplied or contacted.

The product baseline errors include missing actor appearance in Director example documents,
a missing creative result, a planning job remaining in brief phase, and a shot-repair expectation mismatch.
These results predate any iPhone integration by this attempt.

The actual camera/worker integration, physical iPhone capture, LUT pixels and robot playback remain unverified.
