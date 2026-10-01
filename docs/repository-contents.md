# Repository contents and cloning

The September 12, 2026 publication includes the complete project working files in `Zwc-11/TakeOne` on `main`: the app, TakeOne package, modified LeRobot source, tests, documentation, models, configuration, available calibration evidence, saved runs and historical project archives. `lerobot/` is ordinary versioned source, not a Git submodule or a link to an unavailable private repository.

The original local LeRobot repository is preserved at `lerobot/.git`, including its upstream remote, commit history and uncommitted changes. Publishing the working files does not commit or push anything to Hugging Face's repository. Its recorded upstream base is `2774d9bddcbbda50e697e162e89e7eaada8d7105`. Historical snapshots retain the original recovery evidence; they are not the active implementation.

## Clone on another computer

Git LFS is needed for the three large recovery ZIPs and LeRobot's upstream test artifacts. Use a new destination when preserving a robot computer's existing local work. These commands do not initialize hardware:

```powershell
git lfs install
git clone --config core.autocrlf=false https://github.com/Zwc-11/TakeOne.git TakeOne-complete
Set-Location TakeOne-complete
git lfs pull
```

Keeping `core.autocrlf=false` preserves source and evidence bytes across operating systems, including imported LeRobot attributes that explicitly leave JSON line endings unspecified. Follow the root setup instructions to recreate the lightweight simulator environment. The separate LeRobot hardware environment still needs its own dependencies and TakeOne installed into it; copying a Windows virtual environment is not a portable installation.

For an existing checkout without conflicting local work, fetch and pull `main` normally, then run `git lfs pull`. Git will refuse to overwrite conflicting untracked LeRobot files; preserve and reconcile those files rather than using a forced reset or deleting the directory.

## Included and excluded files

Included: active source, LeRobot's tracked and project-specific untracked source, available model files, calibration audit and mapping templates, dependency lock files, saved Director data, run reports, verification evidence, the original import distributions (`archive/imports/*.zip`, `*.tar.gz`) and the pre-migration recovery snapshots (`archive/recovery/`). Existing calibration files are preserved byte-for-byte. Missing physical calibration originals cannot be manufactured or recovered by Git; the current registry continues to report those blockers.

The September 2026 cleanup removed superseded working copies that duplicated
those retained originals: the extracted `TakeOne-main/` prototype trees, the
one-time `archive/restore-verification/` copy (its successful verification is
recorded in [migration and recovery](migration-and-recovery.md)) and the
retired compatibility shims. Git history retains all of them.

Excluded: active `.git` databases, installed `.venv`/`venv`/`env` directories, `node_modules`, Python/tool caches, generated Python package metadata, the retired simulator environment, local credential files and transient SQLite journal files. Nothing in those categories was deleted from the local workspace. A SQLite file in Git is a saved state, not a mechanism for synchronizing simultaneous app sessions between computers.

The publication inventory records every included file's original SHA-256 and distinguishes original Git LFS pointers from actual file content. LeRobot LFS objects are copied to TakeOne's LFS storage so the published repository does not depend on missing local objects.

## Verification

Run `scripts/TakeOne.ps1 -Command test` after setup. The preservation audit checks LeRobot source bytes against the historical manifest. It checks the independent LeRobot Git history only when that nested repository exists; a normal source clone has no nested repository. Materialized LFS artifacts are checked against their original pointer's object ID and length.

Publishing these files does not change device profiles, calibration, motor torque, firmware, joint mappings or physical qualification. Simulated run reports remain simulated evidence.
