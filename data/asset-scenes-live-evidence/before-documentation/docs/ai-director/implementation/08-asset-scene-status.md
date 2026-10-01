# Asset-scene integration status — 2026-09-15

The engineering prompt was saved first in 08-asset-scene-engineering-prompt.md.
The inspected starting checkout was clean at 3e336e55bc623a38247e3ceffd0d5576e5e48824.

## Current Windows project
The existing Director, simulator, saved productions and calibration were NOT changed.
Terminal execution was blocked, including the normal full verification command.
A later code-write request was also blocked before integration activation.
Two incomplete additive files were preserved, not left on the application import path:
- data/recovery/asset-scene-20260915/incomplete-asset-library/__init__.py
- data/recovery/asset-scene-20260915/incomplete-asset-library/storage.py

## Prepared implementation
The TakeOne-Scene-Integration package contains the catalog/importer, generic loader,
Z-up dimension fitting, visible load errors, generation-only scene-dressing skill,
surgical application patches, a separate authored example builder and guarded installer.
It checks all affected anchors before writing and preserves recoverable originals.

Isolated checks passed: 57 Python tests and 17 JavaScript tests.
Those counts are not the complete Windows project verification or a WebGL test.
No third-party model download, paid Director generation or hardware trial was run.
The package must still be applied and tested on this machine before it is called live.
