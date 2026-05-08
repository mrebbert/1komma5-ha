# Security Policy

## Supported versions

Only the latest released version on `main` receives security fixes. If you are running an older release, please update first; the integration is updated through HACS and follows semantic-version-style tags.

| Version | Supported          |
|---------|--------------------|
| Latest release on `main` | yes |
| Older releases | no |

## Reporting a vulnerability

**Please do not open a public issue for security problems.** Use one of the following private channels:

- **Preferred:** [GitHub Security Advisory](https://github.com/mrebbert/1komma5-ha/security/advisories/new) — encrypted, private, lets us coordinate a fix and assign a CVE if appropriate.
- Alternative: a private DM via the [Home Assistant Community Forum](https://community.home-assistant.io/u/mrebbert) addressed to the same maintainer.

Please include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept if possible.
- Your Home Assistant version and the integration version (`manifest.json`).

You can expect an initial response within roughly a week. This is a hobby project — there is no formal SLA, but credible reports get priority.

## Scope

This integration is an unofficial, reverse-engineered Home Assistant component. The relevant security surfaces are:

- **In scope:** issues in the integration code itself (`custom_components/onekommafive/`), the `onekommafive` Python library it depends on, and the published GitHub releases.
- **Out of scope:** vulnerabilities in Home Assistant core, in HACS, or in the 1KOMMA5° backend / API. Please report those to the respective upstream projects.

## Credential handling

The integration stores 1KOMMA5° account credentials in the Home Assistant config entry. Home Assistant encrypts config-entry data on disk. The integration never logs credentials and never sends them anywhere except to the official 1KOMMA5° authentication endpoint via the `onekommafive` library.

If you are aware of a way credentials could leak (logs, diagnostics, traffic on the wire), that is in scope.
