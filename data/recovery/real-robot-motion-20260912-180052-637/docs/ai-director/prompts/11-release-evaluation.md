# 11 — Integrated release, model economics and product evaluation

Implement work package 11 in `C:\TakeOne` as the release engineer and product evaluator. Read root AGENTS/README, `docs/ai-director/implementation-rules.md`, `docs/ai-director/delivery-plan.md`, `docs/ai-director/provider-decisions.md`, and the implementation records for the selected release profile. Follow shared rules.

Dependencies: packages 01–08 for the core original-footage release. Add 09 for the effects profile; add 10 and independent qualification for the motion profile. A missing optional profile must remain explicitly excluded, not silently counted as passed.

## Outcome

A reproducible release report proves which complete user workflows work on the actual equipment and selected models, identifies remaining gaps and measures the cost of a useful result. The app is understandable to a nontechnical actor. Do not declare success from isolated unit tests or provider marketing.

## Implement and evaluate

1. Create a small permissioned evaluation corpus with annotated briefs, beats, takes and review outcomes. Follow the existing proposed pilot of 30 varied briefs and at least 60 short performance clips where available; report the actual sample count. Split by actor/take/setup, not adjacent frames. Do not fabricate labels or claim broad statistical coverage from a tiny pilot.
2. Run two end-to-end scenarios: a product introduction with line assistance, and dialogue coverage for a short argument using separate takes/offscreen partner. Exercise brief, script revision, preview, rehearsal, acknowledged capture, quiet recording, review, take choice and original export. Verify actual served UI and watch the output.
3. Run failure scenarios for actor crossing/loss, intentional exit, stale frames, ambiguous directions, uncertain head view, scripted cut/stop, cancelled voice, delayed reviews, recorder failure, full disk, missing media and provider timeout. Include bounded concurrency tests without disturbing physical testing.
4. Measure capture-to-observation, persistence delay, cue onset, conversation response, transfer, first review, edit render and optional generation separately and end to end. Report p50/p95/p99, sample counts, actual hardware/network/load and queue/resource behavior. Targets are in the delivery plan; missing them requires a visible result and diagnosis.
5. Measure cost per accepted take and finished minute including rejected/retried generations, active voice minutes, reasoning/vision usage and local compute. Compare an explicitly selected local semantic candidate with the established cloud baseline only on equivalent tasks/evidence. Qwen3.5-4B is a candidate from the decision, not an assumed winner on this laptop. Keep optional model dependencies isolated from cart/LeRobot environments.
6. Review quality using observable-error precision/recall/UNKNOWN coverage, human usefulness ratings and false/unhelpful cues per rehearsal minute. Subjective acting advice is not ground truth. Ask whether users finish useful takes with less effort than their previous workflow; do not infer product differentiation from feature count.
7. Make release status and recovery clear: original-only core, optional effects, optional qualified motion. Repair concrete integration failures within this package's scope, but do not hide unsupported features, relax acceptance thresholds after seeing failures or claim a profile that was not exercised.

## Acceptance

- The complete core workflow produces a real playable exported video with source lineage and evidence-linked review.
- Release report names versions/devices, actual test data, measured results, failures and untested profiles.
- Ordinary coaching is absent during every tested recording interval; old results never change a newer take.
- Original edit/export works with generation unavailable.
- No model is selected solely from a general benchmark, parameter count or a guessed tokens-per-second rate.
- Hardware performance is reported only from explicitly supervised measurements, separately from software timing.

Run root verification and the opt-in camera/provider checks needed for the selected profile. Create `docs/ai-director/implementation/11-release-evaluation.md` with reproducible commands, artifacts and a release recommendation. Update the package and release-profile statuses from evidence. Do not label an incomplete demo production-ready.
