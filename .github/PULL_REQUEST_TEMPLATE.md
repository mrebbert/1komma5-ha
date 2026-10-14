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

## Test-quality review (for PRs that add or change tests)

<!--
Skip this block for PRs without test changes.

Full pattern list in `project_mutation_backlog.md` / `feedback_mutation_test_patterns.md`.
These five questions catch the mutations our MagicMock-based tests used to miss.
-->

- [ ] Assertions check a **concrete value** (specific number, string, dict key), not just "something came back".
- [ ] **Boundary cases exact**: for `<` / `<=` logic, assert at `== boundary` explicitly.
- [ ] Mocks carry **only the attributes the code reads** — prefer `types.SimpleNamespace(**wanted)` over `MagicMock` wherever the test asserts something that depends on attribute presence.
- [ ] For every `if … else …` branch, **both sides** have a test.
- [ ] If the test defends code that could be redundant on current Python (e.g. `.replace("Z", "+00:00")` on 3.11+), consider deleting the code instead of asserting on it.
