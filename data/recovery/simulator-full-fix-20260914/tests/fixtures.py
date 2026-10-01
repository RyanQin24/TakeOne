"""Synthetic clips with KNOWN camera and actor motion.

The reference clip has no ground truth: nobody measured where that camera was.
These fixtures do. A textured background is warped by an exactly-known
rotation, and an actor rectangle is moved by an exactly-known amount, so the
analyser's output can be compared against a number that was decided in advance
rather than against another estimate.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np


def _background(width, height, seed=7):
    rng = np.random.default_rng(seed)
    big = rng.integers(0, 255, (height * 3, width * 3, 3), dtype=np.uint8)
    import cv2

    big = cv2.GaussianBlur(big, (0, 0), 1.6)
    for _ in range(240):  # corners for the tracker to hold on to
        x, y = rng.integers(0, width * 3 - 30), rng.integers(0, height * 3 - 30)
        colour = tuple(int(c) for c in rng.integers(40, 240, 3))
        cv2.rectangle(big, (x, y), (x + rng.integers(8, 26), y + rng.integers(8, 26)), colour, -1)
    return big


def _intrinsics(width, height, hfov_deg):
    f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    return np.array([[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1.0]])


def render_clip(
    path,
    frames,
    fps,
    width,
    height,
    yaw_deg,
    pitch_deg,
    scale,
    actor_track,
    hfov_deg=55.0,
    seed=7,
    cut_at=None,
):
    """Write a clip whose background motion is exactly K R K^-1 per frame."""
    import cv2

    big = _background(width, height, seed)
    big2 = _background(width, height, seed + 31) if cut_at is not None else None
    K = _intrinsics(width, height, hfov_deg)
    Ki = np.linalg.inv(K)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Could not open a VideoWriter for the fixture")
    offset = np.array([width, height])
    for i in range(frames):
        u = i / max(frames - 1, 1)
        source = big if (cut_at is None or i < cut_at) else big2
        yaw = math.radians(yaw_deg) * u
        pitch = math.radians(pitch_deg) * u
        s = 1.0 + (scale - 1.0) * u
        # Sign conventions, fixed here so the expectation is unambiguous:
        #   positive yaw_deg   -> the camera pans, matching +rotvec[1]
        #   positive pitch_deg -> the camera tilts UP, so the scene moves DOWN
        #                         in frame (the analyser reports -rotvec[0])
        #   scale > 1          -> the subject gets LARGER in frame
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(-pitch), math.sin(-pitch)
        ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        zoom = np.diag([s, s, 1.0])
        centre = np.array([[1, 0, -width / 2.0], [0, 1, -height / 2.0], [0, 0, 1]], dtype=float)
        h = K @ (ry @ rx) @ Ki
        h = np.linalg.inv(centre) @ zoom @ centre @ h
        shift = np.array([[1, 0, -offset[0]], [0, 1, -offset[1]], [0, 0, 1]], dtype=float)
        frame = cv2.warpPerspective(
            source, h @ shift, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        )
        if actor_track is not None:
            ax, ay, aw, ah = actor_track(u, width, height)
            cv2.rectangle(frame, (int(ax), int(ay)), (int(ax + aw), int(ay + ah)), (30, 30, 220), -1)
            cv2.circle(frame, (int(ax + aw / 2), int(ay - ah * 0.12)), int(ah * 0.14), (40, 180, 230), -1)
        writer.write(frame)
    writer.release()
    return Path(path)


def pan_clip(path, degrees=18.0, frames=72, fps=24, width=640, height=360):
    """Pure camera yaw. The actor holds still in the world, so it slides across
    frame with the background."""
    return render_clip(
        path,
        frames,
        fps,
        width,
        height,
        degrees,
        0.0,
        1.0,
        lambda u, w, h: (w * 0.5 - 40 - degrees * 6 * u, h * 0.45, 70, 130),
    ), dict(yaw_deg=degrees, pitch_deg=0.0, scale=1.0, frames=frames, fps=fps)


def tilt_clip(path, degrees=10.0, frames=60, fps=24, width=640, height=360):
    return render_clip(
        path, frames, fps, width, height, 0.0, degrees, 1.0, lambda u, w, h: (w * 0.45, h * 0.40, 70, 130)
    ), dict(yaw_deg=0.0, pitch_deg=degrees, scale=1.0, frames=frames, fps=fps)


def zoom_clip(path, scale=1.35, frames=60, fps=24, width=640, height=360):
    return render_clip(
        path,
        frames,
        fps,
        width,
        height,
        0.0,
        0.0,
        scale,
        lambda u, w, h: (w * 0.45, h * 0.42, 70 * (1 + 0.35 * u), 130 * (1 + 0.35 * u)),
    ), dict(yaw_deg=0.0, pitch_deg=0.0, scale=scale, frames=frames, fps=fps)


def actor_walk_clip(path, frames=60, fps=24, width=640, height=360):
    """Locked-off camera, actor translating: the residual-motion segmenter
    should find the actor and the global model should report no camera motion."""
    return render_clip(
        path,
        frames,
        fps,
        width,
        height,
        0.0,
        0.0,
        1.0,
        lambda u, w, h: (w * 0.22 + w * 0.45 * u, h * 0.45, 70, 130),
    ), dict(yaw_deg=0.0, pitch_deg=0.0, scale=1.0, frames=frames, fps=fps, actor_travel_px=width * 0.45)


def cut_clip(path, frames=96, fps=24, width=640, height=360, cut_frame=48):
    """One hard cut at a known frame, with no camera motion on either side."""
    return render_clip(
        path,
        frames,
        fps,
        width,
        height,
        0.0,
        0.0,
        1.0,
        lambda u, w, h: (w * 0.45, h * 0.45, 70, 130),
        cut_at=cut_frame,
    ), dict(cut_frame=cut_frame, cut_time_s=cut_frame / fps, frames=frames, fps=fps)
