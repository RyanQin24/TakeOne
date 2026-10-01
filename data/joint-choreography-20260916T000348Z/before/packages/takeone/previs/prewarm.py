"""Populate the content-addressed preview cache before a conversation needs it.

A cold template compile costs ~2 s; warm is ~40 ms. A live voice exchange only
stays under its ~800 ms budget when the compile is warm, so the server warms the
grid in a background thread at startup, and the demo path is warmed explicitly
with the exact shots that will be requested.

Everything here calls `cache.compile_preview` directly — never `/api/compile` —
so warming can never contend with the operator's foreground compile lock.
"""

import json
import threading
import time

GRID_DURATIONS_S = (5, 8, 10, 15, 20)
GRID_LIMIT = 200  # stays well inside cache.MAX_ENTRIES so live misses never evict warms


def grid(catalog=None):
    """The startup warm set: every template at its defaults, and the length
    choices a director actually asks for on stationary shots."""
    if catalog is None:
        from takeone.director.studio import movement_catalog

        catalog = movement_catalog()
    settings = []
    for template in catalog["templates"]:
        settings.append({"mode": "template", "template_id": template["id"]})
        if template["route"] == "hold" and "duration_s" in template["parameters"]:
            for duration in GRID_DURATIONS_S:
                settings.append({"mode": "template", "template_id": template["id"], "duration_s": duration})
    if len(settings) > GRID_LIMIT:
        raise ValueError(f"Pre-warm grid grew to {len(settings)} entries; keep it under {GRID_LIMIT}")
    return settings


def warm(settings_list, *, compile_preview=None, pause_s=0.0, log=lambda message: None):
    """Compile each entry once, reporting misses honestly. Failures are counted,
    never hidden: a template that stops compiling should be visible at startup."""
    if compile_preview is None:
        from .cache import compile_preview
    warmed = failed = 0
    started = time.monotonic()
    for settings in settings_list:
        try:
            compile_preview(settings)
            warmed += 1
        except Exception as error:  # a broken entry must not stop the rest of the grid
            failed += 1
            log(f"prewarm failed for {settings.get('template_id')}: {error}")
        if pause_s:
            time.sleep(pause_s)  # yield to any foreground compile
    report = {"warmed": warmed, "failed": failed, "seconds": round(time.monotonic() - started, 2)}
    log(f"prewarm finished: {report}")
    return report


def start_background(log=lambda message: None):
    """The server's startup warm: a daemon thread, invisible on failure paths
    except for its log line, never touching the HTTP compile lock."""

    def run():
        try:
            warm(grid(), pause_s=0.05, log=log)
        except Exception as error:
            log(f"prewarm unavailable: {error}")

    thread = threading.Thread(target=run, name="takeone-prewarm", daemon=True)
    thread.start()
    return thread


def main(argv=None):
    """Demo-path warming: compile the exact shots the demo will ask for.

    The file is a JSON list of template settings objects — the same shape a
    saved shot's `settings` carries.
    """
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--demo", type=Path, help="JSON list of settings to warm exactly")
    arguments = parser.parse_args(argv)
    if arguments.demo:
        settings_list = json.loads(arguments.demo.read_text(encoding="utf-8"))
        if not isinstance(settings_list, list):
            raise SystemExit("The demo file must be a JSON list of settings objects")
    else:
        settings_list = grid()
    report = warm(settings_list, log=print)
    print(json.dumps(report))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
