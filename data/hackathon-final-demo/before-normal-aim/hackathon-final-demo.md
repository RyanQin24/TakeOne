# HackTheNorth — three-shot demo script

**Three independent takes: 5 s + 5 s + 11 s = 21 s.** These are the requested shots for the one-minute final video; no additional scenes are included here. Two presenters, consistent wardrobe, landscape 16:9. Times below start at the beginning of each recording, after setup.

**Script playback, updated September 20:** Start filming records the iPhone,
initializes the arms, and executes the selected shot's authored movement. There
is no human detection, centering, or live tracking. The monitor is optional.
Cast follows authored performance paths in the preview; both arm target paths are explicit and independent of the people.
Shots 2 and 3 hold both arms relative to the cart. The recorder includes setup
footage before the filmed-source clock; trim that setup footage in the edit.

**Camera adjustment for every shot:** add **−5° pitch** to the intended camera aim. Apply this throughout the walking reveal as well as the other two takes. This is a camera-angle offset, not a −5° change to every arm joint. Keep the horizon level. For shot 3, establish the backward-facing pose and lowered aim before recording, then hold that pose.

## Shot 1 — Walking reveal · 5 seconds

**Scene:** Exterior walkway. Both presenters walk in the same direction as the cart. Both presenters are ahead of the robot, facing the direction of travel. The robot follows behind, filming their backs. Begin framed on legs/waist, then tilt toward their heads as everyone advances.

| Take time | Cart and camera | Performance / sound |
| --- | --- | --- |
| 0–1 s | Start recording and travel forward. Camera begins on lower bodies at 24 mm. | Confident footsteps; both already in stride. |
| 1–4 s | Continue forward and tilt smoothly upward. Maintain the −5° offset throughout. | Optional live line or voiceover: **“Every great demo starts with a good shot.”** |
| 4–5 s | Cart and presenters stop; finish the upward reveal by 5 s. | Hold the final pose. |
| 5 s | End the take. | Cut on the completed reveal. |

## Shot 2 — Left-side camera + delayed zoom · 5 seconds

**Scene:** Open exterior with foreground/background separation for visible parallax. Initialize the camera on the robot's left side, reversing its original side-facing aim by 180°. Preserve the cart's forward travel direction; the simulator calls this **Truck right**. Aim at neck height, approximately **1.50 m** for the illustrative 1.72 m presenters, after applying the −5° offset. Hold both arms relative to the cart throughout the take. The camera does not follow a presenter.

| Take time | Cart and camera | Performance / sound |
| --- | --- | --- |
| 0–2 s | Record and travel along the same forward route, viewing the presenters on the robot’s left. **Hold 24 mm / 1×** with no zoom. | Presenter A: **“And sometimes…”** |
| 2–3 s | Continue cart travel. Zoom **24 → 180 mm** in one second. Keep the −5° aim offset and fixed arm pose. | **“…a closer look.”** |
| 3–5 s | Continue cart travel; hold **180 mm**. | Hold the expression; no person tracking. |
| 5 s | End the take. | Cut on the tight reaction. |

7.5× is interpreted relative to the 24 mm starting view: **180 mm equivalent framing**. The current handset reports a **24–360 mm** range through Blackmagic. TakeOne uses native focal-length commands when that range agrees with the saved measured wide end and the device fingerprint. This does not add calibration points or claim a separate 180 mm optical lens. The achieved image remains unverified until footage is inspected.

## Shot 3 — Time flies · 11 seconds

**Scene:** Robot is already inside the building, looking back toward the entrance. Presenters open the door and walk toward it. When the cart moves deeper inside, the camera remains aimed opposite the direction of travel. Set the arm pose before recording; no arm sweep or live face tracking during this take.

| Take time | Cart / recording | Performance / edit |
| --- | --- | --- |
| 0–3 s | **Record; cart waits.** Camera holds its backward-facing pose, 24 mm, −5° pitch offset. | Open the door and enter. Natural door sound and footsteps. |
| 3–5 s | **Move forward for exactly 2 s**, keeping ahead of the presenters. Requested cruise: **0.30 m/s**; accepted ramp-limited peak: **0.275 m/s**. Arm remains fixed relative to cart. | Walk with the robot, then come to a clean stop. |
| 5–10 s | **Cart stopped for 5 s; continue recording.** Arm and zoom hold. | Presenters freeze. Background becomes fast, blurred movement; layer a rising time-rush sound. |
| 10–11 s | **Remain stopped and recording.** | Snap at 10 s. Instantly remove the blur and time-rush sound. Presenter B urgently says: **“Wait—the hackathon is ending!”** Begin the line on the snap; it is a deliberately quick one-second punchline. |
| 11 s | **Stop recording.** | Hard cut. |

The extra 10–11 s beat resolves the requested 3 s wait + 2 s move + 5 s freeze with recording ending at 11 s.

**Time-rush effect:** after the main take, keep the robot in exactly its final parked pose and record a separate background plate with people crossing behind the presenters' area. Capture 20–30 seconds to compress into the five-second effect. In the edit, mask the still presenters from the main take over the sped-up plate and add directional motion blur to the background. At the snap, cut back to the normal main take. This extra source plate is material for shot 3, not a fourth scene in the final edit. Lock exposure, focus and white balance between the main take and the plate. The preview animates both presenters: door-opening hold at 0–1 s, entrance walk at 1–3 s, walking with the cart at 3–5 s, and a stationary pose at 5–11 s. Door opening, the snap, compositing, and sound remain performance/editing instructions.

## Local scene files

Run `scripts/hackathon_final_demo.py` with the project's Python environment to generate `data/hackathon-final-demo/production.json`, `rehearsal.json`, and `review.json`. Add `--save` to create a separate Director draft. Existing productions are preserved. The script does not run the robot or start a recording.

The saved production is **HackTheNorth final demo — three camera takes** in Director. Open it at `http://127.0.0.1:8766/director.html?session=09059257-081a-4b0a-b3fc-36c2e3e14a80`. Use **Rehearse in studio** to view all three scenes.

The simulated source lengths are exactly **5, 5 and 11 seconds**. Shot 3's cart command schedule moves only from **3–5 s**; both arms retain identical joint goals throughout its recording interval. The planner's final 0.2-second zero-command interval plus a 5.8-second explicit hold creates the full six-second stop from 5–11 s. Optical-position tracks translate with the cart to preserve the fixed arm pose. Setup movement happens before the filming clock.

Shot 1 travels 0.55 m over the five-second take: 0–4 s at the model’s minimum moving speed of approximately 0.1375 m/s, then a one-second stationary hold. This gives **0.11 m/s average**, not continuous 0.11 m/s. The request uses 0.14 m/s to select that minimum command. Shot 2 retains requested cruise of 0.20 m/s and about 1 m of travel. Shot 3 requests 0.30 m/s with an explicit 0.275 m/s pace cap, as agreed to preserve movement exactly from 3–5 s. Its simulated travel is 0.4125 m, including acceleration and deceleration beyond the 0.26 m nominal route. Its average speed during the two-second move is 0.20625 m/s; it does not hold 0.30 m/s throughout. Real distances and actor marks depend on the venue. The saved review has no blocked or revision-level shots. Shot 2 retains a manual crop advisory: 7.5× with fixed neck-height aim can crop the face, so verify the desired detail in the phone view. Zoom beyond the measured mapping still needs physical confirmation. No robot movement or camera recording was performed while creating these scenes.

## Revision verification

The left-side setup is checked using the cross product of drive direction and actor offset; every filmed sample places the actors to the left of the cart. Shot 3 retains identical phone and light arm joint goals while the cart moves from 3–5 s. The delayed zoom, −5° pitch, and 5/5/11-second take lengths remain intact.

The denser acceleration profile exposed the template-preview endpoint’s 4 KiB body limit. `apps/rehearsal/server.py` now allows the same bounded 128 KiB used by path and sequence previews for `/api/previs/templates`; schema validation remains in place. The prior server file and demo source are preserved in `data/hackathon-final-demo/before-left-side-speed/`. An HTTP regression checks acceptance above 4 KiB and rejection above 128 KiB.

The follow/neck/walk revision is preserved against its predecessor in `data/hackathon-final-demo/before-follow-neck-walk/`. Regression checks verify the robot behind the walkers, 0.11 m/s take-average travel, optical neck aim within 2.5 cm, and walking before the 5 s freeze.
