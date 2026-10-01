"""Content addressing. An identifier is derived from meaning, never assigned by a counter."""

import hashlib

from .contracts import encode

NODE_ID_LENGTH = 16


def digest(value):
    """SHA-256 of the canonical JSON encoding of `value`."""
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def content_id(kind, payload, length=NODE_ID_LENGTH):
    """A short stable identifier for a kind of thing with a canonical payload."""
    if not isinstance(kind, str) or not kind:
        raise ValueError("Content identifiers need a kind")
    if not 8 <= length <= 64:
        raise ValueError("Content identifier length must be 8-64 characters")
    return digest({"kind": kind, "payload": payload})[:length]


def file_digest(path, chunk=1 << 20):
    """SHA-256 of a file's bytes. Media identity never depends on a filename."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            hasher.update(block)
    return hasher.hexdigest()
