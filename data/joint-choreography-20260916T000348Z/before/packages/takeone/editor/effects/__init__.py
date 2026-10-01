"""Composable effect primitives and the higher-level looks built from them."""

from . import looks, primitives, transitions  # noqa: F401,E402
from .registry import EFFECTS, register  # noqa: F401

primitives.install(EFFECTS)
looks.install(EFFECTS)
transitions.install(EFFECTS)
