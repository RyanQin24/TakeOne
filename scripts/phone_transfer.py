"""USB original-file worker, run in the isolated phone-transfer environment."""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from takeone.paths import DATA  # noqa: E402
from takeone.phone.transfer import (  # noqa: E402
    BUNDLE_ID,
    clean_interrupted_copies,
    copy_original,
    enqueue,
    read_config,
    write_json,
)


async def configure():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.house_arrest import HouseArrestService
    from pymobiledevice3.usbmux import list_devices
    from takeone.paths import CONFIGS

    devices = [device for device in await list_devices() if device.connection_type == "USB"]
    if len(devices) != 1:
        raise RuntimeError("Connect exactly one unlocked, trusted iPhone by USB.")
    async with await create_using_usbmux(serial=devices[0].serial, autopair=False) as phone:
        if not phone.paired:
            raise RuntimeError("Complete Trust in Apple Devices and on the iPhone first.")
        async with await HouseArrestService.create(phone, BUNDLE_ID, documents_only=True) as fs:
            await fs.listdir("/Documents/Media")
        write_json(
            CONFIGS / "phone-transfer.json",
            {
                "schema_version": 1,
                "enabled": True,
                "udid": phone.udid,
                "python": ".runtime/phone-transfer/Scripts/python.exe",
            },
        )
        print("Automatic USB saving configured for", phone.display_name, flush=True)


async def import_existing(config):
    """Explicit backfill of TakeOne originals; no guess about old take identities."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.house_arrest import HouseArrestService

    async with await create_using_usbmux(serial=config["udid"], autopair=False) as phone:
        async with await HouseArrestService.create(phone, BUNDLE_ID, documents_only=True) as fs:
            count = 0
            for name in await fs.listdir("/Documents/Media"):
                if not name.startswith("TakeOne-") or Path(name).suffix.lower() not in (".mov", ".mp4"):
                    continue
                info = await fs.stat("/Documents/Media/" + name)
                if info.get("st_ifmt") == "S_IFREG" and info["st_size"] > 0:
                    enqueue({"filePath": name, "fileSize": info["st_size"]})
                    count += 1
            print("Queued", count, "existing TakeOne originals.", flush=True)


async def run_once(config, root):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.house_arrest import HouseArrestService

    def report(state, **detail):
        write_json(root / "status.json", {"state": state, "updated_at": time.time(), **detail})

    jobs = []
    for path in sorted((root / "jobs").glob("*.json")):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["state"] != "saved":
            jobs.append((path, job))
    report("connecting", pending=len(jobs))
    try:
        async with await asyncio.wait_for(
            create_using_usbmux(
                serial=config["udid"],
                connection_type="USB",
                autopair=False,
            ),
            10,
        ) as phone:
            if not phone.paired:
                raise RuntimeError("Unlock the iPhone and trust this computer in Apple Devices.")
            async with await asyncio.wait_for(
                HouseArrestService.create(
                    phone,
                    BUNDLE_ID,
                    documents_only=True,
                ),
                10,
            ) as fs:
                for path, job in jobs:
                    last_update = 0.0

                    def progress(done, total):
                        nonlocal last_update
                        if time.monotonic() - last_update >= 1:
                            report(
                                "copying",
                                name=job["clip"]["filePath"],
                                copied_bytes=done,
                                total_bytes=total,
                                pending=len(jobs),
                            )
                            last_update = time.monotonic()

                    try:
                        receipt = await asyncio.wait_for(
                            copy_original(
                                fs,
                                job["clip"],
                                DATA / "phone-sync",
                                progress=progress,
                            ),
                            3600,
                        )
                        job.update(state="saved", receipt=receipt, error=None)
                    except Exception as error:
                        job.update(state="retrying", error=str(error) or type(error).__name__)
                    write_json(path, job)
                pending = [job for _, job in jobs if job["state"] != "saved"]
                if pending:
                    report("retrying", pending=len(pending), message=pending[0]["error"])
                else:
                    report("ready", pending=0, message="USB connected. Completed takes save automatically.")
    except Exception as error:
        report(
            "disconnected",
            pending=len(jobs),
            message="Connect and unlock the trusted iPhone to save queued originals.",
            detail=str(error) or type(error).__name__,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--import-existing", action="store_true")
    args = parser.parse_args()
    if args.configure:
        asyncio.run(asyncio.wait_for(configure(), 30))
        return
    if args.import_existing:
        asyncio.run(asyncio.wait_for(import_existing(read_config()), 60))
        return
    root = DATA / "phone-transfer"
    root.mkdir(parents=True, exist_ok=True)
    # A second app instance cannot start a second writer for the same inbox.
    with (root / "worker.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return
        clean_interrupted_copies(DATA / "phone-sync")
        while True:
            config = read_config()
            if not config.get("enabled"):
                return
            asyncio.run(run_once(config, root))
            if not args.watch:
                return
            time.sleep(3)


if __name__ == "__main__":
    main()
