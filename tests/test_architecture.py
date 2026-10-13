"""Guards that keep the design honest: the team contract and the dependency rule.

Layers (docs/plan/02-architecture.md#layers-and-the-dependency-rule), inner to outer:
domain → application → adapters → entry points (cli, connector, wiring, config).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "bpk_connector"

# What each layer may import from inside the package.
ALLOWED_INTERNAL = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "adapters": {"domain", "application", "adapters"},
}
THIRD_PARTY_ALLOWED_IN = {"adapters"}  # and entry points


def _layer(path: Path) -> str | None:
    parts = path.relative_to(PACKAGE).parts
    return parts[0] if parts[0] in ALLOWED_INTERNAL else None


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _violations() -> list[str]:
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        layer = _layer(path)
        if layer is None:
            continue
        for name in _imports(path):
            top = name.split(".")[0]
            if top == "bpk_connector":
                inner = name.split(".")[1] if "." in name else ""
                if inner not in ALLOWED_INTERNAL[layer]:
                    found.append(f"{path.relative_to(ROOT)} imports {name}")
            elif top not in sys.stdlib_module_names and layer not in THIRD_PARTY_ALLOWED_IN:
                found.append(f"{path.relative_to(ROOT)} imports third-party {name}")
    return found


def test_dependencies_point_inward_only() -> None:
    assert _violations() == []


def test_vendored_interface_matches_the_team_document() -> None:
    doc = (ROOT / "contract/CONNECTOR_INTERFACE.md").read_text()
    published = re.findall(r"```python\n(.*?)```", doc, re.S)[0]
    assert (PACKAGE / "source_connector.py").read_text() == published
