"""Add this kit to an existing TAKE ONE checkout without replacing existing code."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys


def install(source: Path, destination: Path) -> int:
    source, destination = source.resolve(), destination.expanduser().resolve()
    for sentinel in ("packages/takeone", "apps/rehearsal/dist"):
        path = destination / sentinel
        if not path.is_dir() or not path.resolve().is_relative_to(destination):
            raise ValueError(f"Not a TAKE ONE checkout, or linked outside root: {path}")
    manifest = sorted(path for path in source.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    if not manifest:
        raise ValueError("Kit payload is empty")
    planned = []
    for file in manifest:
        target = destination / file.relative_to(source)
        if not target.resolve().is_relative_to(destination):
            raise ValueError(f"Target escapes the checkout: {target}")
        if target.exists():
            if not target.is_file() or file.read_bytes() != target.read_bytes():
                raise FileExistsError(f"Refusing to replace existing content: {target}")
        else:
            planned.append((file, target))
    # Complete conflict preflight before any writes. Roll back only files we created.
    created = []
    try:
        for file, target in planned:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                created.append(target)
                with file.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output)
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return len(created)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--download-starter", action="store_true",
                        help="After additive install, download the four configured free CC0 packs")
    args = parser.parse_args()
    kit = Path(__file__).resolve().parent
    try:
        root = args.root.expanduser().resolve()
        added = install(kit / "payload", root)
        print(f"Added {added} new files. Existing application files were not replaced.")
        print("Director/Shot Studio integration is NOT automatically enabled. Read docs/ai-director/implementation/08-asset-library-integration.md.")
        if args.download_starter:
            candidates = (root / ".venv/Scripts/python.exe", root / ".venv/bin/python")
            interpreter = next((path for path in candidates if path.is_file()), None)
            if interpreter is None:
                raise ValueError("The project's .venv interpreter is missing. Run the existing TAKE ONE setup, then use the asset-library CLI.")
            return subprocess.call([str(interpreter), "-m", "takeone.asset_library", "--root", str(root), "download", "--starter"], cwd=root)
        return 0
    except (OSError, ValueError) as error:
        print(f"Install stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
