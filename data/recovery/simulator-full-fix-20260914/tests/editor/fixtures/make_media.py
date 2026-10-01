"""Deterministic fixture media, generated rather than committed.

Committing video into a repository is a mistake that keeps costing: it bloats clones, it
cannot be reviewed, and it silently drifts from what the tests actually assume. These
clips are synthesised from FFmpeg sources, so the fixtures are reproducible anywhere, the
repository stays text, and every property a test depends on (this take is soft, that one is
warm, this click track is exactly 120 BPM) is visible in the code that made it.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

GENERATOR_VERSION = 1

BASE = "testsrc2=size=1280x720:rate=30"

CLIPS = {
    # name:            (seconds, filter chain, what the clip is for)
    "shot_a_neutral": (6.0, "hue=s=0.75", "A well-exposed, neutral, sharp take."),
    "shot_b_warm": (
        5.0,
        "hue=s=0.75,colortemperature=temperature=4200:mix=1,eq=brightness=0.07",
        "The same scene shot warm and a little hot: the shot-matching target.",
    ),
    "shot_c_soft": (
        4.0,
        "hue=s=0.75,gblur=sigma=7",
        "A soft take the quality scorer must rank below its sharp original.",
    ),
    "shot_d_dark": (
        5.0,
        "hue=s=0.75,eq=brightness=-0.13,eq=contrast=0.9",
        "An underexposed take: the exposure correction target.",
    ),
}


def ffmpeg():
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit("ffmpeg is required to build the editor fixtures")
    return found


def run(argv):
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"fixture generation failed:\n{result.stderr.strip()[-1500:]}")


def build(destination, force=False):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    binary = ffmpeg()
    made = []
    for name, (duration, chain, _purpose) in CLIPS.items():
        path = destination / f"{name}.mp4"
        if path.exists() and not force:
            made.append(path)
            continue
        run(
            [
                binary,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"{BASE}:duration={duration}",
                "-vf",
                f"{chain},format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                str(path),
            ]
        )
        made.append(path)

    click = destination / "click_120bpm.wav"
    if not click.exists() or force:
        # One transient every 0.5 s is exactly 120 BPM, with a decaying 1 kHz tone so the
        # onset is sharp and the ground truth is arithmetic rather than annotation.
        run(
            [
                binary,
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "aevalsrc='0.8*sin(2*PI*1000*t)*exp(-45*mod(t,0.5))':s=48000:d=12",
                "-c:a",
                "pcm_s16le",
                str(click),
            ]
        )
    made.append(click)
    return made


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build deterministic editor fixture media")
    parser.add_argument("--destination", default=str(Path(__file__).parent / "media"))
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args(argv)
    for path in build(arguments.destination, arguments.force):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
