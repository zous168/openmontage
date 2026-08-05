"""One-off: list FastAPI route decorators under agent-hub/src."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
SKIP = ("web_dist", "__pycache__", "ui-tui", "node_modules")
# 已从 monorepo 移除的试验插件目录（提取时忽略）
SKIP_PLUGIN_PREFIXES = (
    "plugins/hub-knowledge/",
    "plugins/hub_crm/",
    "plugins/hub_materials/",
)
DECOR = re.compile(
    r"@(?:app|router)\.(get|post|put|patch|delete|websocket)\(\s*[\"']([^\"']*)[\"']",
    re.I,
)

groups: dict[str, list[str]] = {}
for py in sorted(ROOT.rglob("*.py")):
    rel_posix = py.relative_to(ROOT).as_posix()
    if any(s in rel_posix for s in SKIP):
        continue
    if any(rel_posix.startswith(p) for p in SKIP_PLUGIN_PREFIXES):
        continue
    text = py.read_text(encoding="utf-8", errors="ignore")
    hits = [(m.group(1).upper(), m.group(2)) for m in DECOR.finditer(text)]
    if not hits:
        continue
    rel = py.relative_to(ROOT).as_posix()
    groups[rel] = [f"{method:7} {path}" for method, path in hits]

FOCUS = (
    "hermes_cli/web_server.py",
    "main.py",
    "middlewares/",
    "plugins/hub",
    "hermes_cli/dashboard_auth",
    "gateway/platforms",
)

for rel, lines in groups.items():
    if not any(rel.startswith(f) or f in rel for f in FOCUS):
        continue
    print(f"=== {rel} ({len(lines)}) ===")
    for line in lines:
        print(line)
    print()

print(f"TOTAL FILES WITH ROUTES: {len(groups)}")
print(f"TOTAL ROUTES: {sum(len(v) for v in groups.values())}")
