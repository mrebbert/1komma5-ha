# Contributing to 1komma5-ha

Thanks for taking the time to look into contributing — this is a hobby project, but every clean PR or well-described bug report makes it better.

## Before opening an issue or PR

- For **questions, setup help, automation ideas**: please use [GitHub Discussions](https://github.com/mrebbert/1komma5-ha/discussions) or the [Home Assistant Community Forum](https://community.home-assistant.io/) instead of an issue.
- For **bug reports** and **feature requests**: open an issue. The repo has templates for both — please fill the requested fields (HA version, integration version, hardware, logs).
- Search [existing issues](https://github.com/mrebbert/1komma5-ha/issues?q=is%3Aissue) and [pull requests](https://github.com/mrebbert/1komma5-ha/pulls) first to avoid duplicates.

## What's in scope, what isn't

This is an **unofficial integration** built on top of an undocumented, reverse-engineered API. That has consequences:

- **In scope:** anything the [`onekommafive`](https://github.com/mrebbert/1komma5-api) Python library already exposes (live overview, prices, EV charger, EMS, optimization events, weather).
- **Out of scope:** features that would require backend changes by 1KOMMA5° (we don't have control over the API), and features that need data fields the API doesn't return.
- **Hardware-specific oddities:** I only have one system to test against. PRs that add hardware-specific handling are welcome but should default to behaving correctly for systems that don't have that hardware.

If you're unsure whether your idea fits, open a Discussion before writing code.

## Local development setup

Requires **Python 3.13** (matches the Home Assistant runtime) and `git`.

```bash
git clone https://github.com/mrebbert/1komma5-ha
cd 1komma5-ha

# Create a virtual environment for tooling and run the tests
python3.13 -m venv .venv
.venv/bin/pip install -e ".[test]" ruff pre-commit

# Activate pre-commit hooks for automatic ruff lint/format on every commit
.venv/bin/pre-commit install

# Run the unit tests (Tier 1 — pure helpers only, no HA install needed)
.venv/bin/pytest
```

The `.venv/` directory is gitignored — it stays local.

### Running the linters and formatter

`ruff` is the single source of truth for lint and format; pre-commit runs it automatically. To run manually:

```bash
.venv/bin/pre-commit run --all-files     # Recommended (matches CI exactly)
.venv/bin/ruff check custom_components/ tests/
.venv/bin/ruff format custom_components/ tests/
```

Why `pre-commit run` over plain `ruff`? The pre-commit config pins a specific ruff version; CI uses the same. Calling `ruff` from a fresh `pip install` may format slightly differently and create churn.

## Testing

Tier 1 tests cover the pure helpers in `custom_components/onekommafive/helpers.py` (price slot lookup, forecast building, optimization aggregation, cheapest/most-expensive-window search, trapezoidal integration, active-event lookup). They run in milliseconds and don't require Home Assistant to be installed.

```bash
.venv/bin/pytest                                                   # all tests
.venv/bin/pytest tests/test_helpers.py::TestGetCurrentPrice -v     # one class
.venv/bin/pytest --cov=custom_components/onekommafive --cov-report=term-missing
```

Tier 2 tests (full HA stack via `pytest-homeassistant-custom-component`) are intentionally not set up — keeping the test environment lightweight is more valuable than coverage of thin platform glue for a hobby project.

If you change a pure helper or add one, please add tests under `tests/test_helpers.py`. If you change behaviour that's already covered, don't loosen existing tests just to make a change pass.

## Pull request workflow

1. **Branch from `main`**: `git checkout -b feat/some-short-name` (or `fix/...`, `docs/...`, `chore/...`).
2. **Keep PRs small.** One concern per PR — easier to review and revert if needed.
3. **Run the test suite and pre-commit locally** before pushing.
4. **Update the docs** if you change user-visible behaviour: `README.md`, `dashboard/README.md`, translations under `custom_components/onekommafive/strings.json` and `translations/`.
5. **Add a CHANGELOG entry** under `## [Unreleased]` (Keep-a-Changelog format). Don't bump the version in `manifest.json` — that happens at release time.
6. **Open the PR** against `main`. The repo runs three checks automatically: `Validate` (HACS + hassfest), `Tests` (pytest + ruff), `CodeQL` (security and code-quality). All three should pass.

## Translations

The integration ships German (`strings.json` and `translations/de.json`) and English (`translations/en.json`). When you add a new entity, service or config-flow string:

1. Add the new key to `strings.json` (German is the primary file).
2. Mirror the key in `translations/de.json` and `translations/en.json`.
3. The translation parity test in `tests/test_translations.py` will fail if any locale is missing keys — run `.venv/bin/pytest tests/test_translations.py` to verify.

## Releases

Releases are cut by the maintainer. There's no obligation for contributors to bump versions or tag — just leave the PR with `[Unreleased]` notes and the maintainer will roll them into the next release.

## Code style notes

- The integration uses Python 3.12+ syntax (`type` aliases, PEP 695 generics, `datetime.UTC`).
- All API calls go through `hass.async_add_executor_job` — the `onekommafive` library is synchronous (`requests` underneath).
- Keep the pure helpers in `helpers.py` actually pure — no HA imports, no I/O. They are the only easily-testable surface.
- New sensor entities should follow the description-based pattern already in use (see `sensor_descriptions.py`, `sensor_entities.py`, or `number.py:OneKomma5EVNumberDescription`).

## License

By contributing you agree that your contribution will be licensed under the [MIT License](LICENSE) of this repository.
