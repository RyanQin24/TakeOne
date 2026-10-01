"""The single effect registry instance."""

from .spec import EffectRegistry

EFFECTS = EffectRegistry()


def register(spec):
    return EFFECTS.register(spec)
