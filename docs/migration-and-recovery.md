# Migration and recovery

The before-layout was `lerobot/` plus the nested `TakeOne-main/TakeOne-main/rehearsal-mvp/`, a neighboring evidence bundle and distribution archives. The after-layout is listed in the root README. `migration-manifest.json` records each actual move and its reason. The script records operations incrementally and refuses overwriting destinations; it is historical migration tooling, not a script to rerun on the completed layout.

Before any source move, the original 22 Python and 9 JavaScript tests passed. A full source snapshot captured **1,394 files / 363,138,470 bytes**, including the entire LeRobot `.git` directory, tracked modifications and untracked work. Every archived member was read back and SHA-256 checked. Snapshot: `archive/recovery/20260912T023620Z/`. Its `manifest.json` is the authoritative before-tree, sizes and hashes; `lerobot-status.txt`, `lerobot-head.txt` and `lerobot-diff.patch` aid review. The ZIP contains actual file bytes in addition to the patch.

Excluded from that snapshot: virtual environments, node_modules, Python/test/lint caches, the recovery directory itself and active simulator logs. Logs were moved after stopping the server. The original simulator dependency versions are captured in `requirements-simulation.lock.txt`; web versions remain in `apps/rehearsal/package-lock.json`. A fresh root environment replaces the relocated simulator environment. LeRobot's environment and repository remain in place and unchanged.

No unique source or calibration file was discarded. Original ZIP/TAR distributions were relocated to `archive/imports/`, not assumed to be redundant. `configs/reference/` and `calibration/evidence/` contain intentional imported copies with documented provenance; they do not replace or edit the originals in LeRobot. The reference model/asset bundle remains internally intact under `assets/robots/reference/`.

## Restore without overwriting today's work

Run the following from the workspace root. It restores only into a new, non-existing directory inside `C:\TakeOne`, validates ZIP paths and compares every restored file with the manifest:

```powershell
.\scripts\Restore-Snapshot.ps1 -Destination 'C:\TakeOne\archive\restored-before-migration'
```

The result is an isolated copy of the old layout including nested Git history. Do not extract over the current workspace. Inspect it first. For full rollback, stop only the known TakeOne server, preserve any post-migration work in another snapshot, then deliberately replace the affected paths using the move manifest in reverse order or the isolated restored tree. Recreate the old simulator virtual environment at its restored path from the dependency lock; do not copy a virtual environment blindly. Use its preserved `Start-Rehearsal.ps1` after reinstalling dependencies. A root-relative recovery copy is not protection against losing the entire drive; take a separate offline copy before relying on it for hardware work.

For the current root repository layout, preserved LeRobot history and conditional preservation-audit checks, see [repository contents and cloning](repository-contents.md). The pre-migration snapshot remains historical recovery evidence.

## Completed verification and retained cleanup

The documented restore command was executed into `archive/restore-verification/`: all 1,394 restored files passed their SHA-256 checks. The default's complete 321-frame cart/joint arrays have maximum absolute change **0.0** after migration. The final software checks comprise 20 product-contract tests, 22 original simulation tests and 9 JavaScript tests, plus the preservation audit. Results are recorded in `data/verification/`.

With that verification complete and recorded, the September 2026 cleanup
removed the one-time restore copy (`archive/restore-verification/`), the
retired simulator environment, the retired import shims and the extracted
duplicate of `archive/imports/TakeOne-main.zip`. The authoritative recovery
material remains: the snapshot manifests and LFS workspace ZIPs under
`archive/recovery/`, the original distributions under `archive/imports/`, and
full Git history for everything deleted. The root `.venv` is the active
environment; no old runtime path is required by the active simulator.
