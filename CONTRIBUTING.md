# Local development

See the [organization contribution policy](https://github.com/citrustudio/.github/blob/main/CONTRIBUTING.md)
for pull requests, review, DCO and AI disclosure.

Run `python -m unittest discover -s tests -v`, `ruff check git_env_guard tests` and `mypy --strict git_env_guard`.
Install hash-locked build/test tools with `python -m pip install --require-hashes -r requirements-ci.txt`.
Build with `python -m build --no-isolation`.
