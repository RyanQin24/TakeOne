# Detailed shot-language upgrade: final verification

Completed: 2026-09-15T17:11:04.224612+00:00

The required command, `scripts/TakeOne.ps1 -Command test`, exited 0.
All seven check groups passed on the final source version.

| Check | Result |
| --- | --- |
| Product tests | 723 passed |
| Simulation tests | 29 passed |
| Browser tests | 221 passed; zero failures or skips |
| Browser syntax | Passed |
| Repository integrity | Passed |
| Python lint | Passed |
| Python formatting | Passed |

The server source also passed explicit lint and formatting checks. Both new
Markdown skills passed frontmatter validation. The normal repository Git
whitespace check passed.

## Reviewable exercise

**A small discovery · shot-language exercise**, saved revision 4, is authored
verification data: six shots over 30 seconds, three physical spaces, two
performers, an object insert and an independently keyed walking finish.
All six shots pass their sampled required-region framing check. All nine framing
sizes pass their canonical neutral-actor fixture checks.

Reference: `b00f3ee5-4397-4c4d-b49c-20997dc6160a/cae2b2f293d9b633615fd6b0ce9fcd02ea71fbbbb64075b2875dc72c31ccbcd8`

The final silent production retains all 13 timed performance beats and film
rules in voice context: 29,810 bytes within the
32,768-byte state limit. Persona limits remain 16,384 bytes.

[Open the saved rehearsal](http://127.0.0.1:8766/?script=b00f3ee5-4397-4c4d-b49c-20997dc6160a/cae2b2f293d9b633615fd6b0ce9fcd02ea71fbbbb64075b2875dc72c31ccbcd8).
[Read the shooting guide](shooting-guide.md).

The browser reader and copy flow were verified. The embedded browser did not
deliver a file-download event; the standalone guide uses the same frontend
export function and final program.

## Evidence boundaries

A fresh paid Director request was not sent. Provider request construction,
instruction loading and byte/cost bounds were checked locally. The exercise is
not presented as a provider-generated result.

No hardware motion, live tracking, phone recording or recorded film was used
as evidence. Cart-follow and head-follow integration remains pending. Phone
lens, crop and focus setup is manual. Simulated coverage does not establish
occlusion, full rig clearance, measured site geometry, individual performer
proportions, facial acting, sound or physical repeatability.

## Saved evidence

- `verification/summary.json` and `verification/check-0.txt` through `check-6.txt`: complete final run, original log bytes preserved.
- `camera-evidence.json` and `nine-framing-evidence.json`: sampled camera geometry.
- `browser-evidence.json`: observed editing, framing, cues and guide behavior.
- `voice-context-evidence.json`: actual saved-production context measurement.
- `instruction-budget-evidence.json`: unsent request and shared persona budgets.
- `final-script.json`, `final-program.json`, `shooting-guide.md`: matching final exercise.
- `change-manifest.json`: source and documentation inventory.

Earlier interrupted runs and the earlier complete successful run remain as
historical diagnostics. This complete final run supersedes them.
