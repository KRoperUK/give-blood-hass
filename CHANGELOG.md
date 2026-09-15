# Changelog

This file is maintained by [release-please](https://github.com/googleapis/release-please) from
Conventional Commit messages. Do not edit it by hand.

## [1.1.0](https://github.com/KRoperUK/give-blood-hass/compare/v1.0.1...v1.1.0) (2026-09-15)


### Features

* restrict the HACS listing to the United Kingdom ([#16](https://github.com/KRoperUK/give-blood-hass/issues/16)) ([356e9ac](https://github.com/KRoperUK/give-blood-hass/commit/356e9ac0752b8cdf57a660ce0872861cb70dfac7))

## [1.0.1](https://github.com/KRoperUK/give-blood-hass/compare/v1.0.0...v1.0.1) (2026-09-15)


### Bug Fixes

* declare PARALLEL_UPDATES and back the silver quality-scale claim ([#12](https://github.com/KRoperUK/give-blood-hass/issues/12)) ([6a00ca2](https://github.com/KRoperUK/give-blood-hass/commit/6a00ca21afea61b24706c8d090bf2f466a1853ff))

## [1.0.0](https://github.com/KRoperUK/give-blood-hass/compare/v1.0.0...v1.0.0) (2026-09-15)


### Features

* NHS Give Blood integration for Home Assistant ([ff059b5](https://github.com/KRoperUK/give-blood-hass/commit/ff059b5b0d5c2b8c063f244d6cb2839570788126))


### Bug Fixes

* **ci:** distinguish a missing pip from a missing release in the preflight ([1dc86d4](https://github.com/KRoperUK/give-blood-hass/commit/1dc86d4bea443242d0fb865e0b3f82b308589710))
* **ci:** make the library preflight check actually resolve against PyPI ([132b48b](https://github.com/KRoperUK/give-blood-hass/commit/132b48b81858d0cc53d5e9d4f40027f90fb2ea71))
* satisfy hassfest and unblock the CI security job ([f9420d3](https://github.com/KRoperUK/give-blood-hass/commit/f9420d39be9019eb2c2cbad8f102d0de2c0aeb91))
* ship brand assets so HACS validation passes ([fe9fb6e](https://github.com/KRoperUK/give-blood-hass/commit/fe9fb6e6114acfb7b047c3f0217a34a8198f0c81))
* stop ruff rewriting maintainer scripts into Python 3.14-only syntax ([12c699a](https://github.com/KRoperUK/give-blood-hass/commit/12c699a24467317af15bbbf5d91ec53a7e9667be))


### Miscellaneous Chores

* pin the first release to 1.0.0 ([12e9e68](https://github.com/KRoperUK/give-blood-hass/commit/12e9e6866f3391cff9b1106d741e7f9c606d4756))

## 1.0.0 (unreleased)

Initial release.

### Features

- Config flow with credential validation, reauthentication, and an options flow for the poll interval
  and donation-history toggle.
- Donor accounts are keyed by donor ID rather than email address, so changing the email in the app does
  not create a duplicate entry, and reauthenticating against a different account is refused.
- Calendar entity for booked appointments, with durations estimated per procedure type.
- 18 sensors: appointments, eligibility and booking dates, credits, award progress, donation history,
  blood group, donor messages and nearest plasma venue.
- 6 binary sensors: appointment booked, eligible to donate, booking-system outage, data degradation,
  Platelet Plus and pending email change.
- Adaptive polling: backs off to 4-hourly on sustained failure, and restores the configured interval on
  recovery.
- Token persistence across restarts, with a password fallback so NHSBT's refresh-token rotation does not
  require manual reauthentication.
- Degraded snapshots keep core entities available when a supplementary endpoint fails, with the failed
  endpoints surfaced on a diagnostic sensor.
- Diagnostics built from an allowlist of non-identifying fields, with the donor ID reported as a
  truncated hash.

### Notes

- Read-only by design. See [Why it is read-only](README.md#why-it-is-read-only).
- Requires Home Assistant 2026.8.0 or newer.
