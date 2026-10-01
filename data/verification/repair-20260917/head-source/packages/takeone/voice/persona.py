"""The director persona locked into every live token. The browser cannot alter it.

The persona inherits the robot-film-director SKILL verbatim — including its
refusal to invent failure thresholds, hardware-readiness approvals or measured
wheel accuracy — and adds the conversational rules the live transport needs:
speak in short turns, act only through tools, stay silent while recording.
"""

PERSONA_MAX_BYTES = 16 * 1_024

CONVERSATION_RULES = """\
# TAKE ONE ("TO") — live director
Speak briefly and specifically.

- Never claim hardware readiness, safety approval or measured accuracy.
- Never promise a shot before the simulator has compiled it. Never invent numbers; use tool evidence.
- Spoken agreement changes nothing: durable decisions require tools.
- For ambiguous embodied requests: inspect_scene → select_subject with returned transient track IDs → prepare_filming_behavior.
  Physical motion is started by the operator through armed Live Director authority; disarmed means not moving.
- Active behavior may adjust framing/size only; new subject/motion requires hold/stop then a new prepare.
  Local tracking/servo owns continuous following; never ask Gemini to chase a person frame-by-frame.
- Explain refusals briefly. While recording you say nothing at all unless spoken direction is authored.
- Request visual evidence only when needed. Production/local behavior state is authoritative.
"""


def speaking_style(skill):
    """One skill's voice coaching, folded into the persona when a skill is active."""
    lines = [f"## Active skill: {skill['name']}", "", skill["description"], ""]
    lines.append("Speaking beats to guide the performer through: " + "; ".join(skill["speaking_beats"]) + ".")
    lines.append("Observable cues to watch and coach for: " + "; ".join(skill["observable_cues"]) + ".")
    lines.append("Tone: " + skill["tone"] + ".")
    for limitation in skill["limitations"]:
        lines.append("Limitation: " + limitation)
    return "\n".join(lines)


def build_persona(skill=None, *, filming_skill_text=None):
    """The complete system instruction. Deterministic for a given skill and SKILL.md."""
    if filming_skill_text is None:
        from takeone.director.studio import skill_text

        filming_skill_text = skill_text()
    sections = [CONVERSATION_RULES]
    if skill is not None:
        sections.append(speaking_style(skill))
    sections.append("# Filmmaking contract (verbatim project skill)\n\n" + filming_skill_text)
    persona = "\n\n".join(sections)
    size = len(persona.encode("utf-8"))
    if size > PERSONA_MAX_BYTES:
        raise ValueError(f"Persona is {size} bytes; the ceiling is {PERSONA_MAX_BYTES}")
    return persona
