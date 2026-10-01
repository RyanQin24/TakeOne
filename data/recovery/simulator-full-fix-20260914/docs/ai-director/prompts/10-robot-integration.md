# 10 — Qualified cart and arm execution bridge

Implement work package 10 in `C:\TakeOne` as a robotics software engineer. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, the hardware runbook, `docs/cart-live-testing.md`, `docs/cart-runtime-verification.md`, `docs/arm-movement-design.md`, `docs/architecture-review-2026-09-12.md`, and implementation records 03/04/06. Follow shared rules. Dependencies: 03, 04, 06 and independently collected physical qualification.

## Outcome

An accepted shot can be connected to deterministic device execution only within a verified capability envelope. The Director orchestrates planning, recording and progress; the qualified controller owns physical motion. The cart's command timing is independent of AI, vision, rendering and disk work.

## Implement

1. Audit actual code and qualification evidence without altering an active cart test. Identify missing original arm calibration, model-to-servo signs/zeros, phone/light tool transforms, payload/cable/collision limits, starting state, wheel mapping, stopping and feedback. Preserve blockers. Phone wrist-roll remains ID 6 and light ID 5.
2. Reuse existing motion compilation and cart protocol. Add a typed bridge binding execution to accepted plan, capability/calibration revision, measured start state, expiry and recording acknowledgement. A model proposes shot intent; it cannot emit raw motor/servo commands or extend readiness.
3. Fix any remaining full position/aim residual, trajectory-continuity and start/stop acceptance gaps before enabling movement. The five-joint arms have limited task freedom. Keep requested and achieved poses visible. A successful simulation or serial write is not physical tracking evidence.
4. Implement arm-preferred allocation within measured workspace, velocity/acceleration limits and a bounded correction envelope. Use hysteresis, bounded target updates and an explicit base-turn penalty so vision noise does not cause twitchy turns. When the arm cannot satisfy intent, propose a feasible staging/base revision; never assume lateral cart translation.
5. Keep one owner per device and the cart sender isolated from expensive work. The reported watchdog is 60 ms; the current cart runner targets 20 ms sends with stricter host deadline checks. Verify actual configuration rather than rewriting it from this prose. Do not reuse the synchronous combined executor's looser freshness budget as proof of watchdog compliance.
6. Separate actor progress, plan phase and measured execution. Do not stretch quantized UART timestamps to wait for an actor. Continuous actor-follow retiming requires its own qualified progress governor; otherwise remain on the accepted schedule and report deviations. Zero/deadband/command rounding must match the actual wire protocol.
7. Reconcile device faults and recording faults through explicit state transitions. Stop/cancel must not wait on a cloud answer. Log attempted and confirmed stopping separately; do not invent an arm hold pose from stale feedback. No automatic reconnect, resume, calibration or torque action.

## Acceptance

- Offline fake-device tests reject stale plan/calibration revisions, mismatched starts, infeasible tool targets and unqualified capabilities.
- Camera jitter does not cause alternating base turns in the bounded scenario suite.
- Slow or absent AI, vision and disk workers cannot enqueue stale device commands.
- Quantized wheel schedule and deadline behavior remain covered by existing cart tests; updates require focused regression evidence.
- Recording starts before the action window; capture loss and motion faults cannot leave a successful-take state.
- Physical readiness remains false for every missing qualification item.

Automatic tests use fake transports only. A real robot demonstration is a separate human-supervised run with fresh evidence, an explicit run envelope and the hardware team's coordination; this prompt does not authorize unsupervised actuation. Report software completion separately from physical acceptance. Run root verification and write `docs/ai-director/implementation/10-robot-integration.md`; update package 10 according to the evidence.
