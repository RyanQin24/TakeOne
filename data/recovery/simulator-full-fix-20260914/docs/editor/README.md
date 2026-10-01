# TAKE ONE Editor — documentation

| Document | What it covers | State |
| --- | --- | --- |
| [architecture.md](architecture.md) | The design of record: layers, data flow, schemas, risks, implementation order, and every place this design departs from the originating specification and why | current |
| [edit-operations.md](edit-operations.md) | The operation log: types, targets, parameters, and the rules the reducer enforces | built |
| [edit-graph.md](edit-graph.md) | Node types, content addressing, validation, and why the graph is derived rather than stored | built |
| [render-engine.md](render-engine.md) | Planner / compiler / executor, the artifact cache, proxies, and the safety rules around FFmpeg | built |
| [effect-system.md](effect-system.md) | The twenty-four primitives, the looks built from them, and transitions as two-input effects | built |
| [adding-an-effect.md](adding-an-effect.md) | How to add a primitive or a look without reading the rest of the repository | built |
| [project-format.md](project-format.md) | The project schema, the `.takeone.json` export, OTIO output, and migration | built |
| [ui-design-system.md](ui-design-system.md) | Tokens, layout, motion rules, and the one-reducer contract the interface follows | built |
| [integrating-with-the-rehearsal-server.md](integrating-with-the-rehearsal-server.md) | The exact addition that mounts the editor on the existing app server | ready to apply |
| template-system.md | Templates as parameterised operation programs | milestone 2 |
| ai-editor.md | Orchestrator, planners, schemas, and the explanation contract | milestone 4 |
| robot-metadata.md | `RobotMetadataAdapter` and the signals it contributes | milestone 5 |

The three documents at the bottom are named here because the architecture commits to them,
not because they exist. Writing them before their subsystems would describe software that
does not run.

## Verifying the editor

```powershell
# Hermetic: no media, no FFmpeg, no network.
python -m unittest discover -s tests/editor -p "test_*.py" -t tests/editor

# Real media, real FFmpeg. Builds its fixtures on first run.
python tests/editor/run_milestone1.py     # import -> build -> grade -> render -> export
python tests/editor/run_milestone2.py     # montage, ramps, transitions, colour matching
python tests/editor/run_api_check.py      # the HTTP surface, including SSE and byte ranges
```

## Running it

```powershell
python -m takeone.editor.cli doctor        # is the render backend usable here?
python -m takeone.editor.cli effects       # what is installed
python -m takeone.editor.cli serve --media-root C:\TakeOne\data\takes
```

Then `npm install && npm run dev` in `apps/editor`, or `npm run build` and point
`--static` at `apps/editor/dist`.

Drop clips on the launch screen. Each film stores originals in
`data/editor/library/{project_id}/media/`. The heuristic editor then analyses, selects,
cuts, grades and finishes the film as a paced stream of operations — watch the AI tab
and the timeline while it works. A second drop in the media bin still places a take
manually.
