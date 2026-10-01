# TAKE ONE · Extensible Asset Library Kit

An additive starting implementation for C:\TakeOne. Prepared 15 September 2026.

**This archive contains working importer/catalog code, a Three.js loader and
independent preview-browser source, and a scene-dressing integration handoff.
It does not contain downloaded third-party models. It has not modified your
Windows folder, and does not automatically wire the new assets into the Director
or Shot Studio.** The current local working tree was unavailable; the connected
GitHub main snapshot was inspected instead and appears behind the local upgrade.

## Install into your existing checkout

Extract the archive, open PowerShell in the directory containing install.py, then:

```powershell
& "C:\TakeOne\.venv\Scripts\python.exe" .\install.py --root "C:\TakeOne" --download-starter
```

This adds only new payload files. All destination conflicts are checked before
writing; a different existing file stops the install instead of being overwritten.
It does not change hardware, calibration, firmware, environments, requirements,
existing scenes.py, scene-library.js, AGENTS.md, README.md or any current skill.
There are no purchases or paid API calls. --download-starter explicitly requests
the four free Kenney packs configured in packs.json. Downloads run locally and
may require considerable disk space. Per ZIP limits are 512 MiB compressed and
2 GiB expanded. Live provider downloads were not possible in the authoring
sandbox, so current ZIP discovery still needs a real local test.

Omit --download-starter to install code without network activity. The downloader
uses the existing project's installed takeone package, normally editable through
its .venv. A missing project runtime is an error, not an automatic dependency or
hardware setup action.

## Search, verify and preview

```powershell
& "C:\TakeOne\.venv\Scripts\python.exe" -m takeone.asset_library --root "C:\TakeOne" search "chair"
& "C:\TakeOne\.venv\Scripts\python.exe" -m takeone.asset_library --root "C:\TakeOne" search "person" --kind character
& "C:\TakeOne\.venv\Scripts\python.exe" -m takeone.asset_library --root "C:\TakeOne" verify
```

With the existing simulator running, open:
http://127.0.0.1:8766/asset-library/browser.html

This is a NEW, independent browser, not a claim that models already appear in
Shot Studio. Its vendor import paths match the inspected repository; the current
local server and browser behavior still require verification. Required compressed
extensions are refused unless their matching loaders are explicitly configured.
The model browser loads one selected asset rather than the entire library.

If a provider changes its website, download that specific free ZIP from its
official source and import it through the same checked pipeline:

```powershell
& "C:\TakeOne\.venv\Scripts\python.exe" -m takeone.asset_library --root "C:\TakeOne" import-zip "$env:USERPROFILE\Downloads\kenney_furniture-kit.zip" --pack kenney-furniture --confirm-license
```

The filename is an example; use the actual downloaded filename. Other CC0 packs
can be added to configs/asset-library/packs.json and imported the same way. Only
GLB/glTF and their allowed dependent files are published. This is not a universal
FBX/OBJ/BLEND converter; export those through Blender first. Nothing executes
scripts found inside a model pack. An unsuccessful import never fabricates assets.

## What gets added

```
packages/takeone/asset_library/                  Python catalog and importer
apps/rehearsal/dist/asset-library/               Generic loader and preview browser
configs/asset-library/packs.json                Extensible curated source data
packages/takeone/director/scene-dressing/SKILL.md New directing guidance, not yet loaded
docs/ai-director/implementation/08-asset-library-integration.md
```

Successful imports additionally create catalog.json and immutable packs/ snapshots
under apps/rehearsal/dist/asset-library/. That dist directory is authored source in
this project: do not delete it as a build cache. Keep large third-party binaries
out of normal git history unless intentionally using suitable LFS/storage policy.
The toolkit does not modify .gitignore or configure Git LFS for you.

## Complete the app integration

Read the installed integration handoff and LOCAL-INTEGRATION-PROMPT.md. They map
the next changes to the existing Director schema, scene conversion, renderer
cleanup, timing, measured-world distinction and tests. The source registry is
implemented; LLM tool registration, schema migration, scene placement constraints,
existing cast-rig retargeting and full Studio integration are not implemented here.

The recipe in examples/ensemble-scene-recipe.json explains richer coverage and
independent supporting performances. It contains queries to resolve, not invented
asset IDs. It is NOT a ready-to-run production script or hardware plan.

## Verification performed here

32 Python tests passed; seven Node lifecycle tests passed. Python compilation and
browser-module syntax checks passed. Fixture ZIPs/models were authored test data;
the downloader's network was mocked. No third-party asset was downloaded, no
WebGL model was rendered, and no production-wide Windows, MuJoCo, browser, or
hardware test was run. See VERIFICATION.md and evidence/ for exact scope/logs.

Run this kit's isolated tests with Python and Node from this directory:

```text
python -m unittest discover -s tests -v
node --test tests/lifecycle.test.mjs
```

After integrating in the real project, run its actual full verifier:

```powershell
Set-Location C:\TakeOne
.\scripts\TakeOne.ps1 -Command test
```

A passed importer test does not establish that a real chair is at a measured mark,
that a skeletal clip matches a human cue, or that the rig has safe clearance.
