#!/usr/bin/env bash
# Write one version into every file that carries it.
# Usage: scripts/bump-version.sh 0.2.0
#
# Nine sites: pyproject.toml, three package __init__.py, two Claude manifests,
# the Codex manifest and two skill.json. pyproject.toml is the source of truth —
# it is what a `pip install` publishes — and every other site agrees with it.
#
# Every site is read and checked BEFORE any is written. A site that is missing,
# unreadable, or not carrying the key it is supposed to carry names itself and
# stops the run with nothing modified. A half-bumped tree is worse than no bump,
# and a script that reports success while changing nothing is worse than both.
set -euo pipefail

VERSION="${1:?usage: bump-version.sh <version>}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "not semver: $VERSION" >&2; exit 1; }

cd "$(dirname "$0")/.."

python3 - "$VERSION" <<'PY'
import json, pathlib, re, sys

version = sys.argv[1]

TEXT_SITES = [
    ("pyproject.toml", r'^version = "(?P<v>[^"]*)"$'),
    ("src/printful_core/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
    ("src/printful_mcp/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
    ("src/printful_cli/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
]

# "top"     -> a top-level "version" key
# "plugins" -> a non-empty "plugins" list whose every entry carries "version"
JSON_SITES = [
    (".claude-plugin/plugin.json", "top"),
    (".claude-plugin/marketplace.json", "plugins"),
    (".codex-plugin/plugin.json", "top"),
    ("skills/printful-mcp/skill.json", "top"),
    ("skills/printful-cli/skill.json", "top"),
]

errors = []
writes = []  # (path, new_text)


def read(path):
    p = pathlib.Path(path)
    if not p.exists():
        errors.append(f"{path}: missing")
        return None
    try:
        return p.read_text()
    except OSError as e:
        errors.append(f"{path}: unreadable ({e})")
        return None


for path, pattern in TEXT_SITES:
    text = read(path)
    if text is None:
        continue
    matches = list(re.finditer(pattern, text, flags=re.M))
    if len(matches) != 1:
        errors.append(f"{path}: expected exactly one version line, found {len(matches)}")
        continue
    m = matches[0]
    writes.append((path, text[: m.start("v")] + version + text[m.end("v") :]))

for path, shape in JSON_SITES:
    text = read(path)
    if text is None:
        continue
    try:
        data = json.loads(text)
    except ValueError as e:
        errors.append(f"{path}: not valid JSON ({e})")
        continue
    if shape == "top":
        if not isinstance(data, dict) or "version" not in data:
            errors.append(f'{path}: no top-level "version" key to write')
            continue
        data["version"] = version
    else:
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, list) or not plugins:
            errors.append(f'{path}: no non-empty "plugins" list to write')
            continue
        missing = [i for i, e in enumerate(plugins)
                   if not isinstance(e, dict) or "version" not in e]
        if missing:
            errors.append(f'{path}: no "version" key in plugins{missing}')
            continue
        for entry in plugins:
            entry["version"] = version
    writes.append((path, json.dumps(data, indent=2) + "\n"))

if errors:
    print("bump-version: refusing to write — nothing was modified.", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

expected = len(TEXT_SITES) + len(JSON_SITES)
if len(writes) != expected:
    sys.exit(f"bump-version: prepared {len(writes)} of {expected} sites — refusing to write")

for path, new_text in writes:
    p = pathlib.Path(path)
    if new_text != p.read_text():
        p.write_text(new_text)
    print(f"  {path}")

print(f"version -> {version} ({len(writes)} sites)")
PY
