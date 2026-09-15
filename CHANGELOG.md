# Changelog

This file is maintained by [release-please](https://github.com/googleapis/release-please) from
Conventional Commit messages. Do not edit it by hand.

## [1.1.0](https://github.com/KRoperUK/give-blood-hass/compare/v1.0.0...v1.1.0) (2026-09-15)


### Features

* NHS Give Blood integration for Home Assistant ([ff059b5](https://github.com/KRoperUK/give-blood-hass/commit/ff059b5b0d5c2b8c063f244d6cb2839570788126))

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
