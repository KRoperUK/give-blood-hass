---
title: NHS Give Blood for Home Assistant
---

# NHS Give Blood for Home Assistant

Brings your NHS blood donation account into Home Assistant: appointments, eligibility dates, donation
credits and awards.

!!! warning "Unofficial"

    This talks to the private API behind the [NHS Give Blood app](https://www.blood.co.uk/nhsgivebloodapp).
    NHS Blood and Transplant does not publish, support or endorse it, and can change or break it at any
    time.

## What you get

<div class="grid cards" markdown>

- :material-calendar-heart: **A calendar of your appointments**

    Booked donation appointments as calendar events, so "remind me the evening before" is a two-line
    automation.

- :material-calendar-check: **Eligibility dates**

    When you can next donate, and when you can next book. These are different dates, and the
    integration keeps them separate.

- :material-medal: **Award progress**

    Current tier, next milestone, and how many credits to go.

- :material-history: **Donation history**

    Date and venue of your most recent donations.

- :material-message-text: **Targeted donor messages**

    Filtered to your blood group from the API's all-groups feed.

- :material-alert: **Outage awareness**

    A booking-system sensor, so an automation can tell "nothing booked" from "NHSBT is down".

</div>

## Quick start

```bash
# HACS → Custom repositories → add as an Integration
https://github.com/KRoperUK/give-blood-hass
```

Then **Settings → Devices & services → Add integration → NHS Give Blood**, and sign in with your NHS
Give Blood app credentials.

[Full installation guide →](installation.md){ .md-button .md-button--primary }
[Entity reference →](entities.md){ .md-button }

## Read-only by design

The API can book, reschedule and cancel appointments. This integration exposes none of them.

A cancelled appointment releases a real slot at a real NHS donation centre, immediately and
irreversibly. Behind a Home Assistant entity, that becomes reachable by any automation, script or
misfired template.

[Why, in more detail →](design.md#why-read-only)

## Two projects

| Repository | What it is |
|---|---|
| [give-blood-hass](https://github.com/KRoperUK/give-blood-hass) | This Home Assistant integration |
| [give-blood-py](https://github.com/KRoperUK/give-blood-py) | The `nhs-give-blood` Python library it is built on, plus a CLI |

The library is independently usable and documents the API itself, including how it was recovered from
the Android app.

## Please keep donating 🩸

If this integration nudges you into one extra donation a year, it has done its job.
[Book an appointment](https://my.blood.co.uk).
