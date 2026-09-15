"""Calendar platform tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from nhs_give_blood import Appointment
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import build_snapshot, setup_integration
from .const import LONDON, account_payload

ENTITY_ID = "calendar.nhs_give_blood_appointments"


class TestEntity:
    """The calendar entity itself."""

    async def test_is_created(self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock) -> None:
        await setup_integration(hass, config_entry)
        assert hass.states.get(ENTITY_ID) is not None

    async def test_shows_the_next_appointment(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        state = hass.states.get(ENTITY_ID)

        assert state.state == "off", "no appointment is running right now"
        assert "Platelet" in state.attributes["message"]

    async def test_is_off_with_no_appointments(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        payload = account_payload()
        payload["appointments"] = []
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload, appointments=[]))
        await setup_integration(hass, config_entry)

        assert hass.states.get(ENTITY_ID).state == "off"


class TestEvents:
    """Event construction."""

    async def test_events_are_returned_for_the_window(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        now = dt_util.now()

        response = await hass.services.async_call(
            CALENDAR_DOMAIN,
            "get_events",
            {
                "entity_id": ENTITY_ID,
                "start_date_time": now.isoformat(),
                "end_date_time": (now + timedelta(days=90)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )

        events = response[ENTITY_ID]["events"]
        assert len(events) == 2
        assert all("Give blood" in event["summary"] for event in events)

    async def test_a_past_window_returns_nothing(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """The API only exposes future appointments, so this is correct, not a bug."""
        await setup_integration(hass, config_entry)
        now = dt_util.now()

        response = await hass.services.async_call(
            CALENDAR_DOMAIN,
            "get_events",
            {
                "entity_id": ENTITY_ID,
                "start_date_time": (now - timedelta(days=365)).isoformat(),
                "end_date_time": (now - timedelta(days=1)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )

        assert response[ENTITY_ID]["events"] == []

    async def test_events_carry_the_venue_as_location(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        now = dt_util.now()

        response = await hass.services.async_call(
            CALENDAR_DOMAIN,
            "get_events",
            {
                "entity_id": ENTITY_ID,
                "start_date_time": now.isoformat(),
                "end_date_time": (now + timedelta(days=90)).isoformat(),
            },
            blocking=True,
            return_response=True,
        )

        location = response[ENTITY_ID]["events"][0]["location"]
        assert "Testville" in location
        assert "ZZ99 3WZ" in location


class TestEventShape:
    """Unit-level checks on the conversion, where the edge cases live."""

    def test_duration_varies_by_procedure(self) -> None:
        """Apheresis takes materially longer than whole blood."""
        from custom_components.nhs_give_blood.calendar import _duration

        whole_blood = Appointment.model_validate({"procedureCode": "WB"})
        platelet = Appointment.model_validate({"procedureCode": "PLT"})
        plasma = Appointment.model_validate({"procedureCode": "PLS"})

        assert _duration(platelet) > _duration(plasma) > _duration(whole_blood)

    def test_unknown_procedure_falls_back_to_a_default_duration(self) -> None:
        from custom_components.nhs_give_blood.calendar import _DEFAULT_DURATION, _duration

        assert _duration(Appointment.model_validate({"procedureCode": "ZZZ"})) == _DEFAULT_DURATION
        assert _duration(Appointment.model_validate({})) == _DEFAULT_DURATION

    def test_an_appointment_without_a_start_time_is_skipped(self) -> None:
        """A malformed appointment must not appear as an event at an unknown time."""
        from custom_components.nhs_give_blood.calendar import _to_event

        assert _to_event(Appointment.model_validate({"time": "T1730"})) is None

    def test_uid_distinguishes_two_appointments_in_one_session(self) -> None:
        """Session id alone is not unique: one session can hold two slots."""
        from custom_components.nhs_give_blood.calendar import _to_event

        first = _to_event(
            Appointment.model_validate(
                {"time": "T0900", "session": {"sessionId": "CS1", "sessionDate": "2026-10-08T00:00:00"}}
            )
        )
        second = _to_event(
            Appointment.model_validate(
                {"time": "T1400", "session": {"sessionId": "CS1", "sessionDate": "2026-10-08T00:00:00"}}
            )
        )

        assert first is not None and second is not None
        assert first.uid != second.uid

    def test_venue_notes_are_included_in_the_description(self) -> None:
        """Notes carry things like "step-free access" that matter on the day."""
        from custom_components.nhs_give_blood.calendar import _to_event

        event = _to_event(
            Appointment.model_validate(
                {
                    "time": "T0900",
                    "procedureDescription": "Whole Blood",
                    "session": {
                        "sessionId": "CS1",
                        "sessionDate": "2026-10-08T00:00:00",
                        "venue": {"venueName": "Hall", "notes": ["Step-free access"]},
                    },
                }
            )
        )

        assert event is not None
        assert "Step-free access" in (event.description or "")

    def test_end_time_is_after_start_time(self) -> None:
        from custom_components.nhs_give_blood.calendar import _to_event

        event = _to_event(
            Appointment.model_validate(
                {
                    "time": "T0900",
                    "procedureCode": "WB",
                    "session": {"sessionId": "CS1", "sessionDate": "2026-10-08T00:00:00"},
                }
            )
        )
        assert event is not None
        assert event.end > event.start


class TestCurrentEvent:
    """An in-progress appointment should read as "now", not "next"."""

    async def test_in_progress_appointment_takes_precedence(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        # Clock values must be built in venue-local time: the API's datetimes are
        # naive and the library localises them to Europe/London, so formatting a
        # UTC wall clock here would place the appointment an hour out.
        started = dt_util.now().astimezone(LONDON) - timedelta(minutes=15)
        payload = account_payload()
        payload["appointments"] = []
        current = {
            "status": "A",
            "time": f"T{started.strftime('%H%M')}",
            "procedureCode": "WB",
            "procedureDescription": "Whole Blood",
            "cancellationCode": None,
            "session": {
                "sessionId": "CSNOW",
                "sessionDate": started.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None).isoformat(),
                "venue": {"venueName": "Hall"},
                "periods": [],
            },
        }
        mock_api.async_get_snapshot = AsyncMock(
            return_value=build_snapshot(account=payload, appointments=[Appointment.model_validate(current)])
        )
        await setup_integration(hass, config_entry)

        assert hass.states.get(ENTITY_ID).state == "on"
