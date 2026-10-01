"""Analysis 4: are two compiles of the same timeline in separate processes byte-identical?
Compares plan-run1/2/3.json produced by analysis-tb-compile.py (three separate processes),
first as written, then with the known non-deterministic bookkeeping field (compile_seconds)
removed, then field by field to locate any remaining differences."""
import json, hashlib
from pathlib import Path

OUT = Path(r"C:\TakeOne-audit-20260913\out")
EV = Path(r"C:\TakeOne\docs\audit\2026-09-13\evidence")
lines = ["# Analysis 4 - determinism of Tree B compiles (three separate processes)", ""]
P = lines.append

def sha(b): return hashlib.sha256(b).hexdigest()

plans = {}
for r in ("run1", "run2", "run3"):
    raw = (OUT / f"plan-{r}.json").read_bytes()
    plans[r] = json.loads(raw)
    meta = json.loads((OUT / f"meta-{r}.json").read_text("utf-8"))
    P(f"- {r}: plan sha256 {sha(raw)}  bytes {len(raw)}  compile_s {meta['compile_s']:.2f}  export sha256 {meta['export_sha256']}")
P("")

def strip(p):
    q = json.loads(json.dumps(p))
    q.pop("compile_seconds", None)
    return q

stripped = {r: json.dumps(strip(p), sort_keys=True, separators=(",", ":")) for r, p in plans.items()}
P("After removing plan['compile_seconds'] (wall-clock bookkeeping stored inside the plan artifact):")
for r, s in stripped.items():
    P(f"- {r}: sha256 {sha(s.encode())}")
P("")

def diff(a, b, path="", out=None, limit=40):
    if out is None: out = []
    if len(out) >= limit: return out
    if type(a) != type(b):
        out.append((path, "type", type(a).__name__, type(b).__name__)); return out
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((path + "/" + k, "missing", k in a, k in b)); continue
            diff(a[k], b[k], path + "/" + k, out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((path, "len", len(a), len(b))); return out
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, limit)
    else:
        if a != b:
            if isinstance(a, float) and isinstance(b, float):
                out.append((path, "float", a, b))
            else:
                out.append((path, "value", a, b))
    return out

for a, b in (("run1", "run2"), ("run1", "run3"), ("run2", "run3")):
    d = diff(strip(plans[a]), strip(plans[b]))
    P(f"## {a} vs {b}: {len(d)} differing leaves (first 40 shown)")
    P("")
    if not d:
        P("byte-identical after removing compile_seconds")
    for row in d:
        P(f"- `{row[0]}` {row[1]}: {row[2]!r} vs {row[3]!r}")
    P("")
# Where do the differences live?
d = diff(strip(plans["run1"]), strip(plans["run2"]), limit=100000)
from collections import Counter
c = Counter(r[0].split("/")[1] if "/" in r[0] else r[0] for r in d)
P("## Differences by top-level key (run1 vs run2, unlimited)")
P("")
for k, v in c.most_common():
    P(f"- {k}: {v}")
c2 = Counter()
for r in d:
    parts = r[0].split("/")
    if len(parts) > 3:
        c2["/".join(parts[1:4]).split("[")[0] + "/" + parts[3].split("[")[0] if len(parts) > 3 else r[0]] += 1
P("")
P("## Differences by field family (run1 vs run2)")
P("")
fam = Counter()
for r in d:
    parts = [p.split("[")[0] for p in r[0].split("/") if p]
    fam["/".join(parts[:3])] += 1
for k, v in fam.most_common(30):
    P(f"- {k}: {v}")
(EV / "analysis-04-determinism.md").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines[:60]))
