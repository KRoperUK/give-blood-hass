"""Calendar platform for the NHS Give Blood integration.

Exposes booked donation appointments as calendar events, which is what makes
"remind me the evening before" a two-line automation instead of a template
sensor and a date comparison.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from nhs_give_blood import Appointment

from .coordinator import GiveBloodConfigEntry, GiveBloodCoordinator
from .entity import GiveBloodEntity
from .helpers import safe_datetime

_LOGGER = logging.getLogger(__name__)

# Read-only entities fed by a single coordinator fetch: there are no per-entity
# requests to serialise, and no actions that could write. Home Assistant's
# quality scale asks for this to be explicit rather than left to the default.
PARALLEL_UPDATES = 0

# The API gives a start time but no duration. A whole blood donation appointment
# runs about an hour end to end; apheresis (platelets, plasma) runs longer. These
# are the durations the app's own guidance quotes, used so the calendar block
# roughly matches how long the donor will actually be there.
_DURATION_BY_PROCEDURE: dict[str, timedelta] = {
    "WB": timedelta(minutes=60),
    "PLS": timedelta(minutes=90),
    "PLT": timedelta(minutes=120),
}
_DEFAULT_DURATION = timedelta(minutes=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiveBloodConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the appointments calendar for a config entry."""
    async_add_entities([GiveBloodCalendar(entry.runtime_data.coordinator, entry)])


def _duration(appointment: Appointment) -> timedelta:
    """Estimated appointment length, by procedure."""
    code = (appointment.procedure_code or "").upper()
    return _DURATION_BY_PROCEDURE.get(code, _DEFAULT_DURATION)


def _to_event(appointment: Appointment) -> CalendarEvent | None:
    """Convert an appointment to a calendar event, or ``None`` if unusable."""
    start = safe_datetime(appointment.starts_at)
    if start is None:
        return None
    venue = appointment.venue
    location_parts = [venue.display_name if venue else None]
    if venue is not None and venue.address is not None:
        location_parts.append(venue.address.one_line)
    location = ", ".join(part for part in location_parts if part)

    procedure = appointment.procedure_description or "Donation"
    description_lines = [f"{procedure} donation appointment."]
    if venue is not None and venue.notes:
        description_lines.extend(venue.notes)
    if appointment.session_id:
        description_lines.append(f"Session {appointment.session_id}")

    return CalendarEvent(
        start=start,
        end=start + _duration(appointment),
        summary=f"Give blood — {procedure}",
        location=location or None,
        description="\n".join(description_lines),
        # Stable across polls so calendar consumers can de-duplicate. Session id
        # alone isn't enough: a session can hold two appointments at different
        # times for the same donor.
        uid=f"{appointment.session_id or 'unknown'}-{appointment.time or 'unknown'}",
    )


class GiveBloodCalendar(GiveBloodEntity, CalendarEntity):
    """Booked donation appointments as a calendar."""

    _attr_translation_key = "appointments"
    _attr_icon = "mdi:calendar-heart"

    def __init__(self, coordinator: GiveBloodCoordinator, entry: GiveBloodConfigEntry) -> None:
        """Set up the calendar entity."""
        super().__init__(coordinator, entry, "appointments")

    @property
    def _events(self) -> list[CalendarEvent]:
        """All known appointments as events, soonest first."""
        snapshot = self.snapshot
        if snapshot is None:
            return []
        events = [event for item in snapshot.upcoming_appointments if (event := _to_event(item))]
        return sorted(events, key=lambda event: event.start)

    @property
    def event(self) -> CalendarEvent | None:
        """The next or currently-running appointment.

        An in-progress appointment takes precedence over the next one, so the
        entity reads "now" rather than "next" while the donor is at the clinic.
        """
        now = dt_util.now()
        events = self._events
        for candidate in events:
            if candidate.start <= now < candidate.end:
                return candidate
        return next((candidate for candidate in events if candidate.start > now), None)

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return events overlapping the requested window.

        The API only exposes *future* appointments, so a query for a past range
        legitimately returns nothing. Overlap rather than containment is used so a
        query landing mid-appointment still finds it.
        """
        return [event for event in self._events if event.start < end_date and event.end > start_date]
