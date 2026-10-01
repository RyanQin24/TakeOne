"""The dependency graph, enforced.

The specification asked for fourteen distribution packages to keep these boundaries. One
Python subpackage plus this test enforces them more strictly, because a violating import
fails the build instead of merely looking wrong in a folder listing.
"""

import ast
import unittest

from tests.editor.support import ROOT  # noqa: F401

PACKAGE = ROOT / "packages" / "takeone" / "editor"

# Lower number = lower layer. A module may import from its own layer or any lower one.
LAYERS = {
    "contracts": 0,
    "ids": 0,
    "errors": 0,
    "timing": 1,
    "color": 1,
    "audio": 1,
    "assets": 1,
    "state": 2,
    "operations": 2,
    "patch": 2,
    "media": 2,
    "library": 2,
    "graph": 3,
    "reducer": 3,
    "project": 3,
    "effects": 4,
    "templates": 4,
    "compile": 5,
    "render": 6,
    "analysis": 6,
    "export": 6,
    "robot": 6,
    "plan": 7,
    "repository": 8,
    "jobs": 8,
    "service": 8,
    "api": 9,
    "vfx": 9,
    "vfx_planning": 9,
    "chatcut_probe": 9,
    "cli": 9,
    "__init__": 9,
}

# Edges that must never exist regardless of layer, because they would undo a design rule.
FORBIDDEN = {
    ("plan", "render"): "the planner decides what, never how",
    ("reducer", "plan"): "the editor core must not depend on AI",
    ("reducer", "render"): "the editor core must not depend on a backend",
    ("state", "effects"): "state must not need the effect registry to exist",
    ("graph", "render"): "the graph is backend independent",
    ("export", "render"): "an exporter writes a document, it does not render",
    ("render", "plan"): "the renderer must not know a planner exists",
    ("render", "reducer"): "the renderer must not mutate a project",
}


def module_key(path):
    relative = path.relative_to(PACKAGE)
    return relative.parts[0] if len(relative.parts) > 1 else relative.stem


def local_imports(tree, key, path):
    """Resolve intra-package imports to their top-level module key."""
    found = set()
    for statement in ast.walk(tree):
        if isinstance(statement, ast.ImportFrom):
            if statement.level == 0:
                if statement.module and statement.module.startswith("takeone.editor"):
                    parts = statement.module.split(".")
                    if len(parts) > 2:
                        found.add(parts[2])
                continue
            inside_package = len(path.relative_to(PACKAGE).parts) > 1
            depth = statement.level - (2 if inside_package else 1)
            if statement.module:
                head = statement.module.split(".")[0]
                found.add(key if depth < 0 else head)
            elif depth >= 0:
                for alias in statement.names:
                    found.add(alias.name.split(".")[0])
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name.startswith("takeone.editor."):
                    found.add(alias.name.split(".")[2])
    return {item for item in found if item in LAYERS}


class Layering(unittest.TestCase):
    def setUp(self):
        self.modules = sorted(PACKAGE.rglob("*.py"))
        self.assertTrue(self.modules, "no editor modules found")

    def test_every_module_is_assigned_a_layer(self):
        unassigned = sorted({module_key(path) for path in self.modules} - set(LAYERS))
        self.assertEqual(unassigned, [], f"modules with no declared layer: {unassigned}")

    def test_imports_never_climb_a_layer(self):
        violations = []
        for path in self.modules:
            key = module_key(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in local_imports(tree, key, path):
                if imported == key:
                    continue
                if LAYERS[imported] > LAYERS[key]:
                    violations.append(
                        f"{path.relative_to(PACKAGE)} (layer {LAYERS[key]}) imports "
                        f"{imported} (layer {LAYERS[imported]})"
                    )
        self.assertEqual(violations, [], "\n".join(violations))

    def test_forbidden_edges_are_absent(self):
        violations = []
        for path in self.modules:
            key = module_key(path)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for imported in local_imports(tree, key, path):
                reason = FORBIDDEN.get((key, imported))
                if reason:
                    violations.append(f"{path.relative_to(PACKAGE)} imports {imported}: {reason}")
        self.assertEqual(violations, [], "\n".join(violations))

    def test_importing_the_package_starts_nothing(self):
        """No process, no file handle, no network at import. The Director's rule, kept."""
        source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "sqlite3", "socket", "open("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
