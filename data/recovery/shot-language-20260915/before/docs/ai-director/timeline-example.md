# A shared timeline: worked product example

This is a design example, not a compiled plan, observed performance or approved robot trajectory. Geometry and timings are illustrative. Confirmed product facts replace the placeholders before filming.

Brief: a 12-second vertical introduction to a reusable bottle. One actor, one standing mark, verified product name and one verified benefit. The first real-camera milestone uses a stationary camera; an arm-follow variant is separately compiled and remains preview-only until qualified.

| Shot-relative time | Actor and dialogue | Camera intent | Phone arm / cart | Light intent | Capture and edit |
|---|---|---|---|---|---|
| 0:00–0:01 | Settle on mark A; look at lens | Medium framing, room for product | Hold accepted setup; cart hold | Aim at face; avoid label glare | Recording acknowledged before action zero; retain lead handle |
| 0:01–0:04 | Raise bottle from table to chest; “This is [product name].” | Keep face and bottle visible | Stationary profile: hold. Arm-follow profile: derive tilt from targets and feasible IK; cart hold | Follow accepted face/product target within reach | No spoken coaching; collect observations silently |
| 0:04–0:08 | Turn label toward lens; “It helps me [verified benefit].” | Preserve readable product area | Hold or small qualified arm adjustment; no unplanned base turn | Reduce glare through achievable change or propose another setup | Tag possible product insert; do not invent an unavailable angle |
| 0:08–0:11 | Lower bottle slightly, look at lens; “Here is how I use it.” | Return emphasis to face | Accepted target; cart hold | Maintain face lighting | Optional VFX note: graphic accent beside bottle after take selection |
| 0:11–0:12 | Hold expression and product for cut | Stable end frame | Settle and hold | Hold | Retain tail handle; confirm stop; finalize original |

The timeline describes synchronized tracks, not independently commanded movements. At 0:02, the intention is to keep two subjects visible; the planner must choose a feasible lens pose and expose residual error. It may propose different staging if the rig cannot meet the composition.

## Helping with the words

Before recording, the actor can say, “I don't know how to introduce it.” The Director can answer: “Try: ‘This is [product name]. I use it when [your real use case].’ Say it once in your own words and we can shorten it.”

Offer concise, friendly or dramatic alternatives without inventing specifications, personal experience or benefits. An accepted line updates the script revision; timings and rehearsal regenerate from that revision. An optional teleprompter is an explicit presentation mode and does not prove the actor followed it.

## Exact ranges with natural performance

Store intervals as half-open ranges: [1000, 4000) milliseconds belongs to the 0:01–0:04 beat. A beat may also have a semantic trigger, such as the previous line's completion, and an allowed timing window. Planned time, actor progress and actual media timestamps remain distinct.

For slow delivery, record actual line timing. During rehearsal, suggest a shorter sentence or revise duration. During the first recording release, there is no actor-driven cart retiming; missed beats become review notes. A later qualified progress controller must revalidate acceleration, stopping and command quantization rather than stretch UART packet timestamps.

Media may have variable frame rate. Associate evidence and edits with presentation timestamps and explicit clock mappings; do not assume frame 120 always means four seconds. The UI can display friendly timecodes.

## The stairs example

“Actor walks downstairs, arm tilts up” is not a universal rule. With a stationary lens, a descending face generally reduces elevation angle; distance and camera motion also matter. In a frame with vertical z, simple target elevation is:

`elevation = atan2(target_z - lens_z, horizontal_distance)`

This is an aiming intention, not a servo command. Solve with the actual lens transform, available joints, composition constraints and measured geometry. Never feed screen y directly into a mechanical joint sign.

Stairs need the actor path's height and the camera/room transform. The first physical cart scope stays on a qualified level surface. If stairs or the path are unsupported, preserve the creative request and state the missing capability; do not silently simulate a flat path or drive the cart onto steps.

## Review after the take

After confirmed stop and media validation, useful feedback could be:

“The opening and product reveal are clear. At 0:05–0:06 the label turns away from the lens; here are the frames. On the next take, keep the label toward the camera for one beat longer. You can keep this take or try that adjustment.”

This illustrates the desired form, not a finding about existing footage. Technical observations require evidence. A suggestion such as leaving a longer pause is an artistic option, not a diagnosis of emotion or a claim that the actor is bad. Give one strength and at most two actionable changes, with accept/retake/revise choices.
