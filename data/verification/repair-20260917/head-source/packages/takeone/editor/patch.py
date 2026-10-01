"""A JSON Patch subset: enough to synchronise a client mirror, small enough to trust.

Only `add`, `remove` and `replace` are produced. Lists are compared element-wise when the
lengths match and replaced wholesale when they do not — the client learns *what* changed
semantically from the operation that accompanies the patch, so a coarse structural patch
costs nothing and removes an entire class of index-tracking bugs.
"""

from .errors import ValidationError

MAX_OPERATIONS = 4096


def _escape(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def _unescape(token):
    return token.replace("~1", "/").replace("~0", "~")


def diff(before, after, path=""):
    """Structural difference between two JSON documents."""
    operations = []
    _diff_into(before, after, path, operations)
    if len(operations) > MAX_OPERATIONS:
        return [{"op": "replace", "path": path or "", "value": after}]
    return operations


def _diff_into(before, after, path, operations):
    if before == after:
        return
    if isinstance(before, dict) and isinstance(after, dict):
        for key in before.keys() - after.keys():
            operations.append({"op": "remove", "path": f"{path}/{_escape(key)}"})
        for key in after.keys() - before.keys():
            operations.append({"op": "add", "path": f"{path}/{_escape(key)}", "value": after[key]})
        for key in sorted(before.keys() & after.keys()):
            _diff_into(before[key], after[key], f"{path}/{_escape(key)}", operations)
        return
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for index, (left, right) in enumerate(zip(before, after)):
            _diff_into(left, right, f"{path}/{index}", operations)
        return
    operations.append({"op": "replace", "path": path or "", "value": after})


def apply(document, operations):
    """Apply a patch to a *copy* of `document`. Used by tests and by the replay verifier."""
    import copy

    result = copy.deepcopy(document)
    for operation in operations:
        kind = operation.get("op")
        pointer = operation.get("path")
        if kind not in ("add", "remove", "replace") or not isinstance(pointer, str):
            raise ValidationError("Unsupported patch operation")
        if pointer == "":
            if kind != "replace":
                raise ValidationError("Only replace may target the whole document")
            result = copy.deepcopy(operation["value"])
            continue
        tokens = [_unescape(token) for token in pointer.split("/")[1:]]
        target = result
        for token in tokens[:-1]:
            target = target[int(token)] if isinstance(target, list) else target[token]
        last = tokens[-1]
        if isinstance(target, list):
            index = len(target) if last == "-" else int(last)
            if kind == "remove":
                target.pop(index)
            elif kind == "add":
                target.insert(index, copy.deepcopy(operation["value"]))
            else:
                target[index] = copy.deepcopy(operation["value"])
        else:
            if kind == "remove":
                target.pop(last)
            else:
                target[last] = copy.deepcopy(operation["value"])
    return result
