"""Curated, versioned filmmaking knowledge. These records grant no tool authority."""

import copy

SKILLS = {
    "product": {
        "id": "product",
        "version": "1.0.0",
        "name": "The product story",
        "description": "A clear introduction. One useful detail. A reason to care.",
        "required_facts": ["Product name", "One verified feature", "Intended audience"],
        "audience": "People discovering the product",
        "tone": "Natural and confident",
        "speaking_beats": ["Introduce the problem", "Show a verified feature", "Invite a next step"],
        "observable_cues": ["Hold the product toward the lens", "Look at the lens on the final line"],
        "primitives": ["static", "arm_pan_tilt"],
        "limitations": [
            "No invented price, performance, comparisons or benefits.",
            "Use bracketed placeholders when product facts are missing.",
        ],
    },
    "dialogue": {
        "id": "dialogue",
        "version": "1.0.0",
        "name": "A little disagreement",
        "description": "Two perspectives, a little tension, and a well-timed cut.",
        "required_facts": ["Characters", "Conflict", "Room and actor marks"],
        "audience": "Short-form comedy viewers",
        "tone": "Dry and playful",
        "speaking_beats": ["State opposing wants", "Escalate once", "Land a reversal"],
        "observable_cues": ["Keep eyelines toward the other actor", "Hold a beat before replying"],
        "primitives": ["static", "arm_pan_tilt", "straight_dolly"],
        "limitations": [
            "Astra versus Claude is fictional character dialogue, not a product benchmark.",
            "Maintain the line of action; no unplanned crossing of the camera axis.",
        ],
    },
    "reaction": {
        "id": "reaction",
        "version": "1.0.0",
        "name": "Say it without saying it",
        "description": "A glance, a pause, and the reaction that tells the story.",
        "required_facts": ["What the actor sees", "Eyeline target", "Intended reaction"],
        "audience": "Short-form story viewers",
        "tone": "Understated and cinematic",
        "speaking_beats": ["Establish the eyeline", "Let the discovery register", "Deliver a short response"],
        "observable_cues": ["Look at a named mark", "Pause before the reaction", "Keep the face visible"],
        "primitives": ["static", "arm_pan_tilt"],
        "limitations": [
            "Describe visible acting cues; do not claim to measure internal emotions.",
            "Left and right require a named mark, not guessed motor coordinates.",
        ],
    },
}


def sample_project(skill_id):
    """Explicit editorial examples, independent of custom briefs and provider failures."""
    skill = SKILLS[skill_id]
    dialogue = skill_id == "dialogue"
    product = skill_id == "product"
    title = {
        "product": "An introduction worth watching",
        "dialogue": "Astra, Claude & a second opinion",
        "reaction": "The look says everything",
    }[skill_id]
    context = {"skill_id": skill_id, "audience": skill["audience"], "tone": skill["tone"], "facts": []}
    brief = {
        "title": title,
        "objective": (
            "Introduce a product naturally. Product name and features have not been supplied."
            if product
            else "A fictional disagreement: one person prefers Astra, the other prefers Claude. No benchmark claims."
            if dialogue
            else "An actor notices a surprising detail just off camera, then gives a restrained reaction."
        ),
        "duration_ms": 18000,
        "aspect_ratio": "9:16",
    }
    lines = {
        "product": [
            [
                "Meet [product name]. Let me show you one detail.",
                "Here's [product name], up close.",
                "A quick look at [product name].",
            ],
            ["This is [verified feature].", "Take a look at [verified feature].", "Here's the detail."],
            ["Want a closer look?", "What would you like to see next?", "Let's take a closer look."],
        ],
        "dialogue": [
            ["I asked Astra for a second opinion.", "Astra and I have a plan.", "I have a plan. Mostly."],
            ["Funny. I asked Claude for a third.", "Claude would like a word.", "I brought a second plan."],
            ["Maybe we should ask each other.", "Shall we try our own idea?", "Fine. Your turn."],
        ],
        "reaction": [
            ["Wait a second.", "Hang on.", "Oh."],
            ["That was not the plan.", "Well, that's new.", "I did not see that coming."],
            ["Let's try that again.", "One more take?", "You saw that too, right?"],
        ],
    }[skill_id]
    actions = (
        [
            "Hold the product at chest height; look into the lens.",
            "Turn the product slowly to show the verified feature; leave room around it.",
            "Return your eyes to the lens and hold a relaxed finish.",
        ]
        if product
        else [
            "Actor A at mark A looks toward actor B at mark B.",
            "Actor B at mark B pauses, then replies toward mark A.",
            "Actor A holds the eyeline, then lets a small smile appear.",
        ]
        if dialogue
        else [
            "Look toward mark B, a fixed eyeline target just off camera.",
            "Hold for one beat, then let the eyebrows lift slightly.",
            "Look back to the lens and give a small, dry smile.",
        ]
    )
    shots = []
    for index, alternatives in enumerate(lines):
        shots.append(
            {
                "shot_id": f"shot-{index + 1}",
                "start_ms": index * 6000,
                "end_ms": (index + 1) * 6000,
                "actor_id": "actor-b" if dialogue and index == 1 else "actor-a",
                "mark_id": "B" if dialogue and index == 1 else "A",
                "action": actions[index],
                "framing": "close_up" if index == 1 else "medium",
                "primitive": "static",
                "camera_intent": "Hold a fixed frame. Reposition between takes for the closer view.",
                "light_intent": "Soft key from the rear light arm, clear of the phone view; placement unverified.",
                "edit_intent": "Cut on the response; keep a short pause."
                if dialogue
                else "Straight cut on the beat.",
                "lines": [
                    {"text": line, "tone": tone, "fact_ids": []}
                    for line, tone in zip(alternatives, ("Natural", "Shorter", "Playful"), strict=True)
                ],
                "selected_line": 0,
            }
        )
    document = {
        "title": title,
        "logline": brief["objective"],
        "audience": context["audience"],
        "tone": context["tone"],
        "actors": [{"actor_id": "actor-a", "name": "Presenter" if product else "Actor A"}]
        + ([{"actor_id": "actor-b", "name": "Actor B"}] if dialogue else []),
        "marks": [
            {"mark_id": "A", "description": "Actor's starting position; place and measure in Step 3."},
            {"mark_id": "B", "description": "Other actor or eyeline target; position not yet measured."},
        ],
        "questions": ["What is the product name and one verified feature?"]
        if product
        else ["Where should marks A and B be placed in the room?"],
        "scenes": [
            {
                "scene_id": "scene-1",
                "title": "The introduction" if product else "The exchange",
                "location": "Interior · level floor · room to be confirmed",
                "shots": shots,
            }
        ],
    }
    return copy.deepcopy({"brief": brief, "context": context, "document": document})
