# Entities

One device per donor account, named **NHS Give Blood** — not your name, because device names surface in
logs, diagnostics and screenshots.

Entity IDs below assume a single account. With more than one, Home Assistant appends `_2` and so on.

## Calendar

### `calendar.nhs_give_blood_appointments`

Your booked donation appointments as calendar events.

| Field | Source |
|---|---|
| Summary | `Give blood — {procedure}` |
| Start | Appointment date and time |
| End | Start plus an estimated duration |
| Location | Venue name and full address |
| Description | Procedure, venue notes (parking, step-free access), session ID |

The API gives a start time but no duration, so it is estimated per procedure:

| Procedure | Estimated duration |
|---|---|
| Whole blood | 60 minutes |
| Plasma | 90 minutes |
| Platelets | 120 minutes |

These match the app's own guidance so the calendar block roughly matches how long you will actually be
there. The entity reads `on` while an appointment is in progress and `off` otherwise.

!!! note "Only future appointments"

    The API exposes upcoming appointments only, so querying a past date range legitimately returns
    nothing. Past donations are on `sensor.nhs_give_blood_last_donation` instead.

## Sensors

### Appointments

| Entity | Type | Notes |
|---|---|---|
| `sensor.nhs_give_blood_next_appointment` | timestamp | Attributes carry venue, address, coordinates, session ID, procedure, and the full upcoming list |
| `sensor.nhs_give_blood_next_appointment_venue` | text | Venue name including sub-location |
| `sensor.nhs_give_blood_upcoming_appointments` | count | |

`next_appointment` attributes:

```yaml
venue: Testville, Example Donor Centre (Main Hall)
venue_id: TSTV1
venue_address: 1 Example Street, Testville, ZZ99 3WZ
postcode: ZZ99 3WZ
venue_latitude: 51.5
venue_longitude: -0.12
procedure: Platelet
session_id: CS0000
appointments:
  - starts_at: "2026-10-08T17:30:00+01:00"
    procedure: Platelet
    venue: Testville, Example Donor Centre (Main Hall)
    session_id: CS0000
```

### Eligibility

| Entity | Type | Meaning |
|---|---|---|
| `sensor.nhs_give_blood_eligible_from` | timestamp | When you can next **donate** — the clinical deferral date |
| `sensor.nhs_give_blood_can_book_from` | timestamp | When you can next **book** |

!!! warning "These are different dates"

    `can_book_from` also accounts for booking windows and existing appointments, and routinely differs
    from `eligible_from` by weeks. Conflating them is the easiest mistake to make with this API.

### Credits and awards

| Entity | Type | Notes |
|---|---|---|
| `sensor.nhs_give_blood_donation_credits` | total increasing | Lifetime credits. Authoritative. |
| `sensor.nhs_give_blood_award_level` | text | `Bronze`, `Silver`, `Gold`, `Emerald`, `Ruby` |
| `sensor.nhs_give_blood_next_award` | text | Threshold in the `credits_required` attribute |
| `sensor.nhs_give_blood_credits_to_next_award` | count | Floored at zero |
| `sensor.nhs_give_blood_total_awards` | count | |

### History

| Entity | Type | Notes |
|---|---|---|
| `sensor.nhs_give_blood_last_donation` | timestamp | |
| `sensor.nhs_give_blood_donations_recorded` | count | Diagnostic. **A lower bound** — see below |

!!! danger "`donations_recorded` is not your lifetime total"

    The API truncates long histories and flags it as `history_truncated: true` in the attributes. Use
    `donation_credits` for your real total.

Attributes include the most recent 20 donations with date, venue and the raw one-letter outcome code.
NHSBT publishes no mapping for those codes, so they are passed through verbatim rather than guessed at.

### Other

| Entity | Type | Notes |
|---|---|---|
| `sensor.nhs_give_blood_blood_group` | text | |
| `sensor.nhs_give_blood_donor_messages` | count | Filtered to your blood group; bodies in attributes |
| `sensor.nhs_give_blood_donation_type` | text | Diagnostic |
| `sensor.nhs_give_blood_registered_since` | timestamp | Diagnostic |
| `sensor.nhs_give_blood_nearest_plasma_venue` | text | Disabled by default |
| `sensor.nhs_give_blood_nearest_plasma_venue_distance` | distance | Disabled by default |

!!! note "Distance units"

    The API reports distances without a unit; the app renders them as miles, so that is what the
    integration declares. Home Assistant then converts to your configured unit system, so a metric
    instance will show kilometres.

## Binary sensors

| Entity | Device class | Notes |
|---|---|---|
| `binary_sensor.nhs_give_blood_appointment_booked` | — | |
| `binary_sensor.nhs_give_blood_eligible_to_donate` | — | Compared by date, so it turns on at the start of the eligible day |
| `binary_sensor.nhs_give_blood_booking_system_problem` | problem | Diagnostic. `unknown` when the check itself failed |
| `binary_sensor.nhs_give_blood_data_degraded` | problem | Diagnostic, disabled by default |
| `binary_sensor.nhs_give_blood_platelet_plus` | — | Diagnostic, disabled by default |
| `binary_sensor.nhs_give_blood_email_change_pending` | — | Diagnostic, disabled by default |

`booking_system_problem` reports `unknown` rather than `off` when the failover check itself failed —
reporting "no problem" from a failed check would be a false all-clear.

`data_degraded` names the failed endpoints in its `degraded_endpoints` attribute, which is the fastest
way to diagnose "some sensors are `unknown` but others work".

## Enabling disabled entities

**Settings → Devices & services → NHS Give Blood → entities**, pick the entity, then **Settings** →
enable.

They are off by default because they are either niche (plasma venue) or only useful when something has
gone wrong (`data_degraded`).
