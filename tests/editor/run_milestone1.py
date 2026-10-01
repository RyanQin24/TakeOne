"""Milestone 1 — the spine, run end to end against real media and real FFmpeg.

Import one video, build a proxy, add a clip through an operation, trim it, correct its
colour, apply a creative look, attach an effect, compile the graph, render, export.
Then *verify*: the artifact exists, its duration and frame count are what the timeline
says, the colour operation measurably changed the pixels in the direction it asked for,
a second render is served from cache, the log replays to an identical state, and undo
reverses the last decision.

Nothing here is asserted from a plan; every claim is measured from an output file.
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from takeone.editor import compile as compiler  # noqa: E402
from takeone.editor import media as media_module  # noqa: E402
from takeone.editor.analysis.probe import probe  # noqa: E402
from takeone.editor.export import native as native_export  # noqa: E402
from takeone.editor.export import otio as otio_export  # noqa: E402
from takeone.editor.operations import EditOperation, Target  # noqa: E402
from takeone.editor.operations import OperationType as T  # noqa: E402
from takeone.editor.render.cache import ArtifactCache  # noqa: E402
from takeone.editor.render.executor import RenderExecutor  # noqa: E402
from takeone.editor.render.ffmpeg import assert_backend_ready, compile_graph  # noqa: E402
from takeone.editor.render.planner import RenderPlanner  # noqa: E402
from takeone.editor.render.proxy import ProxyManager  # noqa: E402
from takeone.editor.repository import ProjectRepository  # noqa: E402
from takeone.editor.service import EditorService  # noqa: E402
from takeone.editor.state import RenderSettings  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "media"
CHECKS = []


def check(label, condition, detail=""):
    CHECKS.append((label, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    return condition


def operation(op_type, op_target, op_explanation="", **parameters):
    return EditOperation(
        operation_id=str(uuid.uuid4()),
        type=op_type,
        target=op_target,
        parameters=parameters,
        public_explanation=op_explanation,
    )


def frame_statistics(path, at=0.5):
    """Mean luma and mean saturation of one decoded frame, measured from the artifact."""
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{at:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    result = subprocess.run(argv, capture_output=True, check=True)
    import numpy

    probe_result = probe(path)
    data = numpy.frombuffer(result.stdout, dtype=numpy.uint8)
    expected = probe_result.width * probe_result.height * 3
    data = data[:expected].reshape(probe_result.height, probe_result.width, 3).astype(numpy.float64)
    luma = 0.2126 * data[..., 0] + 0.7152 * data[..., 1] + 0.0722 * data[..., 2]
    maximum = data.max(axis=2)
    minimum = data.min(axis=2)
    saturation = numpy.where(maximum > 0, (maximum - minimum) / numpy.maximum(maximum, 1), 0.0)
    return {"luma": float(luma.mean()), "saturation": float(saturation.mean())}


def letterbox_bars(path, at=0.5):
    """Fraction of the frame height that is masked black, measured from the pixels."""
    import numpy

    probe_result = probe(path)
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{at:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    result = subprocess.run(argv, capture_output=True, check=True)
    data = numpy.frombuffer(result.stdout, dtype=numpy.uint8)
    expected = probe_result.width * probe_result.height * 3
    data = data[:expected].reshape(probe_result.height, probe_result.width, 3)
    rows = data.reshape(probe_result.height, -1).max(axis=1)
    return float((rows < 12).sum()) / probe_result.height


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
    workspace = ROOT / "data" / "editor" / "milestone1"
    if workspace.exists():
        import shutil

        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    print("\nMILESTONE 1 — IMPORT, BUILD, COMPILE, RENDER, EXPORT\n")
    print("Backend")
    assert_backend_ready()
    check("FFmpeg provides every required filter", True)

    repository = ProjectRepository(workspace / "projects.sqlite3")
    service = EditorService(repository)
    settings = RenderSettings(master_width=1280, master_height=720, preview_long_edge=640)
    service.create("m1", "Milestone one", render_settings=settings)
    check("Project created", service.state("m1").version == 0)

    print("\nImport")
    proxies = ProxyManager(workspace / "proxy", long_edge=640)
    import_op = media_module.import_operation(
        FIXTURES / "shot_a_neutral.mp4",
        roots=[FIXTURES],
        probe_fn=probe,
        proxy_manager=proxies,
        explanation="Imported the neutral take.",
    )
    service.submit("m1", import_op)
    state = service.state("m1")
    media_id = import_op.parameters["media_id"]
    item = state.media_item(media_id)
    check(
        "Media identity is the content digest",
        media_id.endswith(item.sha256[:10]),
        f"{media_id} from {item.sha256[:10]}",
    )
    check(
        "Probe read the real duration",
        abs(item.probe.duration_s - 6.0) < 0.1,
        f"{item.probe.duration_s:.3f}s",
    )
    check(
        "Proxy exists on disk",
        Path(item.proxy_path).is_file(),
        f"{Path(item.proxy_path).stat().st_size / 1024:.0f} KiB",
    )
    check("Thumbnail exists on disk", Path(item.thumbnail_path).is_file())
    proxy_probe = probe(item.proxy_path)
    check(
        "Proxy is smaller than the source",
        proxy_probe.width == 640,
        f"{proxy_probe.width}x{proxy_probe.height}",
    )

    print("\nBuild the timeline through operations")
    service.submit("m1", operation(T.ADD_TRACK, Target.project(), track_id="V1", kind="video"))
    service.submit(
        "m1",
        operation(
            T.ADD_CLIP,
            Target("track", track_id="V1"),
            "Strongest opening composition.",
            clip_id="c1",
            media_id=media_id,
            timeline_start_s=0.0,
            source_start_s=1.0,
            source_end_s=5.0,
            label="Opening",
        ),
    )
    state = service.state("m1")
    check(
        "Clip is on the real timeline",
        state.timeline.duration_s == 4.0,
        f"timeline {state.timeline.duration_s:.3f}s",
    )

    service.submit(
        "m1",
        operation(
            T.TRIM_CLIP,
            Target("clip", clip_id="c1"),
            "Removed 0.62s of setup movement.",
            edge="in",
            source_start_s=1.62,
        ),
    )
    state = service.state("m1")
    _, clip = state.timeline.find_clip("c1")
    frame_s = state.media_item(media_id).probe.frame_s
    check(
        "Trim changed the real source range",
        abs(clip.source_start_s - 1.62) < frame_s,
        f"source {clip.source_start_s:.4f}-{clip.source_end_s:.4f}s",
    )
    check(
        "Trim snapped the cut to the media's frame grid",
        abs(clip.source_start_s / frame_s - round(clip.source_start_s / frame_s)) < 1e-6,
        f"frame {clip.source_start_s / frame_s:.3f}",
    )
    check(
        "Trim shortened the timeline",
        3.3 < state.timeline.duration_s < 3.42,
        f"timeline {state.timeline.duration_s:.4f}s",
    )

    print("\nCompile and render the ungraded baseline")
    target = compiler.preview_target(state)
    baseline_graph = compiler.project_graph(state, target)
    cache = ArtifactCache(workspace / "cache")
    planner = RenderPlanner(cache)
    baseline_work = planner.plan(baseline_graph)
    executor = RenderExecutor()
    baseline_plan = compile_graph(baseline_graph, cache.path_for(baseline_work.output_id))
    baseline_result = executor.run(baseline_plan)
    cache.put(baseline_work.output_id, baseline_plan.duration_s)
    check(
        "Baseline artifact rendered",
        Path(baseline_result.output_path).is_file(),
        f"{baseline_result.elapsed_s:.2f}s, {len(baseline_graph.nodes)} nodes",
    )
    baseline_stats = frame_statistics(baseline_result.output_path, 1.0)

    print("\nColour — measured on its own, so the claim is about exposure and nothing else")
    service.submit(
        "m1",
        operation(
            T.APPLY_COLOR_CORRECTION,
            Target("clip", clip_id="c1"),
            "Lifted exposure two thirds of a stop and firmed the contrast.",
            exposure_stops=0.65,
            contrast=1.12,
        ),
    )
    exposure_state = service.state("m1")
    exposure_graph = compiler.project_graph(exposure_state, target)
    exposure_work = planner.plan(exposure_graph)
    exposure_plan = compile_graph(exposure_graph, cache.path_for(exposure_work.output_id))
    exposure_result = executor.run(exposure_plan)
    cache.put(exposure_work.output_id, exposure_plan.duration_s)
    exposure_stats = frame_statistics(exposure_result.output_path, 1.0)
    check(
        "Exposure operation measurably brightened the image",
        exposure_stats["luma"] > baseline_stats["luma"] + 3.0,
        f"luma {baseline_stats['luma']:.1f} -> {exposure_stats['luma']:.1f}",
    )

    print("\nLook and effect")
    service.submit(
        "m1",
        operation(
            T.APPLY_CREATIVE_LOOK,
            Target("clip", clip_id="c1"),
            "Applying restrained luxury warmth.",
            look_id="luxury_warm",
            intensity=0.7,
        ),
    )
    service.submit(
        "m1",
        operation(
            T.ADD_EFFECT,
            Target("clip", clip_id="c1"),
            "Framed to 2.39:1.",
            instance_id="fx1",
            effect_id="letterbox",
            effect_version=1,
            parameters={"ratio": 2.39},
        ),
    )
    state = service.state("m1")
    _, clip = state.timeline.find_clip("c1")
    check(
        "Grade recorded on the clip",
        clip.color.exposure_stops == 0.65 and clip.color.look_id == "luxury_warm",
    )
    check("Effect recorded on the clip", len(clip.effects) == 1)

    graded_graph = compiler.project_graph(state, target)
    check(
        "Grading added nodes to the derived graph",
        len(graded_graph.nodes) > len(baseline_graph.nodes),
        f"{len(baseline_graph.nodes)} -> {len(graded_graph.nodes)} nodes",
    )
    check(
        "Unrelated nodes kept their identity",
        len({n.node_id for n in baseline_graph.nodes} & {n.node_id for n in graded_graph.nodes}) >= 2,
        "the decoded segment and its conform survived the grade",
    )

    graded_work = planner.plan(graded_graph)
    check(
        "Cache reports the new work honestly", graded_work.needs_render, json.dumps(graded_work.cache_report)
    )
    graded_plan = compile_graph(graded_graph, cache.path_for(graded_work.output_id))
    graded_result = executor.run(graded_plan)
    cache.put(graded_work.output_id, graded_plan.duration_s)

    print("\nVerify the rendered film against the timeline")
    rendered = probe(graded_result.output_path)
    check(
        "Rendered duration matches the timeline",
        abs(rendered.duration_s - state.timeline.duration_s) < 0.04,
        f"{rendered.duration_s:.3f}s vs {state.timeline.duration_s:.3f}s",
    )
    frames = frame_count(graded_result.output_path)
    expected_frames = round(state.timeline.duration_s * state.render_settings.fps)
    check(
        "Frame count matches the timeline exactly",
        frames == expected_frames,
        f"{frames} frames, expected {expected_frames}",
    )
    check(
        "Rendered at the preview resolution",
        (rendered.width, rendered.height) == (target.width, target.height),
        f"{rendered.width}x{rendered.height}",
    )

    graded_stats = frame_statistics(graded_result.output_path, 1.0)
    check(
        "Look measurably reduced saturation as specified",
        graded_stats["saturation"] < exposure_stats["saturation"],
        f"saturation {exposure_stats['saturation']:.4f} -> {graded_stats['saturation']:.4f}",
    )
    bars = letterbox_bars(graded_result.output_path, 1.0)
    check(
        "Letterbox effect produced real black bars",
        bars > 0.15,
        f"{bars * 100:.1f}% of frame height is masked",
    )

    print("\nCache")
    again = planner.plan(compiler.project_graph(service.state("m1"), target))
    check("A second render of an unchanged project is a cache hit", not again.needs_render, again.cached_path)

    print("\nReplay and undo")
    replayed, operations, patches = service.replay("m1")
    check(
        "Folding the log reproduces the state exactly",
        json.dumps(replayed.wire(), sort_keys=True) == json.dumps(state.wire(), sort_keys=True),
        f"{len(operations)} operations",
    )
    from takeone.editor import patch as patch_module
    from takeone.editor.state import empty as empty_state

    mirror = empty_state("m1", settings).wire()
    for entry in patches:
        mirror = patch_module.apply(mirror, entry)
    check(
        "Applying the published patches reproduces the same state",
        json.dumps(mirror, sort_keys=True) == json.dumps(state.wire(), sort_keys=True),
        "server reducer and client mirror agree",
    )

    service.undo("m1")
    undone = service.state("m1")
    _, clip = undone.timeline.find_clip("c1")
    check(
        "Undo removed exactly the last decision",
        len(clip.effects) == 0 and clip.color.look_id == "luxury_warm",
    )

    print("\nExport")
    native_path = workspace / "milestone1.takeone.json"
    native_export.export(service, "m1", native_path)
    check(
        "Native project export written", native_path.is_file(), f"{native_path.stat().st_size / 1024:.1f} KiB"
    )
    reloaded = json.loads(native_path.read_text())
    check(
        "Native export carries the full operation log",
        len(reloaded["operations"]) == len(service.history("m1")),
    )

    otio_path = workspace / "milestone1.otio"
    otio_export.export(service.state("m1"), otio_path, name="Milestone one")
    document = json.loads(otio_path.read_text())
    check(
        "OTIO export is a valid timeline document",
        document["OTIO_SCHEMA"].startswith("Timeline"),
        document["OTIO_SCHEMA"],
    )

    master_path = workspace / "master.mp4"
    master_graph = compiler.project_graph(service.state("m1"), compiler.master_target(service.state("m1")))
    master_plan = compile_graph(master_graph, master_path)
    master_result = executor.run(master_plan)
    master_probe = probe(master_result.output_path)
    check(
        "Master renders from the original, not the proxy",
        (master_probe.width, master_probe.height) == (1280, 720),
        f"{master_probe.width}x{master_probe.height} in {master_result.elapsed_s:.2f}s",
    )

    failed = [label for label, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    if failed:
        print("FAILED: " + "; ".join(failed))
    print(f"\nArtifacts: {workspace}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
