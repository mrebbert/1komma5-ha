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

Tier 2 tests use a real Home Assistant instance via `pytest-homeassistant-custom-component`. They live under `tests/integration/` and exercise the config flow, coordinators and services with the `onekommafive` library mocked. The dependency group is heavier (HA itself plus a numpy / sqlalchemy stack), so it is opt-in:

```bash
.venv/bin/pip install -e ".[test-integration]"
.venv/bin/pytest tests/integration -v
```

If you change a pure helper or add one, please add tests under `tests/test_helpers.py`. For platform changes (sensor classes, coordinators, config flow), add tests under `tests/integration/`. If you change behaviour that's already covered, don't loosen existing tests just to make a change pass.

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

### Release cadence (maintainer reference)

The repo uses a two-branch model to keep HACS-user release noise low:

- **`main`** — hot branch. Every commit lands here; CI runs Validate + Tests + CodeQL on push. **No tags from main** under normal circumstances.
- **`release/next`** — release branch. Tags and GitHub Releases originate here only.

A scheduled workflow (`.github/workflows/cadence.yml`) runs every **Sunday 20:00 UTC** (Monday morning EU time for HACS users). It:

1. Checks whether `main` is ahead of `release/next`. If not, logs `nothing to release` and exits.
2. Reads `version` from `custom_components/onekommafive/manifest.json`.
3. If a tag `vX.Y.Z` for that version already exists, the cadence logs a warning and skips — `main` has commits but `manifest.json` was not bumped, so there's no new release to cut.
4. If `release-notes/vX.Y.Z.md` is missing, the workflow fails loudly so notes don't accidentally ship empty.
5. Otherwise: fast-forwards `release/next` from `main`, builds the zip, creates the GitHub Release with the curated notes file as body and the zip attached.

To get changes into the next cadence release, **on `main` before Sunday 20:00 UTC**:

1. Bump `version` in `custom_components/onekommafive/manifest.json`.
2. Rotate the CHANGELOG: move the `## [Unreleased]` block to `## [X.Y.Z] - YYYY-MM-DD`.
3. Add `release-notes/vX.Y.Z.md` with the curated release body.
4. Commit + push.

The workflow can also be triggered manually via Actions → Release cadence → "Run workflow" (e.g. for testing).

#### Hotfix lane (bypasses the cadence)

When something is broken and waiting for Sunday isn't acceptable:

1. Push the fix to `main` as usual.
2. Manually tag `vX.Y.Z` on `main` HEAD: `git tag vX.Y.Z && git push --tags`.
3. Manually create the GitHub Release in the UI pointing at that tag — `.github/workflows/release.yml` fires on the `release: published` event and attaches the zip.
4. The next Sunday cadence run fast-forwards `release/next` past the hotfix tag, no conflict.

## Code style notes

- The integration uses Python 3.12+ syntax (`type` aliases, PEP 695 generics, `datetime.UTC`).
- All API calls go through `hass.async_add_executor_job` — the `onekommafive` library is synchronous (`requests` underneath).
- Keep the pure helpers in `helpers.py` actually pure — no HA imports, no I/O. They are the only easily-testable surface.
- New sensor entities should follow the description-based pattern already in use (see `sensor_descriptions.py`, `sensor_entities.py`, or `number.py:OneKomma5EVNumberDescription`).

## License

By contributing you agree that your contribution will be licensed under the [MIT License](LICENSE) of this repository.
