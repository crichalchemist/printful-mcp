#!/usr/bin/env python3
"""Every manifest parses, every version agrees, every referenced path exists.

The site tables below mirror `scripts/bump-version.sh`, which is the writer.
Every site that script writes, this script reads back -- a checker that cannot
see a site the writer writes reports an agreement it never tested, which is
worse than no checker at all. The two files deliberately spell the sites the
same way, down to the "top" / "plugins" shape vocabulary; keep them in step by
hand when either changes.

Absence is never agreement. A site declared here that carries no version fails
by name, rather than being skipped in silence.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# pyproject.toml is the source of truth -- it is what a `pip install` publishes.
SOURCE_OF_TRUTH = ("pyproject.toml", r'^version = "(?P<v>[^"]*)"$')

# Plain-text version sites, checked against the source of truth.
TEXT_SITES = [
    ("src/printful_core/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
    ("src/printful_mcp/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
    ("src/printful_cli/__init__.py", r'^__version__ = "(?P<v>[^"]*)"$'),
]

# JSON manifests that carry a version.
# "top"     -> a top-level "version" key
# "plugins" -> a non-empty "plugins" list whose every entry carries "version"
JSON_SITES = [
    (".claude-plugin/plugin.json", "top"),
    (".claude-plugin/marketplace.json", "plugins"),
    (".codex-plugin/plugin.json", "top"),
    ("skills/printful-mcp/skill.json", "top"),
    ("skills/printful-cli/skill.json", "top"),
]

# JSON manifests that carry no version and are not written by bump-version.sh.
# They are still parsed, and their referenced paths are still resolved.
PARSE_ONLY = [".mcp.json"]

SYMLINKS = ["skills/printful-mcp/SKILL.md", "skills/printful-cli/SKILL.md"]

failures = []


def read(name):
    path = ROOT / name
    if not path.exists():
        failures.append(f"{name}: missing")
        return None
    try:
        return path.read_text()
    except OSError as e:
        failures.append(f"{name}: unreadable ({e})")
        return None


def sole_version(name, text, pattern):
    """The one version a text site carries, or None with a failure recorded."""
    matches = list(re.finditer(pattern, text, flags=re.M))
    if len(matches) != 1:
        failures.append(f"{name}: expected exactly one version line, found {len(matches)}")
        return None
    return matches[0].group("v")


def strings(node):
    """Every string anywhere in a parsed JSON document."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


name, pattern = SOURCE_OF_TRUTH
text = read(name)
if text is None:
    sys.exit(f"{name} is the source of truth and could not be read")
expected = sole_version(name, text, pattern)
if expected is None:
    sys.exit(f"{name} carries no single version line to check the rest against")

for name, pattern in TEXT_SITES:
    text = read(name)
    if text is None:
        continue
    found = sole_version(name, text, pattern)
    if found is not None and found != expected:
        failures.append(f"{name}: version {found!r}, pyproject says {expected!r}")

for name, shape in JSON_SITES + [(n, None) for n in PARSE_ONLY]:
    text = read(name)
    if text is None:
        continue
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        failures.append(f"{name}: invalid JSON -- {e}")
        continue

    if shape == "top":
        if not isinstance(data, dict) or "version" not in data:
            failures.append(f'{name}: no top-level "version" key to check')
        elif data["version"] != expected:
            failures.append(f"{name}: version {data['version']!r}, pyproject says {expected!r}")
    elif shape == "plugins":
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, list) or not plugins:
            failures.append(f'{name}: no non-empty "plugins" list to check')
        else:
            for i, entry in enumerate(plugins):
                if not isinstance(entry, dict) or "version" not in entry:
                    failures.append(f'{name}: no "version" key in plugins[{i}]')
                elif entry["version"] != expected:
                    failures.append(
                        f"{name}: plugins[{i}] version {entry['version']!r}, "
                        f"pyproject says {expected!r}"
                    )

    # Every relative path a manifest names must resolve, or the plugin installs
    # and then fails for the user rather than for us.
    for value in strings(data):
        if value.startswith("./") and not (ROOT / value[2:]).exists():
            failures.append(f"{name}: references {value}, which does not exist")

for name in SYMLINKS:
    path = ROOT / name
    if path.exists():
        continue
    if path.is_symlink():
        failures.append(f"{name}: broken symlink -> {path.readlink()}")
    else:
        failures.append(f"{name}: missing")

if failures:
    print("\n".join(failures))
    sys.exit(1)

sites = 1 + len(TEXT_SITES) + len(JSON_SITES)
print(
    f"manifests ok, version {expected} "
    f"({sites} version sites, {len(PARSE_ONLY)} parsed without one, "
    f"{len(SYMLINKS)} symlinks)"
)
