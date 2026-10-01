# 06 — Real recording and original take lifecycle

Implement work package 06 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, recording reference configuration, package 04's actual-device decision and implementation records 01/03. Follow shared rules. Dependencies: 01, 03 and 04. Coordinate the shared recorder events with package 05.

## Outcome

The user starts a take through the app, sees truthful recording state, finishes it and receives a playable verified original. The accepted script/shot, observed performance and actual media stay associated. Recording is never declared successful because a command was merely sent.

## Implement

1. Implement one concrete recorder adapter for the verified device integration. Support capability inspection, start request, start acknowledgement, stop request, stop acknowledgement, finalization and verified media retrieval. Report unsupported phone controls rather than assuming an OS or claiming an imported clip was remotely recorded.
2. Add idempotent take/request IDs and durable lifecycle events. The action window begins only after positive recording acknowledgement and any explicit pre-roll. Record request already closes the coaching audio gate. Define acknowledgement timeouts, unknown states and late/duplicate responses.
3. Preserve originals with content identity and TakeRecord metadata: accepted plan/script/configuration revisions, actual camera/lens/crop/FPS/audio settings, requested and acknowledged times, source role, clock mapping and uncertainty. Record start/end media handles; estimated timestamps cannot masquerade as measured exposure times.
4. Associate media presentation timestamps with monotonic observations using the selected integration and a verified synchronization method. Handle variable frame rate, rotation, audio offset and drift. A clap/flash can estimate an offset, but its uncertainty and drift limits must remain explicit.
5. Finalize files transactionally enough to distinguish partial transfer, complete file and validated take. Check existence, nonempty content, decode, duration, expected streams, audio status and checksums before review eligibility. Do not delete or overwrite original takes during retakes or export.
6. Integrate Ready, Starting, Recording, Finalizing and Review-ready screens with actual adapter evidence. Camera failure or disk exhaustion cannot leave the UI claiming success. Restart reconciles device/media status and does not automatically start recording or motion again.

## Acceptance

- An actual supported camera records a take whose file decodes, plays with the expected audio and references the accepted shot.
- Delayed start acknowledgement prevents an early action cue; failed acknowledgement leaves a truthful non-recording/unknown state.
- Duplicate requests do not create duplicate takes; late responses remain attached to their original take.
- Disconnect, disk-full and interrupted transfer keep corrupt/incomplete media out of review and export.
- Coaching remains silent across the complete recording interval, including queued and late voice results.
- Stop acknowledgement and media finalization are separate; neither is evidence of a physical robot stop.

Use offline adapter failure tests, root verification and an opt-in actual-device demonstration. If remote phone control is unavailable, finish the interface and report the exact blocker; an explicit file-import workflow may be useful but cannot close remote-capture acceptance. Leave `docs/ai-director/implementation/06-recording.md` and update package 06 only.
