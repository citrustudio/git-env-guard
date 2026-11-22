# Usage

Requires Python 3.10 or newer; CI tests Python 3.10–3.13.

`git-env-guard [-h] [--root DIR] [--config FILE]`. `-h` / `--help` shows help.
`python -m git_env_guard` has the same interface. Exit 0 means a nonempty scan
found no unmarked fixture commands; exit 1 means offenders or an input/config/Git
error; malformed CLI arguments use argparse exit 2.

By default the tool reads the **staged index**, even when run from a repository
subdirectory. Unstaged edits do not change that result. `--root DIR` instead reads
source files on disk, including untracked files. `--config FILE` selects an
explicit TOML file relative to the current directory. Otherwise the scan root's
`.git-env-guard.toml` wins over `pyproject.toml` `[tool.git-env-guard]`.
Configuration is read from disk, including in index mode; review configuration
changes as policy changes, and keep it in sync with the intended staged policy.

Configuration keys (all optional):

- `extra-globs`: additional root-relative file globs. Unknown extensions selected
  this way use the shell-text detector. Defaults cover `.py`, `.sh`, `.bash` and
  shebang scripts under `scripts/`.
- `commands`: additional Git subcommands, such as `commit` and `worktree`.
  The default `init` remains enabled.
- `scrub-markers`: extra literal code markers or Python callable names indicating
  an isolation helper. The default is `--local-env-vars`. These are policy
  declarations, not proof that the helper clears the environment.
- `[ignore]`: exact root-relative file paths mapped to nonempty reasons. No
  basename exemption exists; ignores are explicit and reviewed. There are no
  default ignores for detector implementation or test files.
- `max-bytes`: per selected file cap, default 1048576, allowed 1–8388608. Oversize
  files fail before disk/index blob reads. Selected content is capped at 64 MiB.

See `examples/config.toml` for the standalone layout. With pyproject, prefix keys
with `[tool.git-env-guard]` and the ignore table with `[tool.git-env-guard.ignore]`.
Unknown keys, malformed Python, invalid UTF-8, binary source, unreadable files,
selected symlink files, unresolved index stages and empty scans fail closed.
Disk traversal skips `.git`, virtualenvs, node_modules, build output and symlink
directories. No scanned source is run. Git read commands have 30-second deadlines.

The detector finds literal Python argv lists/tuples and contiguous shell-command
strings, plus shell command tokens. Separate unrelated `"git"` and `"init"`
literals do not constitute a command. Comments and Python docstrings cannot
supply scrub evidence. A marker elsewhere in the same file is only a heuristic:
it does not prove ordering, scope, execution or that all variables are cleared.
Dynamic command construction and imported helpers can escape detection; use
explicit helper markers and runtime sentinel tests for your trusted fixtures.
