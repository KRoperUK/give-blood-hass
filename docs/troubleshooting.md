# Troubleshooting

## Enable debug logging first

```yaml
logger:
  default: info
  logs:
    custom_components.nhs_give_blood: debug
    nhs_give_blood: debug
```

Neither logger records credentials or tokens.

---

## "Reconfigure NHS Give Blood" keeps appearing

**Most likely:** your password changed. Check it works in the app, then reconfigure.

**Also possible:** NHSBT invalidated the refresh token *and* the stored password is stale.

**If it happens during a known NHSBT outage, that's a bug.** Transient failures are supposed to retry
silently — the integration classifies a 5xx or 429 from the auth service as *transient* rather than a
credential problem, precisely to avoid this. Please
[open an issue](https://github.com/KRoperUK/give-blood-hass/issues) with diagnostics.

## Everything is `unavailable`

The last update failed.

1. Check `binary_sensor.nhs_give_blood_booking_system_problem`
2. Check <https://my.blood.co.uk> in a browser
3. Look for `Could not reach the NHS Give Blood API` in the log

During an outage the integration backs off to 4-hourly polls and restores your configured interval as soon
as a poll succeeds. No action is needed.

To retry immediately: **Settings → Devices & services → NHS Give Blood → ⋮ → Reload**.

## Some sensors are `unknown` but others work

A supplementary endpoint failed while the main account read succeeded — the integration degrades rather
than blanking everything.

Enable `binary_sensor.nhs_give_blood_data_degraded`; its `degraded_endpoints` attribute names which one.

| Degraded endpoint | Affected entities |
|---|---|
| `messages` | Donor messages |
| `features` | (none currently surfaced) |
| `failover` | Booking system problem |
| `donations` | Last donation, donations recorded |
| `appointments` | Falls back to the copy in the account payload |

## `last_donation` and `donations_recorded` are `unknown`

Either **Fetch donation history** is off in the options, or the account has no recorded donations.

## `donations_recorded` looks too low

It is a lower bound. The API truncates long histories and reports `history_truncated: true` in the
attributes. Use `sensor.nhs_give_blood_donation_credits` for your real lifetime total.

## Eligibility dates look wrong

Check which sensor you are reading:

| Sensor | Meaning |
|---|---|
| `eligible_from` | When you can next **donate** — clinical deferral only |
| `can_book_from` | When you can next **book** — also accounts for booking windows and existing appointments |

They routinely differ by weeks. This is the API's behaviour, not the integration's.

## The calendar is empty but I have an appointment booked

1. Check `sensor.nhs_give_blood_upcoming_appointments` — if it is `0`, the API is not returning the
   appointment
2. Check it appears in the NHS Give Blood app
3. Reload the integration

The API only exposes *future* appointments, so a calendar query for a past range legitimately returns
nothing.

## Reauthentication rejected with "different donor account"

Those credentials belong to another account. Add it as a **separate** integration entry.

This is deliberate: reusing the existing entry would keep every entity ID and all its history while
silently repointing them at a different person.

## `already_configured` when adding the integration

That donor account is already set up. Accounts are keyed by donor ID rather than email address, so changing
your email in the app does not let you add it twice.

## Distances are in kilometres and I expected miles

The API reports distances without a unit; the app renders them as miles, so that is what the integration
declares. Home Assistant then converts to your instance's unit system.

To change it: **Settings → System → General → Unit system**. Or override per entity via the entity's
settings.

## Attributes disappear after a restart

If you see this, please [report it](https://github.com/KRoperUK/give-blood-hass/issues) — it is the
signature of Home Assistant's recorder rejecting an oversized attribute payload, and the integration is
built to stay under that limit. Include the entity ID and its attributes.

## Setup hangs or times out

The API can be slow under load. Setup allows 30 seconds per request with up to three retries on transient
statuses. If it consistently fails:

1. Confirm you can sign in at <https://my.blood.co.uk>
2. Check whether your network blocks the host
3. Try again in a few minutes — NHSBT applies rate limits

## Still stuck

[Open an issue](https://github.com/KRoperUK/give-blood-hass/issues) with:

- Home Assistant version
- Integration version (**Settings → Devices & services → NHS Give Blood**)
- The diagnostics download — please read it first; see [Privacy](privacy.md#diagnostics)
- Relevant debug log lines

Or check the [library's troubleshooting notes](https://github.com/KRoperUK/give-blood-py#troubleshooting)
if the problem looks like an API-level one.
