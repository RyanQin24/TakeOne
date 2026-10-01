"""Run the repository's exact declared node --check files without the stalled npm wrapper."""
import json
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/rehearsal"
DEST = Path(__file__).parent
script = json.loads((APP / "package.json").read_text(encoding="utf-8"))["scripts"]["check"]
results = []
for part in script.split("&&"):
    arguments = shlex.split(part)
    if len(arguments) != 3 or arguments[:2] != ["node", "--check"]:
        raise ValueError(f"Unexpected command in browser syntax script: {part}")
    result = subprocess.run(arguments, cwd=APP, capture_output=True, timeout=15)
    results.append({"command": arguments, "exit_code": result.returncode,
                    "stdout": result.stdout.decode("utf-8", errors="replace"),
                    "stderr": result.stderr.decode("utf-8", errors="replace")})
report = {"npm_wrapper_used": False, "declared_script": script, "checks": results,
          "passed": all(r["exit_code"] == 0 for r in results)}
(DEST / "direct-browser-syntax.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"files": len(results), "passed": report["passed"]}))
raise SystemExit(0 if report["passed"] else 1)
