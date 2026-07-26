# Contributing to fastapi-limitex

Thanks for your interest in improving `fastapi-limitex`! Contributions of all
kinds are welcome: bug reports, documentation, tests and features.

## Development setup

The project uses [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Yura2108/fastapi-limitex
cd fastapi-limitex
uv sync --all-extras
```

This installs the library, every optional backend and all development tools into
a local virtual environment.

## Quality gates

All of the following must pass before a change can be merged. They run in CI on
Python 3.10–3.13 and you should run them locally first:

```bash
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy                  # strict type checking
uv run pytest                # tests + coverage
```

To format your code, run `uv run ruff format .`.

## Coding standards

- **Absolute imports only.** Relative imports are rejected by ruff.
- **No inline comments.** Explain intent with docstrings on modules, classes and
  functions instead.
- **Full type coverage.** The package is typed and checked with `mypy --strict`;
  new code must be fully annotated.
- **Tests are required.** New behaviour needs tests, and the suite must keep its
  high coverage.

## Adding a storage backend

Implement the async primitives defined by
`fastapi_limitex.backends.base.BaseStorage`. Counter primitives power the fixed
and sliding window strategies, the log primitives power the moving window
strategy, and `take_token` powers the token bucket strategy. If your backend
cannot support an operation, raise `UnsupportedOperationError` from it.

## Adding a strategy

Subclass `fastapi_limitex.strategies.base.RateLimitStrategy`, implement `hit`
and `peek`, and register the class in `fastapi_limitex/strategies/__init__.py`.

## Releasing (maintainers)

Publishing uses PyPI [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
via OpenID Connect, so no API tokens are stored.

One-time setup:

1. Create the `fastapi-limitex` project on PyPI.
2. Add a trusted publisher pointing to this repository, the `publish.yml`
   workflow and a GitHub environment named `pypi`.
3. Create the `pypi` environment in the repository settings.

To cut a release:

1. Bump the version in `pyproject.toml` and `fastapi_limitex/__init__.py`.
2. Update `CHANGELOG.md`.
3. Create a GitHub release with a `vX.Y.Z` tag. The `publish.yml` workflow builds
   the distributions and uploads them to PyPI.

## Reporting bugs

Please open an issue with a minimal reproduction, the versions of Python,
`fastapi-limitex` and the backend you use, and the observed vs. expected
behaviour.

By contributing you agree that your contributions are licensed under the
project's [MIT license](LICENSE).
