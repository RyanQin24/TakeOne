"""Importing a file: identity, probe, proxy, thumbnail — then one IMPORT_MEDIA operation.

Media identity is the SHA-256 of the bytes, never the filename. Two copies of the same
take are the same media; a re-export of it is not.
"""

import uuid
from pathlib import Path

from .errors import ValidationError
from .ids import file_digest
from .operations import EditOperation, OperationType, Target


def resolve_inside(path, roots):
    """Refuse any media path that escapes the project's declared roots (path traversal)."""
    candidate = Path(path).resolve()
    for root in roots:
        base = Path(root).resolve()
        if candidate == base or candidate.is_relative_to(base):
            return candidate
    raise ValidationError(f"Media path is outside the project's media roots: {candidate}")


def media_id_for(digest, existing=()):
    base = f"m-{digest[:10]}"
    if base not in existing:
        return base
    raise ValidationError(f"Media '{base}' is already imported")


def import_operation(
    path, roots, probe_fn, proxy_manager=None, existing=(), name=None, source_space="rec709", explanation=""
):
    resolved = resolve_inside(path, roots)
    digest = file_digest(resolved)
    media_id = media_id_for(digest, existing)
    probe = probe_fn(resolved)
    parameters = {
        "media_id": media_id,
        "name": name or resolved.name,
        "path": str(resolved),
        "sha256": digest,
        "probe": probe.wire(),
        "source_space": source_space,
    }
    if proxy_manager is not None:
        proxies = proxy_manager.build(media_id, resolved, probe)
        parameters["proxy_path"] = proxies.proxy_path
        parameters["thumbnail_path"] = proxies.thumbnail_path
        if proxies.waveform_path:
            parameters["waveform_path"] = proxies.waveform_path
    return EditOperation(
        operation_id=str(uuid.uuid4()),
        type=OperationType.IMPORT_MEDIA,
        target=Target.project(),
        parameters=parameters,
        public_explanation=explanation or f"Imported {parameters['name']}.",
        metadata={"source": "import"},
    )
