"""Import a licensed local ZIP into an immutable, same-origin asset directory."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile

from .inspect import inspect_model, readable_name
from .storage import digest_file, inside, library_lock, library_path, safe_relative, write_json

ALLOWED_EXTENSIONS = {".glb", ".gltf", ".bin", ".png", ".jpg", ".jpeg", ".webp", ".ktx2", ".txt", ".md"}
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 20000


def extract_pack(archive: Path, target: Path) -> None:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("ZIP exceeds 512 MiB")
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > MAX_MEMBERS or sum(item.file_size for item in members) > MAX_UNPACKED_BYTES:
            raise ValueError("ZIP exceeds the expanded size or file-count limit")
        seen, selected = set(), []
        for item in members:
            path = safe_relative(item.filename.rstrip("/"))
            key = path.as_posix().casefold()
            if key in seen:
                raise ValueError("ZIP contains duplicate or Windows-case-colliding paths")
            seen.add(key)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("ZIP symlinks are not allowed")
            if item.flag_bits & 1:
                raise ValueError("Encrypted ZIPs are not supported")
            if item.file_size > 256 * 1024 * 1024:
                raise ValueError("ZIP member exceeds 256 MiB")
            if item.is_dir():
                continue
            if path.suffix.lower() in ALLOWED_EXTENSIONS or path.name.lower().startswith(("license", "copying")):
                selected.append((item, path))
        # Everything was checked before creating any file. The target is private staging.
        for item, relative in selected:
            destination = inside(target, relative.as_posix())
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(item) as source, destination.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def import_zip(root: Path, archive: Path, pack: dict, origin: dict | None = None) -> dict:
    pack_id = pack["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,59}", pack_id):
        raise ValueError("Pack ID must be 2-60 lower-case letters, numbers, or hyphens")
    if pack.get("license") != "CC0-1.0":
        raise ValueError("This initial importer accepts only explicitly documented CC0 packs")
    source_url = pack.get("page_url", "")
    if urlsplit(source_url).scheme != "https" or not urlsplit(source_url).hostname:
        raise ValueError("A public HTTPS source/license-evidence page is required")
    archive = archive.expanduser().resolve()
    archive_hash = digest_file(archive)
    library = library_path(root)
    with library_lock(library):
        packs = library / "packs"
        packs.mkdir(exist_ok=True)
        relative_snapshot = f"packs/{pack_id}/{archive_hash}"
        destination = inside(library, relative_snapshot)
        with tempfile.TemporaryDirectory(prefix=".asset-import-", dir=library) as temporary:
            staging = Path(temporary) / "pack"
            staging.mkdir()
            extract_pack(archive, staging)
            models = sorted(path for path in staging.rglob("*") if path.suffix.lower() in (".glb", ".gltf"))
            if not models:
                raise ValueError("No glTF/GLB models found. Export the source models from Blender to glTF first.")
            assets = []
            for model in models:
                relative = model.relative_to(staging).as_posix()
                metadata = inspect_model(model, staging)
                path_hash = hashlib.sha256(relative.encode()).hexdigest()[:10]
                slug = re.sub("[^a-z0-9]+", "-", model.stem.lower()).strip("-")[:48] or "model"
                asset_id = f"lib:{pack_id}:{slug}-{path_hash}:{metadata['sha256'][:16]}"
                name = readable_name(model.stem)
                assets.append({
                    "asset_id": asset_id, "name": name, "pack_id": pack_id,
                    "kind": pack.get("kind", "prop"), "tags": pack.get("tags", []),
                    "uri": "/asset-library/" + quote(relative_snapshot + "/" + relative, safe="/"),
                    "license": "CC0-1.0", "author": pack.get("author", "Unspecified"),
                    "source_url": source_url, "archive_sha256": archive_hash,
                    "provenance": "Imported visualization asset; not a measured physical object",
                    **metadata,
                })
            provenance = {
                "pack": pack, "origin": origin or {"method": "local_zip", "license_evidence": "user_asserted"},
                "archive_sha256": archive_hash,
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "hash_evidence": "Hashes computed on imported bytes; not an upstream signature",
                "renderable_file_count": len(assets),
            }
            # Internal metadata uses a dedicated filename; a pack cannot supply it.
            write_json(staging / "TAKEONE-PROVENANCE.json", provenance)
            catalog_path = library / "catalog.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8")) if catalog_path.exists() else {
                "schema_version": 1, "assets": []
            }
            by_id = {asset["asset_id"]: asset for asset in catalog["assets"]}
            for asset in assets:
                if asset["asset_id"] in by_id and by_id[asset["asset_id"]]["sha256"] != asset["sha256"]:
                    raise ValueError("Conflicting asset identity")
                by_id[asset["asset_id"]] = asset
            if destination.exists():
                # Re-import is idempotent, but corruption is never silently accepted.
                for asset in assets:
                    for dependency in asset["dependencies"]:
                        existing = inside(destination, dependency["path"])
                        if not existing.is_file() or digest_file(existing) != dependency["sha256"]:
                            raise ValueError("Installed snapshot has changed; restore it before re-importing")
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                staging.replace(destination)
            catalog["assets"] = sorted(by_id.values(), key=lambda asset: asset["asset_id"])
            write_json(catalog_path, catalog)
            return {"pack_id": pack_id, "imported_renderable_files": len(assets),
                    "total_catalog_entries": len(catalog["assets"]), "catalog": str(catalog_path)}
