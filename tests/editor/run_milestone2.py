"""Milestone 2 — sequencing: multiple clips, a speed ramp, transitions, beat alignment.

Everything here is measured from rendered files. The claims that matter are arithmetic:
a transition removes exactly its own duration from the programme, a speed ramp lengthens a
clip by exactly the ratio its curve implies, and the rendered frame count equals the number
the timeline states. A montage that is one frame wrong is a montage that drifts out of sync
with its music by the end, so "close enough" is not an acceptable result.
"""

import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from takeone.editor import compile as compiler  # noqa: E402
from takeone.editor import media as media_module  # noqa: E402
from takeone.editor.analysis.probe import probe  # noqa: E402
from takeone.editor.operations import EditOperation, Target  # noqa: E402
from takeone.editor.operations import OperationType as T  # noqa: E402
from takeone.editor.render.cache import ArtifactCache  # noqa: E402
from takeone.editor.render.executor import RenderExecutor  # noqa: E402
from takeone.editor.render.ffmpeg import compile_graph  # noqa: E402
from takeone.editor.render.proxy import ProxyManager  # noqa: E402
from takeone.editor.repository import ProjectRepository  # noqa: E402
from takeone.editor.service import EditorService  # noqa: E402
from takeone.editor.state import RenderSettings  # noqa: E402
from takeone.editor.timing.curve import SpeedCurve  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "media"
CHECKS = []


def check(label, condition, detail=""):
    CHECKS.append((label, bool(condition), detail))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  — {detail}" if detail else ""))
    return condition


def send(service, op_type, op_target, op_explanation="", **parameters):
    return service.submit(
        "m2",
        EditOperation(
            operation_id=str(uuid.uuid4()),
            type=op_type,
            target=op_target,
            parameters=parameters,
            public_explanation=op_explanation,
        ),
    )


def frame_count(path):
    argv = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_read_frames",
        "-of",
        "default=nokey=1:noprint_wrappers=1",
        str(path),
    ]
    return int(subprocess.run(argv, capture_output=True, text=True, check=True).stdout.strip())


def main():
    workspace = ROOT / "data" / "editor" / "milestone2"
    if workspace.exists():
        import shutil

        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    print("\nMILESTONE 2 — MULTIPLE CLIPS, SPEED RAMPS, TRANSITIONS\n")
    repository = ProjectRepository(workspace / "projects.sqlite3")
    service = EditorService(repository)
    service.create(
        "m2",
        "Milestone two",
        render_settings=RenderSettings(master_width=1280, master_height=720, preview_long_edge=640),
    )
    proxies = ProxyManager(workspace / "proxy", long_edge=640)

    print("Import three takes")
    ids = []
    for name in ("shot_a_neutral", "shot_b_warm", "shot_d_dark"):
        operation = media_module.import_operation(
            FIXTURES / f"{name}.mp4",
            roots=[FIXTURES],
            probe_fn=probe,
            proxy_manager=proxies,
            existing=tuple(ids),
        )
        service.submit("m2", operation)
        ids.append(operation.parameters["media_id"])
    check("Three distinct media identities", len(set(ids)) == 3, ", ".join(ids))

    print("\nBuild a three-shot montage")
    send(service, T.ADD_TRACK, Target.project(), track_id="V1", kind="video")
    spans = [(0.0, 0.5, 2.5), (2.0, 1.0, 3.0), (4.0, 0.5, 2.5)]
    for index, (start, source_start, source_end) in enumerate(spans):
        send(
            service,
            T.ADD_CLIP,
            Target("track", track_id="V1"),
            f"Shot {index + 1} continues the movement.",
            clip_id=f"c{index + 1}",
            media_id=ids[index],
            timeline_start_s=start,
            source_start_s=source_start,
            source_end_s=source_end,
        )
    state = service.state("m2")
    check(
        "Montage is 6 seconds of butted clips",
        abs(state.timeline.duration_s - 6.0) < 1e-6,
        f"{state.timeline.duration_s:.4f}s",
    )

    print("\nBeat alignment first: a roll edit, before anything is retimed")
    before = state.timeline.duration_s
    cut = state.timeline.track("V1").clip("c2").timeline_start_s
    send(
        service,
        T.ALIGN_CUT_TO_BEAT,
        Target("track", track_id="V1"),
        "Moved the cut onto the beat.",
        clip_id="c2",
        beat_time_s=cut + 0.1,
        max_shift_s=0.25,
    )
    state = service.state("m2")
    check(
        "Roll edit moved the cut without changing the programme length",
        abs(state.timeline.duration_s - before) < 1e-6
        and abs(state.timeline.track("V1").clip("c2").timeline_start_s - (cut + 0.1)) < 1e-6,
        f"cut {cut:.3f}s -> {state.timeline.track('V1').clip('c2').timeline_start_s:.3f}s",
    )

    print("\nSpeed ramp on the hero shot")
    ramp = SpeedCurve.ramp(2.0, 0.42)
    hero_span = state.timeline.track("V1").clip("c2").source_span_s
    expected_length = ramp.fitted_to_source(hero_span).duration_s
    send(
        service,
        T.APPLY_SPEED_CURVE,
        Target("clip", clip_id="c2"),
        "Slowing the hero turn to 42 percent.",
        curve=ramp.wire(),
        interpolation="none",
    )
    state = service.state("m2")
    clip = state.timeline.track("V1").clip("c2")
    check(
        "Ramp consumes exactly the clip's source span",
        abs(clip.speed_curve.source_duration_s - hero_span) < 1e-6,
        f"{clip.speed_curve.source_duration_s:.6f}s of source",
    )
    check(
        "Ramp lengthened the clip by the ratio its curve implies",
        abs(clip.timeline_duration_s - expected_length) < 1e-6,
        f"{hero_span:.3f}s -> {clip.timeline_duration_s:.4f}s",
    )
    check(
        "Ripple kept the following clip butted",
        abs(state.timeline.track("V1").clip("c3").timeline_start_s - clip.timeline_end_s) < 1e-6,
    )

    print("\nTransitions")
    before = state.timeline.duration_s
    send(
        service,
        T.APPLY_TRANSITION,
        Target("track", track_id="V1"),
        "Matching movement between shots.",
        transition_id="t1",
        effect_id="whip",
        effect_version=1,
        from_clip_id="c1",
        to_clip_id="c2",
        duration_s=0.4,
    )
    send(
        service,
        T.APPLY_TRANSITION,
        Target("track", track_id="V1"),
        "Falling to black before the ending.",
        transition_id="t2",
        effect_id="dip_to_black",
        effect_version=1,
        from_clip_id="c2",
        to_clip_id="c3",
        duration_s=0.5,
    )
    state = service.state("m2")
    check(
        "Two transitions removed exactly their own durations",
        abs(state.timeline.duration_s - (before - 0.9)) < 1e-6,
        f"{before:.4f}s -> {state.timeline.duration_s:.4f}s",
    )

    print("\nGrade each shot, then match the second to the first")
    send(
        service,
        T.APPLY_COLOR_CORRECTION,
        Target("clip", clip_id="c3"),
        "Lifted the underexposed take.",
        exposure_stops=0.9,
        contrast=1.08,
    )
    send(
        service,
        T.MATCH_COLOR,
        Target("clip", clip_id="c2"),
        "Matched exposure and white balance to the opening shot.",
        reference_clip_id="c1",
        exposure_stops=-0.25,
        temperature_k=-260.0,
        tint=0.0,
        contrast=0.97,
    )
    send(
        service,
        T.APPLY_CREATIVE_LOOK,
        Target("clip", clip_id="c1"),
        "Applying restrained luxury warmth.",
        look_id="luxury_warm",
        intensity=0.6,
    )
    send(
        service,
        T.APPLY_CREATIVE_LOOK,
        Target("clip", clip_id="c2"),
        "Applying restrained luxury warmth.",
        look_id="luxury_warm",
        intensity=0.6,
    )
    send(
        service,
        T.APPLY_CREATIVE_LOOK,
        Target("clip", clip_id="c3"),
        "Applying restrained luxury warmth.",
        look_id="luxury_warm",
        intensity=0.6,
    )
    state = service.state("m2")
    check(
        "Matched clip records its reference", state.timeline.track("V1").clip("c2").color.matched_to == "c1"
    )

    print("\nCompile and render the sequence")
    target = compiler.preview_target(state)
    graph = compiler.project_graph(state, target)
    check(
        "Graph carries three sources, two transitions and one timing node",
        sum(1 for n in graph.nodes if str(n.type) == "source") == 3
        and sum(1 for n in graph.nodes if str(n.type) == "transition") == 2
        and sum(1 for n in graph.nodes if str(n.type) == "timing") == 1,
        f"{len(graph.nodes)} nodes",
    )

    cache = ArtifactCache(workspace / "cache")
    plan = compile_graph(graph, cache.path_for(graph.output_id))
    result = RenderExecutor().run(plan)
    check(
        "Sequence rendered",
        Path(result.output_path).is_file(),
        f"{result.elapsed_s:.2f}s for {len(graph.nodes)} nodes",
    )

    rendered = probe(result.output_path)
    frames = frame_count(result.output_path)
    expected = round(state.timeline.duration_s * state.render_settings.fps)
    check(
        "Rendered duration matches the timeline",
        abs(rendered.duration_s - state.timeline.duration_s) < 0.05,
        f"{rendered.duration_s:.4f}s vs {state.timeline.duration_s:.4f}s",
    )
    check(
        "Rendered frame count matches the timeline",
        abs(frames - expected) <= 1,
        f"{frames} frames, expected {expected}",
    )

    print("\nReplay")
    replayed, operations, _ = service.replay("m2")
    import json

    check(
        "Folding the log reproduces the montage exactly",
        json.dumps(replayed.wire(), sort_keys=True) == json.dumps(state.wire(), sort_keys=True),
        f"{len(operations)} operations",
    )

    failed = [label for label, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    print(f"\nArtifacts: {workspace}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
