# 08 — Original-footage editing and conversational revisions

Implement work package 08 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/provider-decisions.md`, and implementation records 01/06/07. Follow shared rules. Dependencies: 01, 06 and 07.

## Outcome

TakeOne creates a finished original video from accepted takes. The user can say use take two, shorten the opening, keep the pause, or add captions; the app shows an inspectable edit, previews it and exports a playable file. No generated-video provider is required.

## Implement

1. Define a versioned EditPlan/EDL referencing immutable take/media IDs and actual source presentation-time ranges. Include clip order, trim handles, dialogue/audio alignment, transitions, crops, captions and output format. Distinguish source time from edit time and maintain a reversible mapping.
2. Build a narrow edit planner using shot purpose, accepted takes, actual transcripts and continuity notes. Keep source footage as authority. Do not automatically remove every pause or select highlights by generic engagement scoring when a dramatic pause serves the scene.
3. Implement deterministic rendering with FFmpeg or an equivalently justified mature local media tool. Pin/document the dependency; validate ranges and streams before rendering. Construct tool arguments from allowlisted operations using argument arrays, never execute model-generated shell text.
4. Offer transcript-based trimming, take substitution, captions, basic crop/layout, sound levels and simple titles. Reframe only within available image content; unavailable angles and resolution stay unavailable. Maintain original dialogue unless the user chooses a separate alteration workflow.
5. Convert natural-language edits into a scoped proposed edit revision. Show what changes, preserve previous revisions and support undo. Ambiguous operations need clarification; the model cannot invent a clip or silently discard an accepted take.
6. Add job progress/cancellation, output validation and artifact lineage. Use temporary outputs followed by verified completion; never overwrite originals. Record rendering settings, source hashes, expected/actual duration and audio. Provide an exportable edit manifest alongside the video.

## Acceptance

- Two or more accepted takes become a correctly ordered playable output with source-to-output mapping.
- Use take two or shorten the opening produces the requested scoped change and can be undone exactly at the edit-plan level.
- Captions align to actual recorded speech rather than the original intended script.
- Invalid source ranges, missing assets, failed renders and disk-full conditions cannot create a successful export status.
- Variable frame rate, rotation and differing source audio formats have explicit handling and a tested output policy.
- The original editing/export workflow completes with the effects provider disabled.

Keep UI work inside the existing app; do not fork a full Vizard/Open Generative AI studio. Run root verification and inspect/play an actual export. Technical media assertions alone do not replace watching the resulting cut. Leave `docs/ai-director/implementation/08-editing.md`, including any unsupported operations, and update package 08.
