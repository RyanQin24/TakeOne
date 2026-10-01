"""Paths are independent of the caller's working directory."""

import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("TAKEONE_ROOT", Path(__file__).resolve().parents[2])).resolve()
APP = WORKSPACE / "apps/rehearsal"
MODELS = WORKSPACE / "assets/robots/takeone"
REFERENCE = WORKSPACE / "assets/robots/reference"
CONFIGS = WORKSPACE / "configs"
CALIBRATION = WORKSPACE / "calibration"
DATA = WORKSPACE / "data"
