"""Local, retryable copies of stopped Blackmagic clips. No camera commands."""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

from takeone.paths import CONFIGS, DATA, WORKSPACE

BUNDLE_ID = "com.blackmagic-design.DaVinciCamera"
REMOTE_MEDIA = "/Documents/Media"
CHUNK_BYTES = 1024 * 1024


def read_config(path=None):
    path = Path(path) if path else CONFIGS / "phone-transfer.json"
    if not path.exists():
        return {"enabled": False}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def valid_clip(clip):
    if not isinstance(clip, dict):
        raise ValueError("The phone did not provide a clip record.")
    name = clip.get("filePath")
    if (
        not isinstance(name, str)
        or not name
        or any(c in name for c in '/\\:<>"|?*')
        or any(ord(c) < 32 for c in name)
        or name.endswith((" ", "."))
        or Path(name).suffix.lower() not in (".mov", ".mp4", ".m4v")
        or name.split(".")[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    ):
        raise ValueError("The phone clip must have a safe, original video filename.")
    if type(clip.get("fileSize")) is not int or clip["fileSize"] <= 0:
        raise ValueError("The phone has not finalized the clip size.")
    return name


def enqueue(clip, capture_folder=None, *, root=None):
    """Persist a job only after a confirmed stop and unambiguous clip readback."""
    valid_clip(clip)
    root = Path(root) if root else DATA / "phone-transfer"
    key = hashlib.sha256(json.dumps(clip, sort_keys=True).encode()).hexdigest()
    path = root / "jobs" / (key + ".json")
    if not path.exists():
        write_json(
            path,
            {
                "schema_version": 1,
                "clip": clip,
                "state": "queued",
                "capture_folder": str(capture_folder) if capture_folder else None,
                "queued_at": time.time(),
            },
        )
    return str(path)


async def copy_original(fs, clip, inbox, *, progress=None):
    """Stream a complete original to a temporary file, then publish atomically.

    No remote write or delete operations. Byte count, remote size/mtime stability,
    and a full SHA-256 readback of the local file are required before publication.
    Existing originals are compared by digest and are never overwritten.
    """
    name = valid_clip(clip)
    inbox = Path(inbox)
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / name
    source = REMOTE_MEDIA + "/" + name
    before = await asyncio.wait_for(fs.stat(source), 15)
    if before.get("st_ifmt") != "S_IFREG" or before["st_size"] != clip["fileSize"]:
        raise ValueError("The phone file is not a finalized original of the expected size.")
    temporary = inbox / (".takeone-usb-" + uuid.uuid4().hex + ".partial")
    digest, count = hashlib.sha256(), 0
    handle = await asyncio.wait_for(fs.fopen(source, "r"), 15)
    try:
        with temporary.open("xb") as output:
            while count < clip["fileSize"]:
                chunk = await asyncio.wait_for(
                    fs.fread(handle, min(CHUNK_BYTES, clip["fileSize"] - count)),
                    15,
                )
                if not chunk:
                    raise OSError("USB transfer ended before the complete file arrived.")
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
                if progress:
                    progress(count, clip["fileSize"])
            output.flush()
            os.fsync(output.fileno())
        after = await asyncio.wait_for(fs.stat(source), 15)
        if count != clip["fileSize"] or any(before[k] != after[k] for k in ("st_size", "st_mtime")):
            raise OSError("The phone file changed during transfer; it will be retried.")
        with temporary.open("rb") as local:
            if hashlib.file_digest(local, "sha256").hexdigest() != digest.hexdigest():
                raise OSError("The local file failed checksum verification.")
        if target.exists():
            with target.open("rb") as existing:
                existing_digest = hashlib.file_digest(existing, "sha256").hexdigest()
            if existing_digest != digest.hexdigest():
                raise FileExistsError(
                    "A different local video already uses this filename; nothing was replaced."
                )
        else:
            # Hard-link creation is atomic and fails if another writer won the name.
            os.link(temporary, target)
        return {
            "name": name,
            "size_bytes": count,
            "sha256": digest.hexdigest(),
            "path": str(target.resolve()),
            "source": "iphone_usb_original",
            "copied_at": time.time(),
        }
    finally:
        try:
            await asyncio.wait_for(fs.fclose(handle), 5)
        finally:
            temporary.unlink(missing_ok=True)


def clean_interrupted_copies(inbox):
    """Only the worker holding the exclusive lock may discard its orphan staging files."""
    inbox = Path(inbox)
    if not inbox.is_dir():
        return
    for path in inbox.iterdir():
        if (
            re.fullmatch(r"\.takeone-usb-[0-9a-f]{32}\.partial", path.name)
            and not path.is_symlink()
            and path.is_file()
        ):
            path.unlink()


def status(*, root=None):
    root = Path(root) if root else DATA / "phone-transfer"
    config = read_config()
    try:
        result = json.loads((root / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = {"state": "starting" if config.get("enabled") else "disabled"}
    if config.get("enabled") and time.time() - result.get("updated_at", 0) > 30:
        result = {
            **result,
            "state": "offline",
            "message": "USB transfer service is not running. Start TakeOne.",
        }
    return {**result, "enabled": bool(config.get("enabled"))}


def start_worker():
    """Called by the running app, never by import or test server construction."""
    config = read_config()
    if not config.get("enabled"):
        return None
    python = WORKSPACE / config["python"]
    log = DATA / "phone-transfer" / "worker.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        try:
            return subprocess.Popen(
                [str(python), str(WORKSPACE / "scripts/phone_transfer.py"), "--watch"],
                cwd=WORKSPACE,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as error:
            write_json(
                DATA / "phone-transfer/status.json",
                {
                    "state": "needs_setup",
                    "updated_at": time.time(),
                    "message": "USB transfer helper could not start. Run Setup-PhoneTransfer.ps1.",
                    "detail": str(error),
                },
            )
            return None
