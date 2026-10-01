"""Transport-independent local API use cases. Job completion is not a public tool."""

from .capabilities import inspect_capabilities
from .contracts import Command, ProductionBrief, fields, identity, integer
from .demo import run_demonstration
from .planning import CreativePlanning
from .skills import SKILLS, sample_project
from .studio import rehearsal_manifest


def nanoseconds(value):
    # Decimal strings preserve int64 timestamps across JavaScript's 53-bit number boundary.
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 19:
        raise ValueError("Monotonic nanoseconds must be a decimal string")
    return integer(int(value), "Monotonic time")


class DirectorAPI:
    def __init__(self, service):
        self.service = service
        self.planning = CreativePlanning(service)

    def get(self, path):
        if path.startswith("/api/director/studio/"):
            parts = path.removeprefix("/api/director/studio/").split("/")
            if len(parts) != 2:
                raise ValueError("Open a current script from the Director.")
            session_id = identity(parts[0], "Session ID")
            return rehearsal_manifest(self.service.repository.inspect(session_id), parts[1])
        if path == "/api/director/runtime":
            return self.service.runtime()
        if path == "/api/director/planning":
            return {
                **self.planning.status(),
                "samples": {key: sample_project(key)["brief"] for key in SKILLS},
            }
        if path == "/api/director/capabilities":
            return inspect_capabilities(self.service.epoch, self.service.clock()).wire()
        if path == "/api/director/sessions":
            return {"sessions": self.service.repository.list_sessions()}
        prefix = "/api/director/sessions/"
        if path.startswith(prefix):
            session_id = identity(path.removeprefix(prefix), "Session ID")
            return self.service.repository.inspect(session_id)
        raise KeyError("Director endpoint not found")

    def post(self, path, body):
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        if path == "/api/director/creative":
            return self.planning.submit(body, nanoseconds(body.get("expires_monotonic_ns")))
        if path == "/api/director/commands":
            fields(
                body,
                (
                    "schema_version",
                    "operation_id",
                    "runtime_epoch",
                    "expires_monotonic_ns",
                    "scope",
                    "action",
                ),
                ("brief",),
            )
            data = {**body, "expires_monotonic_ns": nanoseconds(body["expires_monotonic_ns"])}
            return self.service.submit(Command.parse(data))
        if path not in ("/api/director/sessions", "/api/director/demo"):
            raise KeyError("Director endpoint not found")
        required = ("schema_version", "operation_id", "runtime_epoch", "expires_monotonic_ns")
        fields(body, required + (("brief",) if path.endswith("/sessions") else ()))
        if type(body["schema_version"]) is not int or body["schema_version"] != 1:
            raise ValueError("Unsupported request schema")
        args = (
            body["operation_id"],
            body["runtime_epoch"],
            nanoseconds(body["expires_monotonic_ns"]),
        )
        if path.endswith("/demo"):
            return run_demonstration(self.service, *args)
        return self.service.create(*args, ProductionBrief.parse(body["brief"]))
