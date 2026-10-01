# The project format

## What is stored

Five things, in one SQLite file per workspace (`data/editor/projects.sqlite3`):

| Table | Holds |
| --- | --- |
| `projects` | The current state snapshot, its version, and the title |
| `operations` | The append-only log: every operation and the patch it produced |
| `events` | An audit trail of applied operations and truncations |
| `jobs` | Long work; VFX proposal rows persist request identity, full snapshot, conservative reservation and terminal result |
| `artifacts` | Rendered outputs, keyed by the node id that produced them |

The schema is an explicit `SCHEMA` string with `PRAGMA user_version`, following the
Director's storage discipline, and it refuses to initialise a database that belongs to
something else.

**The log is the truth; the snapshot is a cache.** `project.rebuild` folds the log and
compares the result against the stored snapshot. If they disagree, loading *fails* with the
project id and the log length rather than quietly preferring one. A project that cannot be
reconstructed from its own log is a project that cannot be trusted to render the same film
twice.

One transaction holds the operation, its patch, the new snapshot and the event. They commit
together or not at all.

A project created with a starting intent records `SET_INTENT` as its first operation and stores
that operation with the initial snapshot atomically. Reload, replay and unrelated undo therefore
retain the brief. Existing inconsistent journals still fail validation; loading does not repair
them silently.

VFX proposal reservation is a separate atomic transaction. The worker changes a request from
queued to running only when the current full project document still matches the reserved snapshot,
then releases SQLite before any provider call.

## The state document

```
ProjectState
├── project_id, version, phase, finalized
├── intent            prompt, target duration, aspect ratio, genre, emotion, pacing
├── media             {media_id: path, sha256, probe, proxy, thumbnail, waveform, source space}
├── analysis          {media_id: {analyzer_id: {version, result}}}
├── selection         {media_id: state, score, per-signal scores, reason}
├── timeline
│   ├── tracks        [{track_id, kind, clips:[...]}]
│   ├── transitions   [{from, to, effect, duration}]
│   └── markers       [{time, kind, strength}]
├── audio             [{kind, asset_id, timeline/source start, duration, gain, fades, ducks}]
└── render_settings   frame rate, master resolution, preview long edge, quality
```

`EditGraph` and the operation log are deliberately **not** fields of the state. The graph is
derived; the log is what produced the state and lives in its own table.

Media identity is the SHA-256 of the bytes, never the filename. Two copies of a take are the
same media; a re-export of it is not.

### Measured audio timing

Media probes can carry paired `audio_start_s` and `audio_duration_s` from the
first audio stream. The start is relative to the input seek origin, not its
absolute container timestamp. Video/container duration is not substituted for
audio duration. New music/SFX operations require measured timing and reject
spans outside that stream before journal append. Embedded original take sound
uses the existing recording/render path, unchanged by this selection rule.

Absent fields remain absent when older probe documents are replayed. Existing
audio journals and derivative receipts are preserved; legacy media with unknown
timing cannot acquire new standalone audio selections without a fresh measured
import in a new project. Duplicate legacy intake compares all recorded fields
and returns the existing receipt, without inventing historical measurements.

## Migration

`project.MIGRATIONS` is an ordered list of `(from_version, to_version, fn)`. Loading runs
every applicable step or refuses to load. There is no best-effort path: a project either
migrates completely or reports the version it cannot handle.

## Exports

**`.takeone.json`** (`export/native.py`) — state, the complete operation log, and the
artifact record. It is replayable: reloading folds the log and checks the stored state
against the fold, so a hand-edited or truncated file is caught at load rather than producing
a subtly different film.

**`.otio`** (`export/otio.py`) — OpenTimelineIO JSON, written directly. OTIO's on-disk form
is a small, stable, self-describing schema; writing it by hand keeps the editor
dependency-free and keeps the mapping from our timeline to theirs visible and reviewable.

OTIO has no native concept for a creative look, a speed curve or an effect stack. Those are
preserved under the `takeone` metadata key rather than silently dropped, and the file says so
in its own metadata. An exporter that quietly discards half the edit is worse than one that
declines to, because the loss is invisible until someone opens the result somewhere else.

**Master render** — the finished film at source resolution. A preview artifact is never
exported or reported as a master; they are different targets with different node ids.
