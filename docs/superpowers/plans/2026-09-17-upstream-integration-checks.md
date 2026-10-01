# Upstream integration checks implementation plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Track steps with checkboxes.

**Goal:** Clear the exact lint/format failures inherited from Caesar's new main
and repair its reproduced provider-schema regression, before publishing the
next editor batch. Preserve legacy scene documents and new production design.

**Architecture:** Keep the current modules and interfaces. This is mechanical
cleanup on the integrated editor worktree, not a rewrite or director redesign.

**Tech stack:** Existing Python, Ruff, unittest and git.

**Spec:** Root `AGENTS.md`, root README maintained-source conventions, Basil's
standing requirement to repair observed lint/test failures and preserve team
work. Incoming main commit is `c5146d5`; editor integration commit `24ed6d4`.

## Global constraints

- Preserve new director, perception, embodied and production-design behavior.
- No hardware, cloud or paid calls. Do not alter calibration or dependencies.
- No em dash, co-author trailers, CHANGELOG edits or generated-file edits.
- Only the editor worktree is writable. The root director branch is owned by
  its active no-mistakes publishing run and must not be edited or reset.
- Keep every semantically meaningful expression, including dictionary lookup
  evaluation currently assigned to an unused local. No unsafe Ruff fix sweep.
- Do not run the full product suite; controller is doing that independently.

## Task 1: Mechanical inherited Python cleanup

**Files:** Existing Python files reported by Ruff under `packages/takeone`,
`tests`, `scripts`, and only those. No new production module or test scaffold.

**Interfaces:** All function signatures, runtime behavior and public data stay
unchanged. The baseline is five lint errors and 23 files needing formatting.

- [x] Reproduce the exact failures:

  ```sh
  .venv/bin/ruff check packages/takeone tests scripts --output-format concise
  .venv/bin/ruff format --check packages/takeone tests scripts
  ```

- [x] Apply only the reported safe import cleanup/sorting and rename the
  unused local in `director/skills.py`, preserving evaluation in both branches:

  ```python
  template_id, _light_role = "static", "key"
  template_id, _light_role = resolved["template_id"], resolved["light_role"]
  ```

  Safe import issues are unused `dataclasses.field` in
  `director/production_design/contracts.py`, unused `production_design_schema`
  import in `director/provider.py`, import order in `director/studio.py`, and
  unused `copy` in `scripts/cinematic_motif_showcase.py`. Inspect that removed
  imports have no required initialization effect. Use apply_patch for edits;
  Ruff formatting is allowed for the reported 23 files only.

- [x] Compare parsed Python ASTs against the pre-task commit, excluding only
  the explicitly reviewed import edits and `_light_role` local rename. Record
  any other AST change as a defect and correct it before proceeding.
- [x] Rerun both Ruff commands, `git diff --check`, and these focused behavior
  regressions using the existing virtual environment:

  ```sh
  .venv/bin/python -m unittest tests.test_cinematic_motifs tests.test_session_context.PersonaTests tests.test_production_design -q
  ```

  Do not hide a test failure or change assertions just to pass. Report behavior
  failures to the controller without expanding this mechanical task.
- [x] Self-review and commit only the mechanical code changes. Preserve the
  controller's plan/docs. Write exact commands, exit statuses, test counts and
  AST comparison to the task report; return commit/status/concerns. No push.

## Task 2: Restore strict provider schema and preserve legacy scenes

**Files:** `packages/takeone/director/scenes.py`, its schema call site in
`creative.py`, focused director tests.

**Evidence:** The exact rebased PR head ran 926 product tests with two failures:
strict-schema tests in `tests/test_director_script_bridge.py` and
`tests/test_shot_design.py`. Both find `production_role` in properties but not
required. New main adds this metadata and unconditionally removes it from
the required list. `plan_schema(require_movement=True)` is sent with strict
structured output, whereas legacy acceptance intentionally allows omissions.

- [x] Reproduce from the user-facing planning API or its real provider-request
  boundary with an injected validating transport and no paid call. Also run
  both existing failing tests before changing production code. Trace the
  creative-plan request to the actual nested schema, not a duplicated schema.
- [x] Add the smallest regression that proves strict new generation and
  acceptance of legacy scene objects without `production_role`. Preserve
  explicit production roles. No test assertion weakening.
- [x] Correct the schema at its origin, keeping metadata additive for legacy
  acceptance and the strict generation schema valid. Do not redesign scene
  production, change model configuration, remove metadata, or modify fixtures
  merely to hide a regression. Update built-in authored samples only if the
  corrected generation contract demonstrably requires it.
- [x] Run all tests in `tests.test_director_script_bridge`,
  `tests.test_shot_design`, `tests.test_scenes`, and `tests.test_production_design`
  if present, plus affected provider/planning tests and full Ruff checks.
  Controller owns the full verification run separately.
- [x] Commit only the reviewed-scope fix/tests. Record RED/GREEN, exact
  commands, counts and API/request reproduction in task report. No push.

Result: `69e26e8` mechanical cleanup and `917c7ed` strict-schema repair pass
independent task reviews. 52 focused director/provider tests pass; controller
rerun of the two original failures passes. Current integrated full verification
is separate and pending; no whole-repository green claim from focused tests.
