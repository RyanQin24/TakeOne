---
{
  "name": "reaction",
  "description": "A glance, a pause, and the reaction that tells the story.",
  "metadata": {
    "id": "reaction",
    "version": "2.0.0",
    "name": "Say it without saying it",
    "description": "A glance, a pause, and the reaction that tells the story.",
    "required_facts": [
      "What the actor sees",
      "Eyeline target",
      "Intended reaction"
    ],
    "audience": "Short-form story viewers",
    "tone": "Understated and cinematic",
    "speaking_beats": [
      "Establish the eyeline",
      "Let the discovery register",
      "Deliver a short response"
    ],
    "observable_cues": [
      "Look at a named mark",
      "Pause before the reaction",
      "Keep the face visible"
    ],
    "primitives": [
      "static",
      "arm_pan_tilt"
    ],
    "limitations": [
      "Describe visible acting cues; do not claim to measure internal emotions.",
      "Left and right require a named mark, not guessed motor coordinates."
    ]
  }
}
---

# Say it without saying it

Name what the actor sees, show or establish that object, then direct an observable glance, pause and reaction. An object insert must target the object. Keep silence in audio_intent and leave lines empty when no words are spoken. Match eyelines across independently staged cuts. Do not infer internal emotion from the simulation.
