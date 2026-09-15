# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for anything that could expose donor data or credentials.

Use GitHub's private reporting:
[Report a vulnerability](https://github.com/KRoperUK/give-blood-hass/security/advisories/new)

Include what you can reproduce and what data it exposes. I'll acknowledge within a week.

## Scope

This is an unofficial Home Assistant integration for NHS Blood and Transplant's private API.

**In scope** — issues in this repository's code:

- donor PII appearing in an entity state or attribute, the device registry, diagnostics, or logs
- credentials appearing anywhere other than the config entry
- a write operation reaching the integration (it is deliberately read-only — see
  [Design decisions](https://give-blood-hass.kroper.uk/design/#why-read-only))
- authentication failures misclassified such that a transient outage triggers a credential prompt, or a
  dead credential is retried silently forever
- a dependency vulnerability reachable through this integration

**Out of scope:**

- vulnerabilities in NHSBT's own systems. Report those to
  [NHS Blood and Transplant](https://www.nhsbt.nhs.uk/) directly, not here. Please do not test against
  their infrastructure on this project's behalf.
- the config entry storing credentials unencrypted. Home Assistant's `.storage` is unencrypted by
  design and every cloud-polling integration is affected equally; see
  [Privacy](https://give-blood-hass.kroper.uk/privacy/#what-is-stored).
- the static application key in the client library. It ships in a publicly downloadable APK,
  identifies the *application* rather than any user, and authorises nothing on its own.

## What this integration handles

It stores your NHS Give Blood email address, password and API tokens in its config entry, and its API
responses contain your name, address, phone number, date of birth and donor ID.

Design measures:

- **No PII in entities.** No name, address, phone number, date of birth, donor ID or email address is
  published as a state or attribute. Venue addresses are, because locating your appointment is the point.
- **The device is named "NHS Give Blood"**, not after you — device names appear in logs, diagnostics and
  screenshots.
- **Diagnostics use an allowlist, not a redaction list.** Only explicitly non-identifying fields are
  included; your donor ID appears as a truncated hash and venues are reduced to capability flags. An
  allowlist fails safe when the upstream API adds a field, which — being reverse-engineered — it will.
- **Credentials never appear in diagnostics**, at any level of detail, only as presence booleans.
- **Read-only.** A repository test fails if any module references a booking, reschedule or cancel call.

Two tests enforce the PII guarantees, one against synthetic fixtures and one against a **real account**,
searching for the actual values from the live payload plus anything merely shaped like contact detail.

## If you think your data leaked

1. Change your NHS Give Blood password in the app — that invalidates the stored tokens.
2. Delete and re-add the integration.
3. Purge affected recorder history with `recorder.purge_entities`.
4. Report it privately using the link above.

## Supported versions

The latest released version. Fixes go into a new release rather than being backported.
