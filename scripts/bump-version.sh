#!/usr/bin/env bash
# Write one version into every file that carries it.
# Usage: scripts/bump-version.sh 0.2.0
#
# Nine sites: pyproject.toml, three package __init__.py, two Claude manifests,
# the Codex manifest and two skill.json. pyproject.toml is the source of truth —
# it is what a `pip install` publishes — and every other site agrees with it.
set -euo pipefail

VERSION="${1:?usage: bump-version.sh <version>}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not semver: $VERSION" >&2; exit 1; }

cd "$(dirname "$0")/.."

python3 - "$VERSION" <<'PY'
import json, pathlib, re, sys

version = sys.argv[1]

def sub_one(path, pattern, replacement):
    p = pathlib.Path(path)
    text = p.read_text()
    new, n = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"{path}: expected exactly one version line, found {n}")
    if new != text:
        p.write_text(new)
    print(f"  {path}")

sub_one("pyproject.toml", r'^version = ".*"$', f'version = "{version}"')

for path in ["src/printful_core/__init__.py",
             "src/printful_mcp/__init__.py",
             "src/printful_cli/__init__.py"]:
    sub_one(path, r'^__version__ = ".*"$', f'__version__ = "{version}"')

for path in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
             ".codex-plugin/plugin.json",
             "skills/printful-mcp/skill.json", "skills/printful-cli/skill.json"]:
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"{path}: missing — a manifest this script cannot reach is one that drifts")
    data = json.loads(p.read_text())
    if "version" in data:
        data["version"] = version
    for plugin in data.get("plugins", []):
        plugin["version"] = version
    p.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  {path}")

print(f"version -> {version}")
PY
