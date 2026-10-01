"""Read-only preservation audit, including exact documented source changes and recovery."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "archive/recovery/20260912T023620Z"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="write the preservation report outside the default repository evidence directory",
    )
    return parser.parse_args()


def matches_snapshot(path, entry):
    """Accept original bytes or the verified payload of an original LFS pointer."""
    if not path.is_file():
        return False
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual == entry["sha256"]:
        return True
    if entry["bytes"] > 1024:
        return False
    # A source clone may materialize an upstream LFS pointer. Authenticate the
    # pointer against the historical manifest before checking its payload.
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"HEAD:{entry['path']}"],
        capture_output=True,
    )
    if result.returncode or hashlib.sha256(result.stdout).hexdigest() != entry["sha256"]:
        return False
    pointer = re.fullmatch(
        rb"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n",
        result.stdout,
    )
    return bool(pointer and actual == pointer[1].decode("ascii") and path.stat().st_size == int(pointer[2]))


def matches_recorded_change(path, entry, change):
    """A documented source edit must retain the authenticated original bytes."""
    if not change or not path.is_file():
        return False
    recovery = (ROOT / change["recovery"]).resolve()
    return (
        recovery.is_relative_to(ROOT / "data/recovery")
        and recovery.is_file()
        and change["before_sha256"] == entry["sha256"]
        and hashlib.sha256(recovery.read_bytes()).hexdigest() == entry["sha256"]
        and hashlib.sha256(path.read_bytes()).hexdigest() == change["after_sha256"]
    )


def main():
    args = parse_args()
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
    change_path = ROOT / "docs/robot-studio-feature-02-changes.json"
    changes = json.loads(change_path.read_text(encoding="utf-8")) if change_path.is_file() else {}
    recorded_changes = []
    failures = []
    count = 0
    generated_metadata_skipped = 0
    for entry in manifest["files"]:
        name = entry["path"]
        # Git's index/stat cache can change during read-only status commands.
        if not name.startswith("lerobot/") or name.startswith("lerobot/.git/"):
            continue
        if any(part.endswith(".egg-info") for part in Path(name).parts):
            generated_metadata_skipped += 1
            continue
        path = ROOT / name
        if not matches_snapshot(path, entry):
            if matches_recorded_change(path, entry, changes.get(name)):
                recorded_changes.append(name)
            else:
                failures.append(name)
        count += 1
    nested_git_present = (ROOT / "lerobot/.git").exists()
    if nested_git_present:
        for filename, git_args in [
            ("lerobot-head.txt", ["rev-parse", "HEAD"]),
            ("lerobot-status.txt", ["status", "--porcelain=v1", "-uall"]),
        ]:
            current = subprocess.check_output(["git", "-C", str(ROOT / "lerobot"), *git_args])
            if current != (SNAPSHOT / filename).read_bytes():
                failures.append(filename)
    original = ROOT / "lerobot/configs/cinebot/calibration_audit.json"
    if original.read_bytes() != (ROOT / "calibration/evidence/calibration_audit.json").read_bytes():
        failures.append("imported calibration audit")
    for entry in manifest["files"]:
        prefix = "TakeOne-main/TakeOne-main/TAKE-ONE-Simulation-Evidence/takeone_validation/"
        if not entry["path"].startswith(prefix):
            continue
        current = ROOT / "assets/robots/reference" / entry["path"][len(prefix) :]
        if not current.exists() or hashlib.sha256(current.read_bytes()).hexdigest() != entry["sha256"]:
            failures.append(entry["path"])
    report = dict(
        lerobot_files_checked=count,
        generated_metadata_skipped=generated_metadata_skipped,
        nested_git_history_checked=nested_git_present,
        recorded_source_changes=recorded_changes,
        failures=failures,
        passed=not failures,
    )
    target = args.output_dir.resolve() if args.output_dir is not None else ROOT / "data/verification"
    target.mkdir(parents=True, exist_ok=True)
    (target / "preservation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
