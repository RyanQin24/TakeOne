"""Read glTF metadata and local dependencies without executing imported code.

This is an import boundary check, NOT the full Khronos glTF validator, a renderer,
or a physical dimension / clearance measurement.
"""
from pathlib import Path
import base64
import hashlib
import json
import re
import struct
from urllib.parse import unquote, urlsplit

from .storage import digest_file, inside

MAX_MODEL_BYTES = 128 * 1024 * 1024
MAX_DEPENDENCY_BYTES = 256 * 1024 * 1024


def gltf_document(path: Path) -> dict:
    if path.stat().st_size > MAX_MODEL_BYTES:
        raise ValueError("Model exceeds the 128 MiB import limit")
    payload = path.read_bytes()
    if path.suffix.lower() == ".gltf":
        document = json.loads(payload)
    elif path.suffix.lower() == ".glb":
        if len(payload) < 20:
            raise ValueError("Truncated GLB")
        magic, version, length = struct.unpack_from("<4sII", payload)
        if magic != b"glTF" or version != 2 or length != len(payload):
            raise ValueError("Invalid GLB header, version, or length")
        offset, chunks = 12, []
        while offset < len(payload):
            if offset + 8 > len(payload):
                raise ValueError("Truncated GLB chunk")
            size, kind = struct.unpack_from("<II", payload, offset)
            offset += 8
            if size % 4 or offset + size > len(payload):
                raise ValueError("Invalid GLB chunk size")
            chunks.append((kind, payload[offset:offset + size]))
            offset += size
        if not chunks or chunks[0][0] != 0x4E4F534A:
            raise ValueError("GLB must begin with its JSON chunk")
        if len(chunks) > 2 or (len(chunks) == 2 and chunks[1][0] != 0x004E4942):
            raise ValueError("This importer supports JSON plus one optional BIN chunk")
        document = json.loads(chunks[0][1])
        embedded = [item for item in document.get("buffers", []) if "uri" not in item]
        if len(embedded) > 1:
            raise ValueError("Multiple embedded buffers are invalid for this importer")
        if embedded:
            available = len(chunks[1][1]) if len(chunks) == 2 else 0
            if embedded[0]["byteLength"] > available:
                raise ValueError("Embedded GLB buffer is truncated")
    else:
        raise ValueError("Only .gltf and .glb are supported; export other formats first")
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError("Only glTF 2.0 is supported")
    return document


def inspect_model(path: Path, pack_root: Path) -> dict:
    document = gltf_document(path)
    pack_root = pack_root.resolve()
    files = {path.resolve()}
    records = list(document.get("buffers", [])) + list(document.get("images", []))
    for item in records:
        uri = item.get("uri")
        if uri is None:
            continue
        if uri.startswith("data:"):
            header, separator, encoded = uri.partition(",")
            if not separator or not header.endswith(";base64"):
                raise ValueError("Only base64 embedded data URIs are supported")
            content = base64.b64decode(encoded, validate=True)
            if len(content) > MAX_DEPENDENCY_BYTES:
                raise ValueError("Embedded dependency exceeds the size limit")
            if "byteLength" in item and len(content) < item["byteLength"]:
                raise ValueError("Embedded buffer is truncated")
            continue
        parsed = urlsplit(uri)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Models may reference only local pack files, not external URLs")
        # Resolve ../ texture references only within this immutable pack snapshot.
        decoded = unquote(parsed.path)
        if "\\" in decoded or ":" in decoded or "\x00" in decoded or decoded.startswith("/"):
            raise ValueError("Unsafe model dependency URI")
        relative = (path.parent / decoded).resolve()
        if not relative.is_relative_to(pack_root):
            raise ValueError("Model dependency escapes its asset pack")
        dependency = inside(pack_root, relative.relative_to(pack_root).as_posix())
        if not dependency.is_file():
            raise ValueError(f"Missing model dependency: {uri}")
        if dependency.stat().st_size > MAX_DEPENDENCY_BYTES:
            raise ValueError("Dependency exceeds the size limit")
        if "byteLength" in item and dependency.stat().st_size < item["byteLength"]:
            raise ValueError("Referenced buffer is truncated")
        files.add(dependency)
    dependencies, digest = [], hashlib.sha256()
    for file in sorted(files, key=lambda value: value.relative_to(pack_root).as_posix()):
        relative = file.relative_to(pack_root).as_posix()
        file_hash = digest_file(file)
        digest.update(relative.encode() + b"\0" + file_hash.encode() + b"\n")
        dependencies.append({"path": relative, "sha256": file_hash, "bytes": file.stat().st_size})
    animations = [{"index": i, "name": clip.get("name", f"clip-{i}")}
                  for i, clip in enumerate(document.get("animations", []))]
    triangles = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("mode", 4) != 4:
                continue
            index = primitive.get("indices", primitive.get("attributes", {}).get("POSITION"))
            if index is not None:
                triangles += document.get("accessors", [])[index]["count"] // 3
    return {
        "sha256": digest.hexdigest(), "model_sha256": digest_file(path),
        "dependency_bytes": sum(item["bytes"] for item in dependencies),
        "dependencies": dependencies, "animations": animations,
        "has_skin": bool(document.get("skins")), "triangles_nominal": triangles,
        "extensions_required": document.get("extensionsRequired", []),
        "dimensions_m": None, "dimensions_status": "not_measured",
        "source_coordinate_system": "glTF Y-up; nominal metres, not venue measurements",
        "collision_status": "not_qualified",
    }


def readable_name(stem: str) -> str:
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", stem).replace("_", " ").replace("-", " ")
