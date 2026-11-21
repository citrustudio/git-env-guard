"""Inspect fixture source in the Git index or a filesystem root."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .core import Config, Invalid, disk_files, git, index_files, scan


def load_config(path: Path | None, root: Path) -> Config:
    selected = path or next((p for p in (root / ".git-env-guard.toml", root / "pyproject.toml") if p.is_file()), None)
    raw: dict[str, Any] = {}
    if selected is not None:
        with selected.open("rb") as stream:
            raw = tomllib.load(stream)
        if selected.name == "pyproject.toml":
            raw = raw.get("tool", {}).get("git-env-guard", {})
    allowed = {"extra-globs", "commands", "scrub-markers", "ignore", "max-bytes"}
    if not isinstance(raw, dict) or raw.keys() - allowed:
        raise Invalid("unknown configuration keys")
    config = Config()
    for key, attr in (("extra-globs", "extra_globs"), ("commands", "commands"), ("scrub-markers", "scrub_markers")):
        values = raw.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise Invalid(f"{key} must contain nonempty strings")
        if key == "extra-globs" and any(Path(v).is_absolute() or ".." in Path(v).parts for v in values):
            raise Invalid("extra-globs must be root-relative")
        if key == "commands" and any(not v.replace("-", "").isalnum() for v in values):
            raise Invalid("commands must be subcommand names")
        setattr(config, attr, list(dict.fromkeys(getattr(config, attr) + values)))
    config.ignore = raw.get("ignore", {})
    if not isinstance(config.ignore, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() and not Path(k).is_absolute() and ".." not in Path(k).parts for k, v in config.ignore.items()):
        raise Invalid("ignore maps relative file paths to nonempty reasons")
    config.max_bytes = raw.get("max-bytes", config.max_bytes)
    if isinstance(config.max_bytes, bool) or not isinstance(config.max_bytes, int) or not 1 <= config.max_bytes <= 8 * 1024 * 1024:
        raise Invalid("max-bytes must be 1..8388608")
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="scan disk instead of staged index")
    parser.add_argument("--config", type=Path, help="explicit TOML file (relative to current directory)")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve() if args.root else Path(git("rev-parse", "--show-toplevel").decode().strip())
        if not root.is_dir():
            raise Invalid("root must be an existing directory")
        config = load_config(args.config, root)
        count, offenders = scan(disk_files(root, config) if args.root else index_files(config), config)
        for path in offenders:
            print(f"{path}: fixture Git command without a scrub marker", file=sys.stderr)
        print(f"git-env-guard: scanned {count} source files; {len(offenders)} unsafe fixture files")
        return int(bool(offenders))
    except (Invalid, OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(f"git-env-guard: {exc}", file=sys.stderr)
        return 1
