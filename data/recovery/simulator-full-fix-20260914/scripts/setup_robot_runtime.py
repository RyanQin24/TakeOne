"""Install the isolated studio motor runtime. Opens no devices."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Install uv before setting up the robot runtime")
    environment = ROOT / ".runtime/robot/.venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
    subprocess.run(
        [uv, "pip", "sync", "--python", str(python), str(ROOT / "requirements-robot.lock.txt")], check=True
    )
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "packages"), str(ROOT / "lerobot/src")]))
    subprocess.run(
        [
            str(python),
            "-c",
            "from lerobot.motors.feetech import FeetechMotorsBus; "
            "from takeone.motion.studio_worker import BrowserControl; "
            "print('Robot runtime imports passed. No ports opened.')",
        ],
        env=env,
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
