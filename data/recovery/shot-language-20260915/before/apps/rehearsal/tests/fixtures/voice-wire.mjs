import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../../../../', import.meta.url));
const python = `${root}.venv/${process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'}`;
export const wire = JSON.parse(execFileSync(python, [`${root}tests/fixtures/voice_wire.py`], {encoding: 'utf8'}));
