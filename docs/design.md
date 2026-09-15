# Design decisions

The non-obvious choices, and why.

## Why read-only

The NHS Give Blood API can book, reschedule and cancel appointments, and the
[`nhs-give-blood`](https://github.com/KRoperUK/give-blood-py) library implements all three. This
integration exposes none of them.

Cancelling an appointment releases a real slot at a real NHS donation centre, immediately and
irreversibly. It may be taken by another donor within minutes. Booking one commits clinical staff time.

Behind a Home Assistant entity or action, that becomes reachable by:

- any automation with a wrong condition,
- any script triggered by a misfired template,
- anything with access to the service call API.

Reading data has no failure mode worse than a stale sensor. Writing has a failure mode measured in
wasted donation slots. Those belong in different risk classes, and the same interface should not cover
both.

A repository test enforces this — `tests/test_repo_hygiene.py::TestNoWriteOperations` fails if any module
so much as references a write method. It is load-bearing, not decorative.

If you want to script bookings, the library's CLI requires an explicit `--yes` on every write:

```bash
pip install nhs-give-blood
give-blood appointments
give-blood cancel APPT123 --yes
```

## Why the password is stored

The API issues a ~30-minute access token plus a refresh token, and **rotates the refresh token** on each
use. Storing only tokens would mean that any rejected rotation — a missed refresh, a server-side
invalidation, a long Home Assistant downtime — leaves the integration dead until you happen to notice a
reauthentication prompt.

Storing the password lets it recover on its own. The auth ladder is: reuse a fresh token → refresh →
password login.

The trade-off is explicit: a recoverable integration versus one credential stored in
`.storage/core.config_entries`. Every cloud-polling integration that offers unattended recovery makes the
same trade.

## Why accounts are keyed by donor ID

The config entry's `unique_id` is the `donor_id` claim from the access token, not the email address.

Email addresses change. Keying on one would let the same account be added twice after a change in the
app, producing two devices and two sets of entities for one donor.

It also makes a specific mistake detectable: re-authenticating an existing entry with credentials for a
*different* account is refused. Allowing it would keep every entity ID and all its history while
silently repointing them at another person — the worst kind of bug, because nothing appears to break.

## Why entity IDs are keyed by donor ID too

Unique IDs are `{donor_id}_{key}` rather than the more common `{entry_id}_{key}`.

Entry IDs are regenerated when you remove and re-add an integration. Donor IDs are not. Keying on the
donor means your history, customisations and dashboard references survive a re-add.

## Why one aggregate read per poll

The coordinator makes a single call — `async_get_snapshot()` — which fetches the account payload and then,
concurrently, appointments, messages, feature flags, the failover banner and donation history.

**Supplementary failures degrade rather than propagate.** A flaky feature-flag endpoint leaves that field
`None` and records the endpoint name, instead of blanking every entity. The account payload is the only
mandatory read, because without it there is nothing to render at all.

`binary_sensor.nhs_give_blood_data_degraded` surfaces this, with the failed endpoint names in an
attribute.

## Why `unknown` instead of `off`

`binary_sensor.nhs_give_blood_booking_system_problem` reports `unknown` when the failover check itself
failed, rather than `off`.

`off` would be a false all-clear: an automation gated on "booking system is fine" would proceed on the
strength of a check that never completed. `unknown` is honest and fails safe.

## Why eligibility is compared by date

The API returns eligibility as a midnight boundary. Comparing full timestamps would report "not eligible"
for the whole of the day you actually become eligible.

`binary_sensor.nhs_give_blood_eligible_to_donate` compares dates, so it turns on at the start of the
eligible day.

## Why there is no "days until appointment" sensor

A duration sensor derived from a timestamp changes state daily, which fills the recorder database with
values that carry no new information. A timestamp sensor plus a template gives the same answer with more
flexibility — see [Automations](automations.md#countdown-to-the-next-appointment).

## Attribute size

Home Assistant's recorder **silently discards an entity's entire attribute dictionary** when the
serialised JSON exceeds 16,384 bytes. Nothing is logged, the entity looks healthy in memory, and the
attributes are gone after a restart.

Every list-valued attribute here goes through a budget check that halves the largest list until the
payload fits, preferring a truncated list (flagged with `truncated: true`) over losing every attribute on
the entity. Caps are applied first so the common case never needs truncating: 10 appointments, 20
donations, 10 messages.

A test asserts every entity stays under budget, including one that runs against a real account.

## Why the app's own headers are sent

The client sends `ApiKey`, `Nhsbt-Client-Type`, `Nhsbt-Client-Version` and a cache-busting trio on every
request. None of it is decoration:

- Without the API key, requests fail.
- Feature flags and the failover banner vary by client type and version.
- Without the cache headers, intermediary caches return stale bodies.

The API key is a fixed value shipped in a publicly downloadable APK. It identifies the *application*, not
any user, and authorises nothing on its own — the donor's Bearer token does all the authorisation.

## Update interval

30 minutes by default, with automatic backoff to 4 hours on sustained failure.

Donor data changes on the order of days. Polling faster mostly asks a public health service for data that
cannot have changed. See [Configuration](configuration.md#update-interval).

## Two repositories

| Repository | Contents |
|---|---|
| [give-blood-py](https://github.com/KRoperUK/give-blood-py) | All protocol, auth, retry, model and exception logic |
| [give-blood-hass](https://github.com/KRoperUK/give-blood-hass) | All Home Assistant-specific modelling, naming, availability and device-registry logic |

The library has no Home Assistant dependency and is independently useful — it ships a CLI and documents
the API itself. The integration pins it as a **floor** rather than an exact version, so patch releases
reach users without a release here; version-compatibility shims are confined to a single adapter module.
