# Automations

All examples trigger on explicit states rather than templating over values that may be `unknown` or
`unavailable`.

## Remind yourself the evening before

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

A calendar trigger with a negative `offset` is the right tool here: it survives restarts, needs no
template maths, and fires relative to the appointment rather than to a fixed clock time.

## Nudge yourself when eligible with nothing booked

```yaml
automation:
  - alias: Eligible to donate with nothing booked
    triggers:
      - trigger: state
        entity_id: binary_sensor.nhs_give_blood_eligible_to_donate
        to: "on"
        for: "24:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.nhs_give_blood_appointment_booked
        state: "off"
      # Don't nag during an NHSBT outage — there would be nothing to act on.
      - condition: state
        entity_id: binary_sensor.nhs_give_blood_booking_system_problem
        state: "off"
    actions:
      - action: notify.mobile_app_phone
        data:
          title: You can donate again
          message: >-
            Nothing booked yet.
            {{ states('sensor.nhs_give_blood_credits_to_next_award') }} credit(s)
            to {{ states('sensor.nhs_give_blood_next_award') }}.
          data:
            url: https://my.blood.co.uk
```

!!! tip "Why `for: "24:00:00"`"

    Without it, a restart or a reload re-fires the trigger. A day's delay makes the notification a
    considered nudge rather than a side effect of Home Assistant restarting.

## Announce an award milestone

```yaml
automation:
  - alias: Blood donation award reached
    triggers:
      - trigger: state
        entity_id: sensor.nhs_give_blood_award_level
    conditions:
      # Filter out startup transitions from unknown/unavailable, which would
      # otherwise announce an "award" on every restart.
      - condition: template
        value_template: >-
          {{ trigger.from_state.state not in ['unknown', 'unavailable', 'None']
             and trigger.to_state.state not in ['unknown', 'unavailable', 'None'] }}
    actions:
      - action: notify.mobile_app_phone
        data:
          title: New donation award
          message: >-
            You've reached {{ trigger.to_state.state }} —
            {{ states('sensor.nhs_give_blood_donation_credits') }} credits.
```

The condition matters. Every Home Assistant restart takes sensors through `unavailable` → real value,
and without the filter this would congratulate you monthly.

## Show it on a dashboard

```yaml
type: entities
title: Blood donation
entities:
  - entity: sensor.nhs_give_blood_next_appointment
    name: Next appointment
  - entity: sensor.nhs_give_blood_next_appointment_venue
    name: Where
  - entity: sensor.nhs_give_blood_eligible_from
    name: Eligible from
  - entity: sensor.nhs_give_blood_donation_credits
    name: Credits
  - type: attribute
    entity: sensor.nhs_give_blood_next_award
    attribute: credits_required
    name: Next award at
  - entity: binary_sensor.nhs_give_blood_eligible_to_donate
    name: Can donate now
```

A conditional card that only appears when there is something to say:

```yaml
type: conditional
conditions:
  - condition: state
    entity: binary_sensor.nhs_give_blood_appointment_booked
    state: "off"
  - condition: state
    entity: binary_sensor.nhs_give_blood_eligible_to_donate
    state: "on"
card:
  type: markdown
  content: |
    ## 🩸 You can donate again
    Nothing booked. [Book now](https://my.blood.co.uk)
```

## Countdown to the next appointment

The integration deliberately does not ship a "days until" sensor — a timestamp plus a template is more
flexible and avoids a sensor that changes state every day.

```yaml
template:
  - sensor:
      - name: Days until blood donation
        unique_id: days_until_blood_donation
        unit_of_measurement: d
        state: >-
          {% set appointment = states('sensor.nhs_give_blood_next_appointment') %}
          {% if appointment not in ['unknown', 'unavailable', ''] %}
            {{ ((appointment | as_datetime - now()).total_seconds() / 86400) | round(0) }}
          {% else %}
            {{ none }}
          {% endif %}
        availability: >-
          {{ states('sensor.nhs_give_blood_next_appointment')
             not in ['unknown', 'unavailable', ''] }}
```

The `availability` template is what keeps this from logging a template error every poll when no
appointment is booked, and `{{ none }}` in the state keeps it `unknown` rather than a misleading `0`.

## Read the donor message for your blood group

```yaml
template:
  - sensor:
      - name: Blood donation message
        unique_id: blood_donation_message
        state: >-
          {{ (state_attr('sensor.nhs_give_blood_donor_messages', 'messages')
              or [{}]) | first | attr_or_default('title', 'None') }}
        attributes:
          text: >-
            {{ ((state_attr('sensor.nhs_give_blood_donor_messages', 'messages')
                 or [{}]) | first).get('text', '') }}
        availability: >-
          {{ states('sensor.nhs_give_blood_donor_messages')
             not in ['unknown', 'unavailable'] }}
```

!!! warning "State length"

    Home Assistant rejects a state longer than 255 characters. Message *bodies* frequently exceed that,
    which is why they belong in an attribute rather than a state.
