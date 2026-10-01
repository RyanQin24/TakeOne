# Editing and effects: researched integration decisions

Research date: 2026-09-12. Public documentation was inspected; no account, paid generation, uploaded footage or quality benchmark was tested. Capabilities below are vendor-documented, not TakeOne verification.

## Build, integrate or defer

| Reference | What was verified | TakeOne decision |
|---|---|---|
| Vizard Agent | Published workflows describe footage selection, narrative assembly and conversational revision | Borrow the interaction pattern; build a focused editor around known shots and take metadata |
| Vizard API | Public API documentation covers clipping, transcripts, subtitles and presentation settings | Optional later adapter for long-footage repurposing; do not assume full Agent website functionality is exposed |
| Runway Aleph 2.0 | Documented video editing API and keyframe-guided changes | First effects adapter candidate for selected real clips |
| Seedance 2.5 | Runway lists video input alongside image/text inputs | Explicit alternative to evaluate; reference/extend modes do not guarantee exact source preservation |
| Open Generative AI | MIT-licensed studio code with a MuAPI client | Reference for job/UI patterns; avoid importing the entire studio or mistaking it for local model weights |

Vizard's [Agent editing example](https://agent.vizard.ai/use-cases/vlog.html) describes conversational recuts. Its [API introduction](https://docs.vizard.ai/docs/introduction) documents a narrower clipping interface. Full Agent API parity was not established. TakeOne already knows shot purposes, chosen takes and intended dialogue; its editor should use that information rather than rediscover everything from pixels.

The repository's [README](https://github.com/anil-matcha/open-generative-ai) and [API client](https://raw.githubusercontent.com/Anil-matcha/Open-Generative-AI/main/packages/studio/src/muapi.js) show cloud submissions and polling. Its [license](https://raw.githubusercontent.com/Anil-matcha/Open-Generative-AI/main/LICENSE) is MIT; retain required notices if reusing code. Hosting the UI locally does not move the underlying generation models onto the laptop. No code was copied for this plan.

## Concrete access path

Runway's current [model catalog](https://docs.dev.runwayml.com/guides/models/) lists `aleph2` and `seedance2_5`. Its [API changelog](https://docs.dev.runwayml.com/api-details/api_changelog/) records Aleph 2.0 access on June 2 and Seedance 2.5 access on August 7, with 1080p support added August 15. This updates the earlier decision document's uncertainty about a public Seedance 2.5 route; this user's account and regional eligibility remain untested.

Use the documented video-to-video endpoint through one server-side adapter. Resolve credentials, entitlement, input rules, billing and upload behavior before an opt-in integration test. Do not make browser automation of the vendor website the production integration.

Aleph accepts 2–30 second inputs at up to 1080p and at most 30 FPS, with timestamped keyframe guidance. Preserve original media and make an explicit conforming derivative if needed. [Input requirements](https://docs.dev.runwayml.com/assets/inputs/), [editing guide](https://help.runwayml.com/hc/en-us/articles/52150503729171-Aleph-2-0-Prompting-Guide).

Seedance's documented video modes are reference and extend. Evaluate whether they deliver the intended effect without unacceptable changes to performance, timing or products. A similar-looking generated video does not prove the photographed action was preserved. [API changelog](https://docs.dev.runwayml.com/api-details/api_changelog/).

## Cost checkpoint

Illustrative standard generation costs, before tax, previews, retries, extra references and optional output formats:

| Model / resolution | Documented rate | Five-second example |
|---|---|---|
| Aleph 2.0 | 28 credits/second; 56-credit minimum | 140 credits = $1.40 |
| Seedance 2.5 / 720p | 30 credits/output second + 15/input-video second | 5 seconds in + 5 out = 225 credits = $2.25 |
| Seedance 2.5 / 1080p | 68 credits/output second + 34/input-video second | 5 seconds in + 5 out = 510 credits = $5.10 |

Runway lists $0.01 per credit and an 80-credit minimum for Seedance 2.5. Recheck rates during implementation. These examples are arithmetic, not measured quality or a session quote. [Official pricing](https://docs.dev.runwayml.com/guides/pricing/).

## Focused product workflow

TakeOne owns source selection, cuts, pacing, captions, audio alignment, revisions and export. Use deterministic compositing for titles and simple effects where it gives reliable control. Use generation for a selected change whose value warrants its cost.

The user chooses a take and effect interval. Save preserve/change requirements, prepare a representative frame or low-cost look preview, then submit an explicitly budgeted clip job. Review the derivative beside the original. A preview image is a look reference, not a guarantee of temporal consistency.

Keep one explicit provider/model per job, stable job identity, cancellation/reconciliation and complete source lineage. Failed providers do not trigger another paid provider automatically. Original export remains a first-class feature.

Evaluate permissioned TakeOne footage for face/product preservation, requested effect, background stability, motion continuity, dialogue sync, cost per accepted result and elapsed time. Choose the provider from evidence. Do not train a foundation video model or build a marketplace of hundreds of models.
