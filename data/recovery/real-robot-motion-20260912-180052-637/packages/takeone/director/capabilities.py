"""Read configuration evidence without discovering, connecting or configuring devices."""

from dataclasses import asdict, dataclass

from takeone.calibration import hardware_blockers
from takeone.config import file_hash, read_json
from takeone.paths import CALIBRATION, CONFIGS, MODELS

from .provider import ResponsesPlanner
from .service import COMMAND_TTL_NS, fingerprint


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    available: bool
    source: str
    explanation: str


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    snapshot_id: str
    runtime_epoch: str
    observed_monotonic_ns: str
    expires_monotonic_ns: str
    capabilities: tuple[Capability, ...]
    hardware_blockers: tuple[str, ...]
    configuration_hashes: tuple[tuple[str, str], ...]

    def wire(self):
        return {"schema_version": 1, **asdict(self)}


def inspect_capabilities(runtime_epoch, now_ns):
    recording = read_json(CONFIGS / "reference/recording.json")
    preview = (MODELS / "rig_tall.xml").is_file()
    blockers = tuple(hardware_blockers())
    # A configured endpoint would still need the actual recorder adapter and qualification.
    phone_configured = bool(recording["phone"].get("preview_url"))
    planning = ResponsesPlanner().status()
    capabilities = (
        Capability("Save and resume video ideas", True, "implemented", "Stored locally in this workspace."),
        Capability("3D rehearsal studio", preview, "simulated", "Existing preview; not physical readiness."),
        Capability(
            "Script and shot editor", True, "implemented", "Versioned creative proposals and line choices."
        ),
        Capability(
            "AI script planning",
            planning["available"],
            planning["state"],
            planning["message"],
        ),
        Capability(
            "Phone preview and recording",
            False,
            "not_integrated",
            "Endpoint configured; adapter not integrated."
            if phone_configured
            else "Actual phone integration and recording controls have not been selected.",
        ),
        Capability(
            "Actor tracking and voice", False, "not_integrated", "Camera and voice modules are not connected."
        ),
        Capability("Robot execution", False, "not_integrated", "No Director motor interface is enabled."),
    )
    paths = (
        CONFIGS / "rig.json",
        CONFIGS / "qualification.json",
        CONFIGS / "reference/recording.json",
        CALIBRATION / "registry.json",
    )
    hashes = tuple((str(path), file_hash(path)) for path in paths)
    return CapabilitySnapshot(
        fingerprint({"epoch": runtime_epoch, "now_ns": now_ns, "hashes": hashes}),
        runtime_epoch,
        str(now_ns),
        str(now_ns + COMMAND_TTL_NS),
        capabilities,
        blockers,
        hashes,
    )
