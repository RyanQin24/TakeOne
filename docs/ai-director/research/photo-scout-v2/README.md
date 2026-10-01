# TAKE ONE Photo Scout v2 — research deliverables

This bundle contains an implementation assignment, not an installed photo-to-3D feature.

- `13-photo-scout-v2-research.md`: product decision, source audit, geometry, cost policy and evaluation.
- `13-photo-scout-v2-engineering-prompt.md`: the complete assignment for the existing C:\TakeOne checkout.
- `photo_scout_geometry_proof.py`: isolated standard-library mathematical fixtures, not production code.
- `geometry-proof-results.json` and `geometry-proof-tests.txt`: actual research-environment results.
- `source-manifest.json`: source revisions and publisher weight metadata (no weights included).
- `project-checkpoint.json`: completed initial main-branch checkpoint.

Run the independent synthetic checks with:

```powershell
python photo_scout_geometry_proof.py --output geometry-proof-results.json
```

No photo inference, reconstruction accuracy benchmark, paid API call or hardware trial is represented by these tests. The product pipeline described in the prompt still requires implementation and its own acceptance tests. The older 12-photo-to-scene documents remain historical context; v2 supersedes their model and integration choices where stated.

Actual Windows execution also passed 24/24 synthetic tests. See `geometry-proof-results-windows.json`, `geometry-proof-tests-windows.txt` and `windows-execution.json`. The application full test suite was not run for this documentation-only task.
