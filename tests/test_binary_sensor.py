"""Binary sensor platform tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from nhs_give_blood import FailoverBanner
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.const import ATTR_DEGRADED_ENDPOINTS

from .conftest import build_snapshot, setup_integration
from .const import DONOR_ID, LONDON, account_payload


def _enable(hass: HomeAssistant, key: str) -> str:
    """Enable a default-disabled entity and return its id."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("binary_sensor", "nhs_give_blood", f"{DONOR_ID}_{key}")
    assert entity_id is not None
    registry.async_update_entity(entity_id, disabled_by=None)
    return entity_id


class TestStates:
    """States derived from the synthetic snapshot."""

    @pytest.mark.parametrize(
        ("entity_id", "expected"),
        [
            ("binary_sensor.nhs_give_blood_appointment_booked", STATE_ON),
            ("binary_sensor.nhs_give_blood_eligible_to_donate", STATE_ON),
            ("binary_sensor.nhs_give_blood_booking_system_problem", STATE_OFF),
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

    async def test_no_appointments_means_off(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        payload = account_payload()
        payload["appointments"] = []
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload, appointments=[]))
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_appointment_booked").state == STATE_OFF


class TestEligibility:
    """The eligibility boundary is a date, not an instant."""

    async def test_eligible_on_the_boundary_day(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """The API returns midnight; comparing timestamps would say "not yet" all day."""
        from homeassistant.util import dt as dt_util

        today_midnight = dt_util.now().astimezone(LONDON).replace(hour=0, minute=0, second=0, microsecond=0)
        payload = account_payload()
        payload["eligibility"]["nextPossibleDonationDate"] = today_midnight.replace(tzinfo=None).isoformat()
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload))
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_eligible_to_donate").state == STATE_ON

    async def test_not_eligible_when_the_date_is_in_the_future(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        from homeassistant.util import dt as dt_util

        future = (dt_util.now().astimezone(LONDON) + timedelta(days=10)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        payload = account_payload()
        payload["eligibility"]["nextPossibleDonationDate"] = future.replace(tzinfo=None).isoformat()
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload))
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_eligible_to_donate").state == STATE_OFF

    async def test_unknown_when_the_api_omits_the_date(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        payload = account_payload()
        payload["eligibility"] = None
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(account=payload))
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_eligible_to_donate").state == STATE_UNKNOWN


class TestBookingSystemProblem:
    """The failover banner is the only signal that writes will fail."""

    async def test_on_when_failover_is_active(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        mock_api.async_get_snapshot = AsyncMock(
            return_value=build_snapshot(
                failover=FailoverBanner.model_validate({"header": "Down", "content": "…", "isActive": True})
            )
        )
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_booking_system_problem").state == STATE_ON

    async def test_unknown_rather_than_all_clear_when_the_check_failed(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Reporting "no problem" from a failed check is a false all-clear."""
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(failover=None, degraded=("failover",)))
        await setup_integration(hass, config_entry)

        assert hass.states.get("binary_sensor.nhs_give_blood_booking_system_problem").state == STATE_UNKNOWN


class TestDegradation:
    """The degradation sensor is how a partial poll becomes visible."""

    async def test_off_on_a_clean_snapshot(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        entity_id = _enable(hass, "data_degraded")
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

        assert hass.states.get(entity_id).state == STATE_OFF

    async def test_on_and_names_the_failed_endpoints(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        entity_id = _enable(hass, "data_degraded")
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(degraded=("messages", "features")))
        await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()

        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_DEGRADED_ENDPOINTS] == ["messages", "features"]


class TestRegistry:
    """Identity and default visibility."""

    async def test_diagnostic_sensors_are_disabled_by_default(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        registry = er.async_get(hass)

        for key in ("data_degraded", "platelet_plus", "email_change_pending"):
            entity_id = registry.async_get_entity_id("binary_sensor", "nhs_give_blood", f"{DONOR_ID}_{key}")
            assert registry.async_get(entity_id).disabled_by is not None, key

    async def test_problem_sensors_use_the_problem_device_class(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass

        await setup_integration(hass, config_entry)
        state = hass.states.get("binary_sensor.nhs_give_blood_booking_system_problem")
        assert state.attributes["device_class"] == BinarySensorDeviceClass.PROBLEM

    async def test_a_raising_value_function_is_contained(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        from nhs_give_blood import DonorSnapshot

        from custom_components.nhs_give_blood.binary_sensor import (
            GiveBloodBinarySensor,
            GiveBloodBinarySensorEntityDescription,
        )

        await setup_integration(hass, config_entry)

        def _explode(_: DonorSnapshot) -> bool:
            raise RuntimeError("boom")

        entity = GiveBloodBinarySensor(
            config_entry.runtime_data.coordinator,
            config_entry,
            GiveBloodBinarySensorEntityDescription(key="exploding", value_fn=_explode, attributes_fn=_explode),
        )

        assert entity.is_on is None
        assert entity.extra_state_attributes is None
