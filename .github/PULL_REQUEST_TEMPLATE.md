<!--
Thanks for opening a pull request!

A few quick reminders (full guide in CONTRIBUTING.md):
- Run `pre-commit run --all-files` and `pytest` locally — the same checks
  run in CI (Validate, Tests, CodeQL).
- Add a CHANGELOG entry under `## [Unreleased]`. Don't bump the version
  in `manifest.json` — that happens at release time.
- For new entities/services: update `strings.json` plus all locales in
  `translations/`.
-->

## Summary

<!-- What does this PR change? Why? Link to a related issue if there is one. -->

## Type of change

<!-- Tick the one that applies. -->

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor (no behaviour change)
- [ ] Documentation only
- [ ] Tooling / CI / chore

## How was this tested?

<!--
Describe what you ran. For pure helpers: pytest output is enough.
For platform changes: ideally a manual smoke test in a Home Assistant
instance — note the HA version and any hardware specifics that matter.
-->

## Checklist

- [ ] `pre-commit run --all-files` is clean.
- [ ] `pytest` passes locally.
- [ ] User-visible changes are reflected in `README.md` and (where applicable) `dashboard/README.md`.
- [ ] Translation parity: every new key in `strings.json` is also in `translations/de.json` and `translations/en.json`.
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`.
