# NHS Give Blood for Home Assistant

Brings your NHS blood donation account into Home Assistant: appointments, eligibility dates, donation
credits and awards.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=give-blood-hass&category=integration)
[![Docs](https://img.shields.io/badge/docs-give--blood--hass.kroper.uk-c8102e)](https://give-blood-hass.kroper.uk)
[![HACS](https://img.shields.io/badge/HACS-custom-orange)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-blue)](https://www.home-assistant.io)
[![Licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

📖 **Full documentation: [give-blood-hass.kroper.uk](https://give-blood-hass.kroper.uk)**

**Unofficial.** This talks to the private API behind the [NHS Give Blood app](https://www.blood.co.uk/nhsgivebloodapp).
NHS Blood and Transplant does not publish, support or endorse it, and can change or break it at any
time.

## Contents

- [What you get](#what-you-get)
- [Install](#install)
- [Set up](#set-up)
- [Entities](#entities)
- [Automation examples](#automation-examples)
- [Options](#options)
- [Why it is read-only](#why-it-is-read-only)
- [Privacy](#privacy)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

| Documentation | |
|---|---|
| [Installation](https://give-blood-hass.kroper.uk/installation/) | HACS and manual install, multiple accounts |
| [Configuration](https://give-blood-hass.kroper.uk/configuration/) | Poll interval, backoff, logging |
| [Entities](https://give-blood-hass.kroper.uk/entities/) | Full reference with attributes |
| [Automations](https://give-blood-hass.kroper.uk/automations/) | Worked examples and dashboard cards |
| [Design decisions](https://give-blood-hass.kroper.uk/design/) | Why read-only, why the password is stored |
| [Privacy](https://give-blood-hass.kroper.uk/privacy/) | What is stored, and what never leaves |
| [Troubleshooting](https://give-blood-hass.kroper.uk/troubleshooting/) | |

## What you get

- **A calendar** of your booked donation appointments, so "remind me the evening before" is a two-line
  automation.
- **Eligibility dates** — when you can next donate, and when you can next book. These are different
  dates and the integration keeps them separate.
- **Award progress** — current tier, next milestone, and how many credits to go.
- **Donation history** — date and venue of your most recent donations.
- **Targeted donor messages** for your blood group, filtered from the API's all-groups feed.
- **A booking-system outage sensor**, so an automation can tell "nothing booked" from "NHSBT is down".

## Install

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=give-blood-hass&category=integration)

Already running HACS? The button above opens it on your own instance with this repository and the
**Integration** category pre-filled. Otherwise add it by hand:

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/KRoperUK/give-blood-hass`, category **Integration**
3. Install **NHS Give Blood**, then restart Home Assistant

### Manual

Copy `custom_components/nhs_give_blood/` into your `config/custom_components/` directory and restart.

Requires Home Assistant 2026.8 or newer. The
[`nhs-give-blood`](https://github.com/KRoperUK/give-blood-py) library is installed automatically.

HACS only offers this to instances with their country set to the United Kingdom (`hacs.json` sets
`country: GB`). NHS Blood and Transplant serves England and north Wales, so an account cannot be held
from elsewhere — see [the installation guide](https://give-blood-hass.kroper.uk/installation/) for the
detail.

## Set up

**Settings → Devices & services → Add integration → NHS Give Blood**

Enter the email address and password you use for the NHS Give Blood app.

Both are stored in your Home Assistant config entry. The password is kept deliberately: NHSBT rotates
refresh tokens, and when a stored one is rejected the integration logs in again rather than going
unavailable until you notice. Without it, every rotation would need a manual reauthentication.

One config entry per donor account. Accounts are keyed by donor ID rather than email address, so
changing your email in the app does not create a duplicate.

## Entities

One device per donor account.

### Calendar

| Entity | Notes |
|---|---|
| `calendar.nhs_give_blood_appointments` | Booked appointments. Duration is estimated by procedure: 60 min whole blood, 90 min plasma, 120 min platelets. |

### Sensors

| Entity | Example | Notes |
|---|---|---|
| `sensor.nhs_give_blood_next_appointment` | `2026-10-08T17:30:00+01:00` | Timestamp. Attributes carry venue, address, coordinates and the full upcoming list. |
| `sensor.nhs_give_blood_next_appointment_venue` | `Testville, Example Donor Centre (Main Hall)` | |
| `sensor.nhs_give_blood_upcoming_appointments` | `2` | |
| `sensor.nhs_give_blood_eligible_from` | `2026-09-28T00:00:00+01:00` | When you can next **donate** (clinical deferral). |
| `sensor.nhs_give_blood_can_book_from` | `2026-11-07T00:00:00+00:00` | When you can next **book**. Not the same date. |
| `sensor.nhs_give_blood_donation_credits` | `15` | Lifetime credits. Authoritative. |
| `sensor.nhs_give_blood_award_level` | `Bronze` | |
| `sensor.nhs_give_blood_next_award` | `Silver` | Threshold in attributes. |
| `sensor.nhs_give_blood_credits_to_next_award` | `10` | |
| `sensor.nhs_give_blood_total_awards` | `6` | |
| `sensor.nhs_give_blood_last_donation` | `2026-09-14T00:00:00+01:00` | |
| `sensor.nhs_give_blood_blood_group` | `A-` | |
| `sensor.nhs_give_blood_donor_messages` | `1` | Filtered to your blood group; bodies in attributes. |
| `sensor.nhs_give_blood_nearest_plasma_venue` | | Disabled by default. |
| `sensor.nhs_give_blood_nearest_plasma_venue_distance` | `9.9 mi` | Disabled by default. |

Diagnostic: `donations_recorded`, `donation_type`, `registered_since`.

> `donations_recorded` is a **lower bound**. The API truncates long histories and flags it as
> `history_truncated` in the attributes. Use `donation_credits` for your real total.

### Binary sensors

| Entity | Notes |
|---|---|
| `binary_sensor.nhs_give_blood_appointment_booked` | |
| `binary_sensor.nhs_give_blood_eligible_to_donate` | Compared by date, so it turns on at the start of the eligible day. |
| `binary_sensor.nhs_give_blood_booking_system_problem` | Diagnostic. `unknown` when the check itself failed, rather than a false all-clear. |
| `binary_sensor.nhs_give_blood_data_degraded` | Diagnostic, disabled by default. Names the failed endpoints. |
| `binary_sensor.nhs_give_blood_platelet_plus` | Diagnostic, disabled by default. |
| `binary_sensor.nhs_give_blood_email_change_pending` | Diagnostic, disabled by default. |

## Automation examples

Remind yourself the evening before an appointment:

```yaml
automation:
  - alias: Blood donation tomorrow
    triggers:
      - trigger: calendar
        entity_id: calendar.nhs_give_blood_appointments
        event: start
        offset: "-16:00:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: Donating tomorrow
          message: >-
            {{ trigger.calendar_event.summary }} at
            {{ trigger.calendar_event.location }},
            {{ trigger.calendar_event.start | as_datetime | as_local
               | strftime('%H:%M') }}. Eat well and drink plenty of water.
```

Nudge yourself when you become eligible with nothing booked:

```yaml
automation:
  - alias: Eligible to donate with nothing booked
    triggers:
      - trigger: state
        entity_id: binary_sensor.nhs_give_blood_eligible_to_donate
        to: "on"
        for: "24:00:00"
    conditions:
      # Don't nag during an NHSBT outage — there would be nothing to act on.
      - condition: state
        entity_id: binary_sensor.nhs_give_blood_appointment_booked
        state: "off"
      - condition: state
        entity_id: binary_sensor.nhs_give_blood_booking_system_problem
        state: "off"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            You can donate again. Nothing booked yet —
            {{ states('sensor.nhs_give_blood_credits_to_next_award') }} credit(s)
            to {{ states('sensor.nhs_give_blood_next_award') }}.
```

Both guard against `unknown` and `unavailable` by triggering on explicit states rather than templating
over values that may not exist yet.

## Options

**Settings → Devices & services → NHS Give Blood → Configure**

| Option | Default | Range |
|---|---|---|
| Update interval | 30 minutes | 5–1440 minutes |
| Fetch donation history | on | — |

Donor data changes on the order of days. The default already makes a booking made in the app appear
promptly; polling faster mostly asks a public health service for data that cannot have changed. On
sustained failure the interval backs off automatically to a maximum of 4 hours, and returns to your
setting once the API recovers.

Turning off donation history drops one request per update and leaves `last_donation` and
`donations_recorded` unavailable.

## Why it is read-only

The API can book, reschedule and cancel appointments, and the underlying library implements all three.
This integration deliberately exposes none of them.

A cancelled appointment releases a real slot at a real NHS donation centre, immediately and
irreversibly, and it may be taken by another donor. Behind a Home Assistant entity or action, that
becomes reachable by any automation, script or misfired template — a materially different risk from
reading data.

If you want to script bookings, use the library's CLI, where every write requires an explicit `--yes`:

```bash
pip install nhs-give-blood
give-blood appointments
give-blood cancel APPT123 --yes
```

## Privacy

Every account endpoint in this API returns your name, address, phone number, date of birth and donor
ID. The integration is built so that data does not leak into places you would not expect:

- **Entities expose none of it.** No name, address, phone number or date of birth is published as a
  state or attribute. Venue addresses appear on appointment entities, because that is the point of them.
- **The device is named "NHS Give Blood"**, not your name — device names appear in logs, diagnostics and
  screenshots.
- **Diagnostics are built from an allowlist**, not a redaction list. Only explicitly non-identifying
  fields are included, your donor ID appears as a truncated hash, and venues are reduced to capability
  flags. An allowlist fails safe when NHSBT adds a field; a redaction list fails open.
- **Credentials never appear in diagnostics**, at any level of detail — only whether they are present.

Diagnostics are still worth reading before you attach them to a public issue.

## Troubleshooting

**"Reconfigure NHS Give Blood" keeps appearing.** Your password has probably changed. Check it in the
app, then reconfigure. If it appears during a known NHSBT outage instead, that is a bug — please open
an issue with diagnostics, because transient failures are supposed to retry silently.

**Everything is `unavailable`.** The last update failed. Check
`binary_sensor.nhs_give_blood_booking_system_problem` and https://my.blood.co.uk. The integration backs
off to 4-hourly polls during an outage and recovers on its own.

**Some sensors are `unknown` but others work.** A supplementary endpoint failed. Enable
`binary_sensor.nhs_give_blood_data_degraded` — its attributes name which one.

**`last_donation` is `unknown`.** Either "Fetch donation history" is off, or your account has no
recorded donations yet.

**Eligibility dates look wrong.** Check you are reading the right one: `eligible_from` is the clinical
deferral date, `can_book_from` also accounts for booking windows and existing appointments. They
routinely differ by weeks.

**Reauthentication is rejected with "different donor account".** Those credentials belong to another
account. Add it as a separate integration entry instead — reusing this one would silently repoint every
existing entity at a different person.

**Enable debug logging:**

```yaml
logger:
  default: info
  logs:
    custom_components.nhs_give_blood: debug
    nhs_give_blood: debug
```

## Development

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pre-commit install

pytest
ruff check . && ruff format --check .
mypy
bandit -c bandit.yaml -r custom_components
```

Tests patch the API adapter rather than HTTP — the library's own suite covers transport, retries and
auth. All fixtures are synthetic; `tests/test_repo_hygiene.py`, `scripts/check_pii.py`, bandit and
detect-secrets all guard against real data entering the repo.

Documentation is built with [Zensical](https://zensical.org) and deployed to
[give-blood-hass.kroper.uk](https://give-blood-hass.kroper.uk) on every push to `main`:

```bash
pip install zensical
zensical serve     # live preview
zensical build     # writes ./site
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT. Not affiliated with, endorsed by, or supported by NHS Blood and Transplant.

Please keep donating. 🩸
