# 09 — Optional generated effects on selected footage

Implement work package 09 in `C:\TakeOne`. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/provider-decisions.md`, and package 08's implementation record. Follow shared rules. Dependency: 08. Preserve the complete original-edit/export workflow.

## Outcome

The user selects a real take or edit interval, describes a visual change, previews the intended look and receives a separately reviewable derivative. TakeOne owns editorial decisions; the generation service supplies an effect. Originals remain intact and generation is never a prerequisite for shooting or editing.

## Implement

1. Verify the selected provider's current API, model entitlement, upload requirements, input duration/resolution/FPS, retention and billing. Start with the documented Runway `aleph2` route for precise-edit evaluation. Treat `seedance2_5` as an explicit alternative experiment with its own reference/extend semantics. Do not use retired model identifiers or assume website features equal API features.
2. Define EnhancementJob with original media and edit revision, interval, effect intention, preserve/change constraints, optional region/keyframe references, explicit provider/model, cost ceiling, operation identity, provider job identity and output lineage. Keep user-facing choices about appearance rather than implementation details.
3. Prepare an explicit conforming derivative when input rules require it. Keep source-to-derivative timing, crop, color and audio mappings. A keyframe/look preview helps choose style but does not promise unchanged identity or temporal consistency in generated output.
4. Implement a server-side submit/status/reconcile/cancel boundary with durable pending intent. A timeout with unknown submission outcome must not cause a second paid generation. Use provider idempotency where supported; otherwise expose reconciliation/manual resolution. Cancellation cannot claim a refund or stopped computation unless confirmed.
5. Submit media only within the user's selected upload and spending scope. Store keys outside the browser. Return useful failures for unavailable credentials, unsupported inputs, exhausted budget and provider errors. Never automatically switch provider or claim a fake generated result.
6. Compare output with source for face/product consistency, requested region, motion continuity, duration, lip/audio synchronization and unwanted changes. Show before/after review and accept/reject. Reuse original audio only when timing alignment is verified; different generated pacing requires an explicit re-edit, not blind remuxing.

## Acceptance

- One permitted real clip produces a provider-confirmed, decodable derivative whose source and cost are recorded.
- Duplicate submission, crash/restart, timeout and cancellation do not silently create a second paid job.
- Rejected outputs and failed jobs leave the accepted original edit unchanged.
- A changed face, product detail or timing is surfaced for review rather than labeled preserved by the prompt alone.
- The app can still export the original edit with generation unavailable.
- Credentials and private media URLs do not appear in client state or logs unnecessarily.

Use offline provider fixtures for automatic tests. A live generation test requires configured access, a permitted sample and an explicit budget; if absent, finish independent integration work and report live validation pending. Do not install the whole referenced studio or train a video model. Run root verification and leave `docs/ai-director/implementation/09-generated-effects.md`. Update package 09 only.
