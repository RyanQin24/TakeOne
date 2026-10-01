# 05 — Rehearsal coach and conversational voice

Implement work package 05 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/delivery-plan.md`, the model decision in `docs/ai-director-decision-2026-09-12.md`, and implementation records 02–04. Follow shared rules. Dependencies: 02, 03 and 04.

## Outcome

Before recording, the actor can rehearse, ask what to say and receive one useful correction at a time. During recording the Director does not interrupt the performance with coaching. After recording it can discuss the completed review. Conversation never owns robot timing or privileged control.

## Implement

1. Implement beat evaluation from accepted timeline intent and actual observations. Use SATISFIED, VIOLATED and UNKNOWN, with evidence, actor identity, confidence and expiry. Add persistence, hysteresis and cooldown so jitter does not produce repeated instructions. Diagnose camera/setup limitations separately from actor mistakes.
2. Implement a cue policy with one active instruction and explicit cancellation. Rehearsal cues can use prepared phrases for low latency; conversational answers use the selected voice/backend adapter. A decision expires when its beat, actor, session or revision changes.
3. Integrate the selected conversational voice service after verifying current official API contracts. For client delegation, keep application tools and state in the supervisor. Voice interruption must propagate cancellation to pending backend work rather than merely stopping audio playback. Separate transcript data from authenticated operator intent.
4. Connect line help to the accepted script: offer speakable alternatives, demonstrate delivery if requested and save the actor's choice. Unknown product facts remain unknown. Show the same suggestion in text so it is reviewable. Optional text-only mode must be an explicit user mode, not hidden provider-failure behavior.
5. Add a recorder-lifecycle audio gate. From start request, cancel queued coaching and silence ordinary speech until stop is confirmed. Suppress a late model/audio response even if generated earlier. If recording state is unknown, preserve the quiet gate. Package 06 connects the real recorder; test the gate now through its typed event contract.
6. Keep the independent operator stop path responsive. A scripted word such as cut or stop, spoken by an actor, is not an authenticated control message. Human-facing safety/control indications are distinct from performance advice.

## Acceptance

- A sustained observable error generates one relevant rehearsal cue; transient jitter and low-confidence evidence generate none.
- The actor asks for help introducing a product and receives short fact-grounded line alternatives.
- Changing takes, cancelling or interrupting prevents old speech and old tool results from acting later.
- No ordinary coaching is audible after record request, during start uncertainty, during recording or before confirmed stop.
- Scripted cut/stop dialogue does not change recording or motion state.
- Network delay does not grow an unbounded queue or block local observation processing.

Measure the full event-to-cue path and conversational end-of-speech to first audible response, including device/network conditions and persistence delay. Treat plan targets as unproven until measured. Run root verification and inspect the served rehearsal flow. Leave `docs/ai-director/implementation/05-rehearsal-voice.md`, separate offline and live-provider evidence, and update only package 05.
