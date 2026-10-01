# Analysis 5 - duplicated archives and data/ accounting

## Archive hashes (SHA-256)
- archive\imports\TakeOne-main.zip  bytes=18051572  sha256=4c7bc50a16577149de90c61dcb5249e801df33174725b7de3f95467f76b9dc4d
- archive\restore-verification\TakeOne-main.zip  bytes=18051572  sha256=4c7bc50a16577149de90c61dcb5249e801df33174725b7de3f95467f76b9dc4d
- archive\imports\lerobot-upload.tar.gz  bytes=6537938  sha256=e1a02b3d7efbf145d0b989b5248e7bef5e14d4bc820efbde1774a64c5f637b71
- archive\restore-verification\lerobot-upload.tar.gz  bytes=6537938  sha256=e1a02b3d7efbf145d0b989b5248e7bef5e14d4bc820efbde1774a64c5f637b71
- (archive >1MB) archive\imports\lerobot-upload.tar.gz  bytes=6537938
- (archive >1MB) archive\imports\rehearsal-dist.zip  bytes=1546227
- (archive >1MB) archive\imports\TakeOne-main.zip  bytes=18051572
- (archive >1MB) archive\imports\TakeOne-main\TakeOne-main\reference-video-beats.png  bytes=1334852
- (archive >1MB) archive\imports\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence.zip  bytes=7305770
- (archive >1MB) archive\restore-verification\lerobot-upload.tar.gz  bytes=6537938
- (archive >1MB) archive\restore-verification\TakeOne-main.zip  bytes=18051572
- (archive >1MB) archive\restore-verification\lerobot\uv.lock  bytes=1166845
- (archive >1MB) archive\restore-verification\lerobot\media\readme\robots_control_video.webp  bytes=2425850
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\reference-video-beats.png  bytes=1334852
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence.zip  bytes=7305770
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist.zip  bytes=1546227
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist\reference.mp4  bytes=1545985
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist\dist\reference.mp4  bytes=1545985
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist\models\take-one-panel.glb  bytes=5015248
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist\models\take-one-ring.glb  bytes=5034188
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\dist\models\take-one-tube.glb  bytes=5038240
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\verification\default-prediction.json  bytes=2067724
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\verification\legacy-orbit-prediction.json  bytes=2229541
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\rehearsal-mvp\verification\steady-arc-prediction.json  bytes=2110512
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\results\sha256.json  bytes=1170130
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\base_motor_holder_so101_v1.stl  bytes=1877084
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\motor_holder_so101_base_v1.stl  bytes=1129384
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\motor_holder_so101_wrist_v1.stl  bytes=1052184
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\moving_jaw_so101_v1.stl  bytes=1413584
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\under_arm_so101_v1.stl  bytes=1975884
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\upper_arm_so101_v1.stl  bytes=1303484
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\wrist_roll_follower_so101_v1.stl  bytes=1439884
- (archive >1MB) archive\restore-verification\TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation\upstream\assets\wrist_roll_pitch_so101_v2.stl  bytes=2699784

## Is TakeOne-main tracked by git?
79 tracked files under TakeOne-main/
git log for TakeOne-main (first 5):
6036010 Publish complete workspace including modified LeRobot and recovery assets
f928842 Update TakeOne workspace and include simulator dist
root tests/ that came from TakeOne-main/tests (git status):
 D TakeOne-main/tests/browser-evidence/01-loaded.png
 D TakeOne-main/tests/browser-evidence/02-import-missing-file.png
 D TakeOne-main/tests/browser-evidence/03-imported.png
 D TakeOne-main/tests/browser-evidence/04-analysed.png
 D TakeOne-main/tests/browser-evidence/05-shot-selected.png
 D TakeOne-main/tests/browser-evidence/06-after-split.png
 D TakeOne-main/tests/browser-evidence/07-intent-applied.png
 D TakeOne-main/tests/browser-evidence/08-compiled.png
 D TakeOne-main/tests/browser-evidence/09-playing.png
 D TakeOne-main/tests/browser-evidence/10-tracking-loss.png
 D TakeOne-main/tests/browser-evidence/11-complete.png
 D TakeOne-main/tests/browser-evidence/console.log
 D TakeOne-main/tests/browser-evidence/results.json
 D TakeOne-main/tests/browser.mjs
 D TakeOne-main/tests/fixtures.py
 D TakeOne-main/tests/governor-trace.json
 D TakeOne-main/tests/governor.test.mjs
 D TakeOne-main/tests/make_governor_trace.py
 D TakeOne-main/tests/program.test.mjs
?? tests/browser.mjs
?? tests/fixtures.py
?? tests/governor-trace.json
?? tests/governor.test.mjs
?? tests/make_governor_trace.py
?? tests/program.test.mjs
.gitignore mentions TakeOne-main? False

## data/ accounting
total data/: 303.4 MB in 945 files
- data/checked-plans: 39.33 MB, 54 files
- data/commissioning: 44.31 MB, 66 files
- data/director: 0.08 MB, 1 files
- data/logs: 0.01 MB, 4 files
- data/real-robot-measurement-templates: 0 MB, 4 files
- data/real-robot-measurement-templates-final: 0 MB, 4 files
- data/real-robot-measurement-templates-v2: 0 MB, 4 files
- data/real-robot-mobile-ik-measurements-20260912: 0 MB, 3 files
- data/recovery: 20.53 MB, 279 files
- data/reference-analysis: 1.12 MB, 8 files
- data/runs: 109.3 MB, 361 files
- data/verification: 47.23 MB, 106 files

### largest 30 files in data/
- 39.68 MB  data\verification\photo-export-payloads.json
- 4.83 MB  data\recovery\ring-size-20260912-230908\take-one-tube.glb
- 4.82 MB  data\recovery\ring-size-20260912-230908\take-one-ring.glb
- 4.8 MB  data\recovery\ring-size-20260912-230908\take-one-panel.glb
- 4.59 MB  data\runs\20260913T032141Z-robot-e033caa6\plan.json
- 4.58 MB  data\runs\20260913T033708Z-robot-f226be85\plan.json
- 4.58 MB  data\runs\20260913T033806Z-robot-1f3aab23\plan.json
- 4.56 MB  data\runs\20260913T033021Z-robot-6097ff9f\plan.json
- 4.55 MB  data\runs\20260913T033926Z-robot-18441f30\plan.json
- 4.51 MB  data\runs\20260913T033418Z-robot-3ca6fb45\plan.json
- 4.44 MB  data\runs\20260913T034043Z-robot-9658a349\plan.json
- 3.59 MB  data\runs\20260913T034043Z-robot-9658a349\report.json
- 3.1 MB  data\direct-motor-test.json
- 2.56 MB  data\commissioning\20260913T032812Z-maxima-0bbc895d\plan-before.json
- 2.56 MB  data\commissioning\20260913T032406Z-maxima-5bb71c66\plan-before.json
- 2.56 MB  data\commissioning\20260913T032303Z-maxima-1c0e428e\plan-before.json
- 2.56 MB  data\commissioning\20260913T032136Z-maxima-b3fb0f7b\plan-before.json
- 2.56 MB  data\photo-mount-direction-plan-20260912.json
- 2.56 MB  data\robot-commissioning-ready.json
- 2.56 MB  data\robot-commissioning-fixed.json
- 2.55 MB  data\commissioning\20260913T033921Z-maxima-9cd6b6f4\plan-before.json
- 2.55 MB  data\commissioning\20260913T033413Z-maxima-645a62f3\plan-before.json
- 2.55 MB  data\commissioning\20260913T034038Z-maxima-f1d1580f\plan-before.json
- 2.55 MB  data\recovery\runtime-ready-20260913T034456Z\plan-before.json
- 2.55 MB  data\commissioning\20260913T033801Z-maxima-a41ec004\plan-before.json
- 2.55 MB  data\commissioning\20260913T033703Z-maxima-8c8f8127\plan-before.json
- 2.55 MB  data\commissioning\20260913T024403Z-maxima-030bb8bb\plan-before.json
- 2.55 MB  data\commissioning\photo-br60-20260913T0312\previous-default-plan.json
- 2.55 MB  data\commissioning\20260913T024126Z-maxima-f2898a8f\plan-before.json
- 2.55 MB  data\real-robot-review-mobile-ik-20260912.json

### cart-plan-4s variants (size + hash)
- 35822 bytes  c85e1e373b5dfae7  data\cart-plan-4s-final.json
- 35822 bytes  8f400964a1b9d948  data\cart-plan-4s-fixed.json
- 35822 bytes  b868c1987da1fa7a  data\cart-plan-4s-guarded.json
- 35822 bytes  88b290465b9420da  data\cart-plan-4s-precise.json
- 35822 bytes  5218aabd2161e041  data\cart-plan-4s-priority.json
- 37824 bytes  2439a8f2f1afc01f  data\cart-plan-4s-reverse.json

### checked-plans
count=27 total=39.3 MB

### real-robot-review siblings
- 2.06 MB  data\real-robot-review-calibration-policy.json
- 2.08 MB  data\real-robot-review-final.json
- 2.06 MB  data\real-robot-review-geometry-calibration-final.json
- 2.06 MB  data\real-robot-review-geometry-revision-v2.json
- 2.06 MB  data\real-robot-review-geometry-revision.json
- 2.55 MB  data\real-robot-review-mobile-ik-20260912.json
- 2.55 MB  data\real-robot-review-mobile-ik-final-20260912.json
- 2.55 MB  data\real-robot-review-mobile-ik-run-local-20260912.json
- 2.08 MB  data\real-robot-review-plan.json
- 2.06 MB  data\real-robot-review-v2.json
- 0 MB  data\verification\real-robot-review-final-preflight.json
- 0 MB  data\verification\real-robot-review-geometry-calibration-final-preflight.json
- 0 MB  data\verification\real-robot-review-geometry-revision-preflight.json
- 0 MB  data\verification\real-robot-review-geometry-revision-v2-preflight.json
- 0 MB  data\verification\real-robot-review-preflight.json
- 0 MB  data\verification\real-robot-review-v2-preflight.json

### git-tracked size of data/
tracked files under data/: 945
