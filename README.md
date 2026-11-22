# git-env-guard

Catch test fixtures that run Git repository commands without clearing the calling
hook's repository environment. Git hooks export `GIT_DIR`, `GIT_INDEX_FILE` and
other local variables: `git -C TEMP init` alone does not isolate a fixture.
Clear every variable named by `git rev-parse --local-env-vars` before running Git
against a disposable repository. See the [shell](examples/fixture.sh) and
[Python](examples/fixture.py) examples; do not run fixtures against a real checkout.

Python 3.10–3.13. The tool only reads source and Git objects. It never executes or
imports scanned files, writes repositories, accesses the network or runs fixtures.
TOML parsing uses the standard library on 3.11+ and tomli on older Python.

```sh
python -m pip install --require-hashes -r requirements-ci.txt
python -m unittest discover -s tests -v
ruff check git_env_guard tests
mypy --strict git_env_guard
python -m git_env_guard --root examples
python -m build --no-isolation
```

After a release, install `git-env-guard` and run `git-env-guard` to scan the staged
index. The included pre-commit hook has id `git-env-guard`; pin a reviewed release
in your pre-commit configuration. No supported public release yet.

See [usage](docs/usage.md), [architecture](docs/architecture.md),
[contribution policy](CONTRIBUTING.md), [security](SECURITY.md),
[release setup](docs/releases.md) and [changelog](CHANGELOG.md).
Licensed under [Apache-2.0](LICENSE).
