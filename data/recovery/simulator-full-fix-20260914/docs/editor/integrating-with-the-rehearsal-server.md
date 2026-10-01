# Mounting the editor on the existing app server

The editor runs standalone today (`python -m takeone.editor.cli serve`), and this change is
what puts it on the same port and the same page set as the Director and the rehearsal
simulator. It was written but **not applied**: `apps/rehearsal/server.py` is under active
change, and a merge collision there is worse than a one-minute edit made deliberately.

Everything the change needs already exists in `apps/rehearsal/editor_http.py`, which owns the
Server-Sent Events framing, byte-range media delivery and the error-to-status mapping, so the
addition to `server.py` is a mount rather than a rewrite.

## The change

**1. Imports** — add beside the existing Director and Voice imports:

```python
from takeone.editor.api import EditorAPI
from takeone.editor.jobs import JobPool
from takeone.editor.repository import ProjectRepository as EditorRepository
from takeone.editor.service import EditorService

from editor_http import EditorRoutes           # same directory as server.py
```

**2. `Handler.do_GET`** — first branch, before the Director and Voice branches:

```python
        if path.startswith("/api/editor/"):
            if self.server.editor.handle_get(self, path, parse_qs(urlparse(self.path).query)):
                return None
```

**3. `Handler.do_POST`** — the editor's own bodies can be large (an imported operation
carries a probe), so extend the size table and add the route:

```python
            elif path.startswith("/api/editor/"):
                limit = 262144
```

and, beside the Director and Voice POST branches:

```python
        if path.startswith("/api/editor/"):
            if self.server.editor.handle_post(self, path, body):
                return None
```

Also add `"/api/editor/"` to the prefix tuple in the "Not found" guard, so editor POSTs are
not rejected before they reach the route.

**4. `make_server`** — construct it alongside the Director service:

```python
        editor_workspace = DATA / "editor"
        editor_service = EditorService(EditorRepository(editor_workspace / "projects.sqlite3"))
        server.editor_jobs = JobPool()
        server.editor = EditorRoutes(
            EditorAPI(editor_service, editor_workspace,
                      media_roots=[DATA / "takes"], jobs=server.editor_jobs)
        )
```

**5. `RehearsalServer.server_close`** — shut the pool down with the server:

```python
        if getattr(self, "editor_jobs", None) is not None:
            self.editor_jobs.close()
```

## Notes on the seams

**Streaming and `ThreadingHTTPServer`.** The stream holds one thread per open editor for as
long as the page is open. `ThreadingHTTPServer` already spawns a thread per request, so this
costs one thread per editor tab and nothing else; the subscription queue is bounded and a
slow reader is dropped rather than allowed to back-pressure the editor.

**Local-only.** Editor routes must sit *after* `local_request_error()` in both methods, as
the Director and Voice routes do. The standalone server enforces the same rule itself.

**The static interface.** `apps/editor/dist` is a Vite build. Either serve it from
`apps/rehearsal/dist/editor/` by copying the build output, or run the editor standalone with
`--static apps/editor/dist`. Do not treat `apps/rehearsal/dist` as build output: those files
are authored source.

**`pyproject.toml`.** The editor adds no runtime dependency — it is standard library only.
The measurement helpers in `tests/editor/run_milestone1.py` use NumPy, which is already in
the `simulation` extra. To get the command on the path, add to `[project.scripts]`:

```toml
takeone-edit = "takeone.editor.cli:main"
```

**What this does not do.** Mounting the editor does not connect it to the Director's session
state. `Phase.EDITING` and the `prepare_edit` action already exist in the Director's FSM, and
the bridge between them belongs in milestone 4 with the planner — a Director session that
claims an edit exists before the planner can produce one would be a lie in the product's own
state machine.
