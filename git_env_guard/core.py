"""Read source as data; never import, evaluate or run scanned code."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
import re
import shlex
import subprocess
from typing import Iterable


class Invalid(ValueError):
    pass


@dataclass
class Config:
    extra_globs: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=lambda: ["init"])
    scrub_markers: list[str] = field(default_factory=lambda: ["--local-env-vars"])
    ignore: dict[str, str] = field(default_factory=dict)
    max_bytes: int = 1024 * 1024


def wanted(path: str, config: Config) -> bool:
    return path.endswith((".py", ".sh", ".bash")) or path.startswith("scripts/") or any(fnmatch(path, g) for g in config.extra_globs)


def command_present(words: list[str], commands: list[str]) -> bool:
    for i, word in enumerate(words):
        if word != "git":
            continue
        j = i + 1
        while j < len(words):
            arg = words[j]
            if arg in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
                j += 2
            elif arg.startswith("-"):
                j += 1
            else:
                if arg in commands:
                    return True
                break
    return False


def strip_shell_comments(text: str) -> str:
    # A shell comment starts at an unquoted word boundary, not at every hash.
    result = []
    quote = ""
    boundary = True
    escaped = False
    comment = False
    for char in text:
        if comment:
            if char != "\n":
                continue
            comment = False
        if escaped:
            result.append(char)
            escaped = False
            if char != "\n":
                boundary = False
            continue
        if char == "\\" and quote != "'":
            result.append(char)
            escaped = True
            continue
        if quote:
            result.append(char)
            if char == quote:
                quote = ""
            continue
        if char in ("'", '"'):
            quote = char
            boundary = False
        elif char == "#" and boundary:
            comment = True
            continue
        else:
            boundary = char.isspace() or char in ";&|()<>"
        result.append(char)
    return "".join(result)


def shell_tokens(text: str) -> list[str]:
    try:
        lexer = shlex.shlex(strip_shell_comments(text), posix=True, punctuation_chars=";&|()\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError as exc:
        raise Invalid("shell text has unmatched quoting") from exc


def classify(path: str, text: str, config: Config) -> tuple[bool, bool]:
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError) as exc:
            raise Invalid("Python source does not parse") from exc
        # Ignore prose expressions, including module/class/function docstrings.
        prose = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)}
        strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose]
        commands = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.List, ast.Tuple)):
                words = [n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else "DYNAMIC" for n in node.elts]
                commands.append(command_present(words, config.commands))
        for text_value in strings:
            # Only contiguous shell command text qualifies; unrelated literals do not.
            if re.search(r"(?:^|[;&|()]|\n)\s*git\s", text_value):
                commands.append(command_present(shell_tokens(text_value), config.commands))
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        return any(commands), any(marker in value for marker in config.scrub_markers for value in strings) or any(marker in calls for marker in config.scrub_markers)
    words = shell_tokens(text)
    runs = command_present(words, config.commands)
    code = " ".join(words)
    scrubbed = all(token in words for token in ("git", "rev-parse", "--local-env-vars")) or any(marker in code for marker in config.scrub_markers if marker != "--local-env-vars")
    return runs, scrubbed


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30).stdout


def index_files(config: Config) -> Iterable[tuple[str, bytes]]:
    entries = []
    for entry in git("ls-files", "--stage", "-z", "--full-name", "--", ":/").split(b"\0"):
        if not entry:
            continue
        meta, raw_name = entry.split(b"\t", 1)
        mode, oid, stage = meta.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if not wanted(name, config) or name in config.ignore:
            continue
        if stage != "0" or mode not in ("100644", "100755"):
            raise Invalid("unmerged or non-regular staged input")
        entries.append((name, oid))
    if not entries:
        return
    requests = "".join(oid + "\n" for _, oid in entries).encode()
    sizes = git("cat-file", "--batch-check=%(objectsize)", data=requests).splitlines()
    if len(sizes) != len(entries):
        raise Invalid("incomplete index size response")
    total = 0
    for (name, oid), size in zip(entries, sizes):
        count = int(size)
        if count > config.max_bytes:
            raise Invalid(f"{name}: file exceeds max-bytes")
        total += count
        if total > 64 * 1024 * 1024:
            raise Invalid("selected source exceeds 64 MiB")
        yield name, git("cat-file", "blob", oid)


def disk_files(root: Path, config: Config) -> Iterable[tuple[str, bytes]]:
    import os
    total = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "build", "dist") and not d.startswith(".venv") and not (Path(base) / d).is_symlink()]
        for name in sorted(names):
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            if not wanted(relative, config) or relative in config.ignore:
                continue
            if path.is_symlink() or not path.is_file():
                raise Invalid(f"{relative}: non-regular input")
            if path.stat().st_size > config.max_bytes:
                raise Invalid(f"{relative}: file exceeds max-bytes")
            with path.open("rb") as stream:
                data = stream.read(config.max_bytes + 1)
            if len(data) > config.max_bytes:
                raise Invalid(f"{relative}: file exceeds max-bytes")
            total += len(data)
            if total > 64 * 1024 * 1024:
                raise Invalid("selected source exceeds 64 MiB")
            yield relative, data


def scan(files: Iterable[tuple[str, bytes]], config: Config) -> tuple[int, list[str]]:
    count = 0
    offenders = []
    for path, data in files:
        if path in config.ignore:
            continue
        if len(data) > config.max_bytes:
            raise Invalid(f"{path}: file exceeds max-bytes")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Invalid(f"{path}: input is not UTF-8") from exc
        if "\0" in text:
            raise Invalid(f"{path}: binary input")
        if not (path.endswith((".py", ".sh", ".bash")) or text.startswith("#!") or any(fnmatch(path, g) for g in config.extra_globs)):
            continue
        runs, scrubbed = classify(path, text, config)
        count += 1
        if runs and not scrubbed:
            offenders.append(path)
    if not count:
        raise Invalid("scanned 0 source files")
    return count, offenders
