"""Sensor platform tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from nhs_give_blood import AccountDetails, DonorSnapshot
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.const import (
    ATTR_APPOINTMENTS,
    ATTR_DONATIONS,
    ATTR_HISTORY_TRUNCATED,
    ATTR_MESSAGES,
    ATTR_VENUE,
)

from .conftest import build_snapshot, setup_integration
from .const import DONOR_ID, account_payload


class TestValues:
    """States derived from the synthetic snapshot."""

    @pytest.mark.parametrize(
        ("entity_id", "expected"),
        [
            ("sensor.nhs_give_blood_blood_group", "A-"),
            ("sensor.nhs_give_blood_donation_credits", "15"),
            ("sensor.nhs_give_blood_award_level", "Bronze"),
            ("sensor.nhs_give_blood_next_award", "Silver"),
            ("sensor.nhs_give_blood_credits_to_next_award", "10"),
            ("sensor.nhs_give_blood_total_awards", "6"),
            ("sensor.nhs_give_blood_upcoming_appointments", "2"),
            ("sensor.nhs_give_blood_donation_type", "Platelet"),
        ],
    )
    async def test_state(
        self,
        hass: HomeAssistant,
        config_entry: MockConfigEntry,
        mock_api: AsyncMock,
        entity_id: str,
        expected: str,
    ) -> None:
        await setup_integration(hass, config_entry)
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} was not created"
        assert state.state == expected

    async def test_timestamp_sensors_are_iso_and_aware(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """A naive timestamp would be read as UTC and shift the displayed time."""
        await setup_integration(hass, config_entry)

        for entity_id in (
            "sensor.nhs_give_blood_next_appointment",
            "sensor.nhs_give_blood_eligible_from",
            "sensor.nhs_give_blood_can_book_from",
            "sensor.nhs_give_blood_last_donation",
        ):
            state = hass.states.get(entity_id)
            assert state is not None
            parsed = datetime.fromisoformat(state.state)
            assert parsed.tzinfo is not None, f"{entity_id} is naive"

    async def test_next_appointment_is_the_soonest(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock, snapshot: DonorSnapshot
    ) -> None:
        await setup_integration(hass, config_entry)
        state = hass.states.get("sensor.nhs_give_blood_next_appointment")

        expected = min(item.starts_at for item in snapshot.upcoming_appointments if item.starts_at)
        assert datetime.fromisoformat(state.state) == expected

    async def test_venue_sensor_uses_the_display_name(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        state = hass.states.get("sensor.nhs_give_blood_next_appointment_venue")
        assert state.state == "Testville, Example Donor Centre (Main Hall)"

    def test_plasma_distance_is_rounded(self, snapshot: DonorSnapshot) -> None:
        """The API returns full float precision; a mile to 15 decimals is noise.

        Asserted on the native value rather than the state, because Home
        Assistant converts distances into the instance's unit system.
        """
        from custom_components.nhs_give_blood.sensor import _plasma_venue_distance

        assert _plasma_venue_distance(snapshot) == 9.9

    def test_plasma_distance_declares_its_unit(self) -> None:
        """The API sends distances unitless; the app renders them as miles."""
        from homeassistant.components.sensor import SensorDeviceClass
        from homeassistant.const import UnitOfLength

        from custom_components.nhs_give_blood.sensor import SENSORS

        description = next(item for item in SENSORS if item.key == "nearest_plasma_venue_distance")
        assert description.device_class is SensorDeviceClass.DISTANCE
        assert description.native_unit_of_measurement == UnitOfLength.MILES


class TestAttributes:
    """Attributes carry the detail dashboards need."""

    async def test_next_appointment_attributes(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        attributes = hass.states.get("sensor.nhs_give_blood_next_appointment").attributes

        assert attributes[ATTR_VENUE] == "Testville, Example Donor Centre (Main Hall)"
        assert len(attributes[ATTR_APPOINTMENTS]) == 2
        assert attributes["procedure"] == "Platelet"

    async def test_donation_attributes_report_api_truncation(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """The list length is a lower bound, and the sensor must say so."""
        await setup_integration(hass, config_entry)
        attributes = hass.states.get("sensor.nhs_give_blood_donations_recorded").attributes

        assert attributes[ATTR_HISTORY_TRUNCATED] is True
        assert len(attributes[ATTR_DONATIONS]) == 2

    async def test_messages_are_filtered_to_the_donors_blood_group(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """The API returns messages for every group; only A- applies here."""
        await setup_integration(hass, config_entry)
        state = hass.states.get("sensor.nhs_give_blood_donor_messages")

        assert state.state == "1"
        assert [item["title"] for item in state.attributes[ATTR_MESSAGES]] == ["A negative donors!"]

    async def test_attributes_stay_within_the_recorder_budget(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Above 16,384 bytes the recorder silently discards the whole blob."""
        import json

        await setup_integration(hass, config_entry)
        for entity_id in hass.states.async_entity_ids("sensor"):
            attributes = dict(hass.states.get(entity_id).attributes)
            size = len(json.dumps(attributes, default=str).encode())
            assert size < 16384, f"{entity_id} attributes are {size} bytes"


class TestMissingData:
    """Every field in this API is optional in practice."""

    async def test_an_empty_account_yields_unknown_not_errors(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        mock_api.async_get_snapshot = AsyncMock(
            return_value=build_snapshot(account=AccountDetails.model_validate({}).model_dump(by_alias=True))
        )
        await setup_integration(hass, config_entry)

        assert hass.states.get("sensor.nhs_give_blood_blood_group").state == STATE_UNKNOWN

    async def test_missing_awards_degrade_to_unknown(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        payload = account_payload()
        payload["awardsData"] = None
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload))
        await setup_integration(hass, config_entry)

        assert hass.states.get("sensor.nhs_give_blood_award_level").state == STATE_UNKNOWN
        assert hass.states.get("sensor.nhs_give_blood_next_award").state == STATE_UNKNOWN

    async def test_no_appointments_yields_zero_and_unknown(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        payload = account_payload()
        payload["appointments"] = []
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload, appointments=[]))
        await setup_integration(hass, config_entry)

        assert hass.states.get("sensor.nhs_give_blood_upcoming_appointments").state == "0"
        assert hass.states.get("sensor.nhs_give_blood_next_appointment").state == STATE_UNKNOWN

    async def test_history_disabled_leaves_the_sensor_unknown(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(include_donations=False))
        await setup_integration(hass, config_entry)

        assert hass.states.get("sensor.nhs_give_blood_last_donation").state == STATE_UNKNOWN
        assert hass.states.get("sensor.nhs_give_blood_donations_recorded").state == STATE_UNKNOWN

    async def test_a_raising_value_function_is_contained(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """One broken sensor must become `unknown`, not break the state write."""
        from custom_components.nhs_give_blood.sensor import (
            GiveBloodSensor,
            GiveBloodSensorEntityDescription,
        )

        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator

        def _explode(_: DonorSnapshot) -> str:
            raise RuntimeError("boom")

        entity = GiveBloodSensor(
            coordinator,
            config_entry,
            GiveBloodSensorEntityDescription(key="exploding", value_fn=_explode, attributes_fn=_explode),
        )

        assert entity.native_value is None
        assert entity.extra_state_attributes is None


class TestRegistry:
    """Entity identity and default visibility."""

    async def test_unique_ids_are_keyed_by_donor_not_entry(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Donor-keyed ids survive removing and re-adding the integration."""
        await setup_integration(hass, config_entry)
        registry = er.async_get(hass)

        entity = registry.async_get("sensor.nhs_give_blood_blood_group")
        assert entity is not None
        assert entity.unique_id == f"{DONOR_ID}_blood_group"
        assert config_entry.entry_id not in entity.unique_id

    async def test_all_unique_ids_are_distinct(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        registry = er.async_get(hass)
        ids = [entity.unique_id for entity in er.async_entries_for_config_entry(registry, config_entry.entry_id)]
        assert len(ids) == len(set(ids))

    async def test_niche_sensors_are_disabled_by_default(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        registry = er.async_get(hass)

        for key in ("nearest_plasma_venue", "nearest_plasma_venue_distance"):
            entity_id = registry.async_get_entity_id("sensor", "nhs_give_blood", f"{DONOR_ID}_{key}")
            assert entity_id is not None
            assert registry.async_get(entity_id).disabled_by is not None

    async def test_diagnostic_sensors_are_categorised(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        from homeassistant.const import EntityCategory

        await setup_integration(hass, config_entry)
        registry = er.async_get(hass)

        entity_id = registry.async_get_entity_id("sensor", "nhs_give_blood", f"{DONOR_ID}_registered_since")
        assert registry.async_get(entity_id).entity_category is EntityCategory.DIAGNOSTIC
