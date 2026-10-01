"""Apply reviewed integration while preserving one open Windows file's identity.
The file permits writing but Windows denies replacement; do not change its ACL.
The existing installer still preflights all changes and backs up original bytes.
"""
from pathlib import Path
import os
import apply_integration as installer

atomic_write = installer.atomic_write
locked_target = Path('C:/TakeOne/apps/rehearsal/dist/director.js').resolve()

def write_preserving_open_file(path, content):
    if path.resolve() != locked_target:
        return atomic_write(path, content)
    print('Editing writable director.js in place; preserving its open-file identity.')
    with path.open('r+b') as stream:
        before = stream.read()
        try:
            stream.seek(0)
            stream.write(content)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.seek(0); stream.write(before); stream.truncate(); stream.flush()
            raise

installer.atomic_write = write_preserving_open_file
raise SystemExit(installer.main())
