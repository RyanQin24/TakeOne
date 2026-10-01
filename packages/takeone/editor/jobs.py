"""Long work runs in a bounded pool so the interface never waits on FFmpeg.

Analysis, proxy generation and rendering all take seconds to minutes. None of them may
block a request, and none may be started twice for the same work: a job is keyed by the
content address of what it produces, so asking for the same render twice joins the job in
flight rather than starting a second FFmpeg.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from .errors import EditorError
from .project import now_utc
from .render.executor import RenderExecutor
from .render.ffmpeg import compile_graph

MAX_WORKERS = 2
MAX_RECORDS = 200


class JobPool:
    def __init__(self, max_workers=MAX_WORKERS):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="editor-job")
        self._lock = threading.Lock()
        self._records = {}
        self._by_output = {}
        self._executors = {}
        self._order = []
        self._proposal_slots = threading.BoundedSemaphore(max_workers)

    # -- records -----------------------------------------------------------

    def _record(self, job_id, **changes):
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            record.update(changes)
            record["updated_utc"] = now_utc()
            return dict(record)

    def get(self, job_id):
        with self._lock:
            record = self._records.get(job_id)
            return dict(record) if record else None

    def list(self, project_id=None):
        with self._lock:
            records = [dict(item) for item in self._records.values()]
        if project_id:
            records = [item for item in records if item["project_id"] == project_id]
        return sorted(records, key=lambda item: item["created_utc"], reverse=True)

    def cancel(self, job_id):
        with self._lock:
            executor = self._executors.get(job_id)
        if executor is None:
            raise EditorError(f"Job '{job_id}' is not running")
        executor.cancel()
        return self._record(job_id, status="CANCELLED", stage="cancelled")

    def _prune(self):
        while len(self._order) > MAX_RECORDS:
            stale = self._order.pop(0)
            self._records.pop(stale, None)
            self._executors.pop(stale, None)

    # -- render ------------------------------------------------------------

    def submit(self, project_id, kind, graph, work, cache, service):
        """Start, or join, the render that produces this output node."""
        output_id = work.output_id
        with self._lock:
            existing = self._by_output.get(output_id)
            if existing and self._records.get(existing, {}).get("status") in ("QUEUED", "RUNNING"):
                return dict(self._records[existing])
            job_id = str(uuid.uuid4())
            stamp = now_utc()
            self._records[job_id] = {
                "job_id": job_id,
                "project_id": project_id,
                "kind": f"render:{kind}",
                "status": "QUEUED",
                "progress": 0.0,
                "stage": "queued",
                "output_id": output_id,
                "node_count": len(work.nodes),
                "error": None,
                "artifact": None,
                "created_utc": stamp,
                "updated_utc": stamp,
            }
            self._by_output[output_id] = job_id
            self._order.append(job_id)
            self._prune()
        self._pool.submit(self._run_render, job_id, project_id, kind, graph, work, cache, service)
        return self.get(job_id)

    def _run_render(self, job_id, project_id, kind, graph, work, cache, service):
        def on_progress(update):
            self._record(job_id, progress=update.get("progress", 0.0), stage=update.get("stage", "render"))

        executor = RenderExecutor(on_progress=on_progress)
        with self._lock:
            self._executors[job_id] = executor
        self._record(job_id, status="RUNNING", stage="compiling")
        try:
            plan = compile_graph(graph, cache.path_for(work.output_id))
            self._record(job_id, stage="render")
            result = executor.run(plan)
            entry = cache.put(work.output_id, plan.duration_s)
            service.repository.record_artifact(
                project_id,
                work.output_id,
                kind,
                entry.path,
                entry.bytes,
                entry.duration_s,
                now_utc(),
            )
            self._record(
                job_id,
                status="COMPLETED",
                progress=1.0,
                stage="complete",
                artifact=entry.path,
                elapsed_s=round(result.elapsed_s, 3),
            )
        except EditorError as error:
            self._record(job_id, status="FAILED", stage="failed", error=error.wire())
        except Exception as error:  # noqa: BLE001 - a job must never take the server down
            self._record(
                job_id,
                status="FAILED",
                stage="failed",
                error={"stage": "render", "code": "unexpected", "message": str(error)},
            )
        finally:
            with self._lock:
                self._executors.pop(job_id, None)

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def submit_proposal(self, work):
        """Bound provider jobs including queued work; never grow an unbounded queue."""
        if not self._proposal_slots.acquire(blocking=False):
            raise EditorError("The proposal job pool is full")
        try:
            future = self._pool.submit(work)
        except BaseException:
            self._proposal_slots.release()
            raise
        future.add_done_callback(lambda _: self._proposal_slots.release())
        return future
