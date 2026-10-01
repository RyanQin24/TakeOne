# Preview loading verification

Date: September 13, 2026 (America/Toronto). The full runner completed September 14 in UTC.

## Result

The stale planner was restarted. The browser now clears the previous shot while a new movement is being calculated, applies the solved starting pose before showing the cart and arms, and provides an explicit Retry preview action on failure. Rapid selection changes apply only the latest selection. Concurrent preview requests wait for the planner rather than immediately failing because another tab is compiling.

The process-freshness check still covers motion source and drive configuration. Changes to unrelated Director, editor, recording, and voice service code remain recorded in full plan provenance but no longer incorrectly invalidate the loaded motion planner. No calibration originals, motor limits, hardware settings, or live robot commands were changed by this fix.

## Browser checks

- Reproduced the stale-planner message before the restart.
- Confirmed failed/loading previews hide the unposed cart and old camera image, clear statistics and timeline values, and disable playback/preparation for the unavailable shot.
- After restarting the planner, Retry preview successfully loaded Whip pan.
- Selected all 28 movement presets individually; each reached its named ready state with playback enabled.
- Loaded both existing tools: Draw a ground path and Orbit template.
- Rapidly selected full orbit, Dolly Zoom out, Pan left, side tracking, and Hero reveal; the final preview, timeline, and camera labels matched Hero reveal.
- Entered an invalid radius after a successful load. The failure cleared the previous shot; restoring a valid radius loaded the correct movement again.
- Visually checked the cart and actor separation in Top and Studio views.
- Confirmed the actor remains visible as a reference while drawing a path, with the unposed cart hidden.
- Prepared Whip pan motor commands successfully using the offline Prepare robot run action. No Run on robot action or device actuation was performed.
- Left the working simulator tab on Whip pan, at its final filming frame in Studio view.

## Automated checks

The documented PowerShell test launcher was attempted but Windows blocked the unsigned script. The execution policy was left unchanged. Its underlying runner was executed directly:

```powershell
C:\TakeOne\.venv\Scripts\python.exe C:\TakeOne\scripts\verify.py --output-dir C:\TakeOne\data\verification\preview-loading-20260913
```

| Check | Result | Evidence |
| --- | --- | --- |
| Relevant motion/loading modules | 72 passed: cart response 16, studio robot 14, movement library 15, shot templates 9, drawn path 8, orbit previs 10 | check-0.txt |
| Frontend tests | 173 passed, 0 failed | check-2.txt |
| Frontend syntax | Passed, including the final path-drawing change | check-3.txt |
| Preservation audit | Passed; 1,086 LeRobot files checked, no audit failures | check-4.txt and preservation.json |
| Targeted Python lint/format and source diff whitespace | Passed for this fix | Interactive verification |
| Full root Python discovery | 431 tests; 4 failures and 12 errors | check-0.txt |
| Separate simulation suite | 29 tests; 5 failures and 1 error | check-1.txt |
| Repository-wide lint | One import-order error in tests/editor/test_plan.py | check-5.txt |
| Repository-wide format check | 37 files would be reformatted | check-6.txt |

The overall verification runner exited 1. The full repository is not reported as passing.

The root discovery failures/errors are in editor test imports, tests.fixtures imports, the older cart-plan wrist-roll check, and planning assertions/signatures. The separate simulation failures concern model/camera pose, arm-led tracking, powered-axle coordinates, mount geometry, height expectations, and an infeasible-request case. Those files were outside this loading fix and were not modified to suppress the failures. The repository-wide formatting findings also remain unchanged. These observations do not establish when those unrelated failures were introduced.

The new regression checks verify that unrelated service edits do not stop planning, motion/drive edits still require a fresh process, a queued preview request returns its requested movement, and all default preset frames keep the cart and actor centres separated, including calibration/setup. The separation check is a test assertion, not a new runtime threshold or playback restriction.

## Recovery and scope

Exact original copies of the five changed product/frontend files are under C:\TakeOne\data\recovery\preview-loading-20260913. The corresponding before/after mapping is documented in C:\TakeOne\docs\camera-movement-library.md.

The local server was verified healthy with robot playback idle and hardwareConnected false. Browser playback and offline preparation validate the software path; this run contains no physical robot test.
