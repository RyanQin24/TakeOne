"""Small filesystem primitives shared by the importer and catalog."""

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".asset-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_relative(value: str) -> Path:
    """Accept only portable, non-traversing relative paths, including on Windows."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe relative path: {value!r}")
    pieces = value.split("/")
    windows_names = {"CON", "PRN", "AUX", "NUL"}
    windows_names.update(f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10))
    for part in pieces:
        if (
            part in ("", ".", "..")
            or re.search(r'[<>:"|?*\x00-\x1f]', part)
            or part.endswith((".", " "))
            or part.split(".")[0].upper() in windows_names
        ):
            raise ValueError(f"Unsafe relative path: {value!r}")
    parsed = PurePosixPath(value)
    if parsed.is_absolute():
        raise ValueError(f"Absolute path forbidden: {value}")
    return Path(*parsed.parts)


def inside(root: Path, relative: str) -> Path:
    root = root.resolve()
    result = (root / safe_relative(relative)).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Path escapes its asset directory")
    return result


def require_project(root: Path) -> Path:
    root = root.expanduser().resolve()
    for relative in ("packages/takeone", "apps/rehearsal/dist"):
        path = root / relative
        if not path.is_dir() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Not a TAKE ONE checkout, or linked outside root: {path}")
    return root


def library_path(root: Path) -> Path:
    root = require_project(root)
    path = root / "apps/rehearsal/dist/asset-library"
    if not path.resolve().is_relative_to(root):
        raise ValueError("Asset library directory resolves outside the project")
    return path


@contextmanager
def library_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".import.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise RuntimeError(
            f"Another import may be running. Inspect {lock}; do not remove a live lock."
        ) from error
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)
