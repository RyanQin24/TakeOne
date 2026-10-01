# Automatic original-file saving over USB

TakeOne can copy a completed Blackmagic Camera recording directly from a trusted
iPhone to `data/phone-sync`. The connection is local USB; no cloud account is used.
Keep the iPhone connected and TakeOne running. Unlock the phone if iOS denies
file access. Blackmagic Camera remains the recording app.

## One-time Windows setup

Install Apple's **Apple Devices** app from the Microsoft Store, open it, connect
the iPhone with a USB data cable, and complete **Trust** on the computer and phone.
Then run `scripts/Setup-PhoneTransfer.ps1` from this checkout. It checks the
Blackmagic app's shared Media folder before enabling anything, and saves the
specific USB device identity in the local `configs/phone-transfer.json`.

The setup uses a separate `.runtime/phone-transfer` Python environment. The
checked-in lock installs pymobiledevice3 11.15.5 and its USB/AFC service imports
with `--no-deps`; firmware restore and developer-tool dependencies are deliberately
excluded. The simulator and robot environments do not import that package.

Start/restart TakeOne with its normal launcher. The server starts one background
USB worker and stops its child when it exits. A file lock prevents multiple app
instances from copying the same jobs simultaneously. No hardware connection is
opened during module import or test server construction.

## What happens after Stop

When USB saving is enabled, the recording adapter reads Blackmagic's clip list
before recording. After the phone confirms Stop, it identifies the single new
clip, records the actual filename/size/ID in the take evidence, and writes a
durable copy job. The phone can ignore the requested `clipName`; matching now uses
the filename the phone actually returned. An ambiguous or missing clip list
requires attention instead of silently selecting another recording.

The worker reads only Blackmagic's shared `/Documents/Media` originals. It writes
a temporary local file, checks byte count and unchanged phone size/mtime, and
verifies a full SHA-256 readback before atomically publishing the original name.
It never deletes phone footage, transcodes, or replaces a different local file.
Disconnects leave jobs queued for retry. Incomplete `.partial` files are not clips.

The Edit page refreshes every five seconds and shows USB connection/copy status.
File presence remains separate from visual review. `media_verified` is not changed
into a claim that a person or model has judged the picture.

## Existing recordings and recovery

Old takes predate the clip-ID readback and cannot be safely matched by their
requested names. To copy existing TakeOne originals without guessing their take
identities, explicitly run:

```powershell
.\.runtime\phone-transfer\Scripts\python.exe .\scripts\phone_transfer.py --import-existing
```

The running worker drains these jobs. Imported files whose take identity is
unknown appear as unmatched footage in Edit. Queue and verified receipts are in
`data/phone-transfer/jobs`; current connection/progress is in `status.json` and
worker diagnostics are in `worker.log`. Run the worker without `--watch` for one
retry pass. Set `enabled` to `false` in the local transfer configuration to disable
automatic copies.

Validated on the connected iPhone 17 Pro Max with Blackmagic Camera 3.5: trusted
USB access to `com.blackmagic-design.DaVinciCamera`, reading `/Documents/Media`, and
a real original MOV transfer. No robot movement is required to verify this feature.
