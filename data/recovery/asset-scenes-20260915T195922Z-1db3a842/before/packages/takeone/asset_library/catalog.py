"""Search installed assets without adding each model to a Python enum."""
from pathlib import Path
import copy
import json
import re

from .storage import library_path


def terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class AssetCatalog:
    def __init__(self, document: dict):
        if document.get("schema_version") != 1:
            raise ValueError("Unsupported asset catalog version")
        self._assets = {}
        for asset in document.get("assets", []):
            asset_id = asset["asset_id"]
            if asset_id in self._assets:
                raise ValueError(f"Duplicate asset ID: {asset_id}")
            self._assets[asset_id] = copy.deepcopy(asset)

    @classmethod
    def from_project(cls, root: Path):
        path = library_path(root) / "catalog.json"
        document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "schema_version": 1, "assets": []
        }
        return cls(document)

    def get(self, asset_id: str, sha256: str | None = None) -> dict:
        try:
            asset = self._assets[asset_id]
        except KeyError as error:
            raise ValueError(f"Asset is not installed: {asset_id}. Search the catalog or import it first.") from error
        if sha256 is not None and asset["sha256"] != sha256:
            raise ValueError("The saved production references a different asset revision")
        return copy.deepcopy(asset)

    def search(self, query: str, limit: int = 12, kind: str | None = None) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("Search limit must be between 1 and 100")
        requested = terms(query)
        ranked = []
        for asset in self._assets.values():
            if kind is not None and asset["kind"] != kind:
                continue
            name_terms = terms(asset["name"])
            metadata_terms = terms(" ".join(asset["tags"]) + " " + asset["pack_id"])
            matched = requested & (name_terms | metadata_terms)
            if requested and not matched:
                continue
            score = 5 * len(requested & name_terms) + len(matched)
            ranked.append((-score, asset["asset_id"], asset))
        ranked.sort(key=lambda item: item[:2])
        return [copy.deepcopy(asset) for _, _, asset in ranked[:limit]]

    def __len__(self) -> int:
        return len(self._assets)
