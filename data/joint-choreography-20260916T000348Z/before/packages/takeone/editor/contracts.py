"""Explicit validators. Same idiom as the Director contracts: fail closed, name the field.

Units are in the field name. `_s` is seconds, `_ms` is milliseconds, `_deg` is degrees,
`_k` is kelvin, `_stops` is photographic stops. Unitless ratios are named `_ratio` or
constrained to 0..1 by `unit`.
"""

import json
import math
import re
from uuid import UUID

from .errors import ValidationError

SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
MAX_SECONDS = 36000.0


def integer(value, name, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def number(value, name, minimum=-1e12, maximum=1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{name} must be finite")
    if not minimum <= result <= maximum:
        raise ValidationError(f"{name} must be from {minimum} to {maximum}")
    return result


def seconds(value, name, minimum=0.0, maximum=MAX_SECONDS):
    return number(value, name, minimum, maximum)


def unit(value, name):
    return number(value, name, 0.0, 1.0)


def text(value, name, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValidationError(f"{name} must contain 1-{maximum} characters")
    return value


def slug(value, name):
    if not isinstance(value, str) or not SLUG.match(value):
        raise ValidationError(f"{name} must be 1-64 characters of letters, digits, '_', '.' or '-'")
    return value


def identity(value, name="ID"):
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a UUID")
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ValidationError(f"{name} must be a canonical UUID") from None
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise ValidationError(f"{name} must be true or false")
    return value


def choice(value, name, choices):
    if value not in choices:
        raise ValidationError(f"{name} must be one of {sorted(choices)}")
    return value


def enum_value(cls, value, name):
    try:
        return cls(value)
    except ValueError:
        raise ValidationError(f"{name} must be one of {sorted(item.value for item in cls)}") from None


def fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValidationError("Expected a JSON object")
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing or extra:
        raise ValidationError(f"Invalid fields; missing: {sorted(missing)}, unknown: {sorted(extra)}")
    return value


def mapping(value, name, maximum=64):
    if not isinstance(value, dict) or len(value) > maximum:
        raise ValidationError(f"{name} must be an object with at most {maximum} keys")
    for key in value:
        if not isinstance(key, str) or not key or len(key) > 64:
            raise ValidationError(f"{name} keys must be 1-64 character strings")
    return dict(value)


def sequence(value, name, maximum=1024):
    if not isinstance(value, (list, tuple)) or len(value) > maximum:
        raise ValidationError(f"{name} must be a list of at most {maximum} items")
    return tuple(value)


def digest_hex(value, name, length=64):
    if not isinstance(value, str) or len(value) != length or any(c not in "0123456789abcdef" for c in value):
        raise ValidationError(f"{name} must be a {length}-character lowercase hexadecimal digest")
    return value


def ordered(start, end, name, minimum_span=0.0):
    if end - start < minimum_span:
        raise ValidationError(f"{name} must span at least {minimum_span} seconds")
    return start, end


def encode(value):
    """Canonical JSON. Sorted keys, no NaN, no incidental whitespace."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
