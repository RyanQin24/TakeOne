"""CLI: download, import, search, inspect, and verify local asset libraries."""
from pathlib import Path
import argparse
import json
import sys
from zipfile import BadZipFile

from .catalog import AssetCatalog
from .importer import import_zip
from .providers import download_pack
from .storage import digest_file, inside, library_path, require_project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Existing TAKE ONE checkout")
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Download only the selected configured free packs")
    selection = download.add_mutually_exclusive_group(required=True)
    selection.add_argument("--starter", action="store_true")
    selection.add_argument("--pack")
    importer = commands.add_parser("import-zip", help="Import a ZIP whose CC0 license you have checked")
    importer.add_argument("archive", type=Path)
    importer.add_argument("--pack", required=True, help="ID in configs/asset-library/packs.json")
    importer.add_argument("--confirm-license", action="store_true", required=True)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=12)
    search.add_argument("--kind", choices=["prop", "character", "environment"])
    get = commands.add_parser("get")
    get.add_argument("asset_id")
    get.add_argument("--sha256")
    commands.add_parser("verify", help="Re-hash each installed model and dependency")
    args = parser.parse_args()
    try:
        root = require_project(args.root)
        if args.command in ("download", "import-zip"):
            config = json.loads((root / "configs/asset-library/packs.json").read_text(encoding="utf-8"))
            packs = config["packs"]
            if args.command == "download" and args.starter:
                chosen = [pack for pack in packs if pack.get("starter")]
            else:
                chosen = [pack for pack in packs if pack["id"] == args.pack]
            if not chosen:
                raise ValueError("No matching pack. Add its reviewed source metadata to packs.json first.")
            results = []
            for pack in chosen:
                print(f"Importing {pack['id']}...", file=sys.stderr)
                result = download_pack(root, pack) if args.command == "download" else import_zip(root, args.archive, pack)
                results.append(result)
            result = results
        elif args.command == "verify":
            path = library_path(root)
            document = json.loads((path / "catalog.json").read_text(encoding="utf-8"))
            checked = set()
            for asset in document["assets"]:
                snapshot = path / "packs" / asset["pack_id"] / asset["archive_sha256"]
                for dependency in asset["dependencies"]:
                    file = inside(snapshot, dependency["path"])
                    if file not in checked:
                        if digest_file(file) != dependency["sha256"]:
                            raise ValueError(f"Asset integrity mismatch: {file}")
                        checked.add(file)
            result = {"verified_files": len(checked), "assets": len(document["assets"]),
                      "scope": "local byte integrity, not visual correctness or hardware clearance"}
        else:
            catalog = AssetCatalog.from_project(root)
            result = catalog.get(args.asset_id, args.sha256) if args.command == "get" else catalog.search(args.query, args.limit, args.kind)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, BadZipFile) as error:
        print(f"Asset library: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
