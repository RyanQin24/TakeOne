"""VFX instructions on the existing configured Responses transport and budget."""

from takeone.director.provider import PlanningError, ResponsesPlanner

from ..contracts import encode
from ..ids import digest
from .vfx import INSTRUCTIONS, SCHEMA


class VFXResponsesPlanner:
    def __init__(self, config=None, api_key=None):
        self.transport = ResponsesPlanner(config=config, api_key=api_key)
        self.config = self.transport.config

    def status(self):
        return self.transport.status()

    def request(self, payload):
        return self.transport.reserve_request(
            {
                "model": self.config["model"],
                "store": False,
                "instructions": INSTRUCTIONS,
                "input": encode(payload),
                "max_output_tokens": self.config["max_output_tokens"],
                "reasoning": {"effort": self.config["reasoning_effort"]},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "takeone_vfx_proposal_v1",
                        "strict": True,
                        "schema": SCHEMA,
                    }
                },
            }
        )

    def generate(self, payload):
        raw, _ = self.request(payload)
        result = self.transport.transmit(raw)
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("output"), list)
            or any(
                not isinstance(item, dict) or item.get("type") not in ("message", "reasoning")
                for item in result["output"]
            )
        ):
            raise PlanningError("malformed_response", "Unexpected provider output.")
        parsed = self.transport.parse_response(result, payload, include_filming=False)
        parsed.provenance.update(
            {
                "request_instructions_digest": digest(INSTRUCTIONS),
                "instructions_source": "vfx_proposal_v1",
                "observation_basis": "supplied_observations_only",
            }
        )
        return parsed
