"""Coordinator tests: error mapping, backoff, and token persistence."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from nhs_give_blood import DonorSnapshot
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.nhs_give_blood.api import CannotConnect, InvalidAuth
from custom_components.nhs_give_blood.const import (
    BACKOFF_FAILURE_THRESHOLD,
    CONF_TOKENS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_BACKOFF_INTERVAL,
)

from .conftest import build_snapshot, setup_integration


async def _advance(hass: HomeAssistant, interval: timedelta) -> None:
    """Fire the coordinator's next scheduled refresh."""
    async_fire_time_changed(hass, dt_util.utcnow() + interval + timedelta(seconds=1))
    await hass.async_block_till_done()


class TestErrorMapping:
    """How a failure is classified decides what the user sees."""

    async def test_connection_failure_marks_entities_unavailable(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator

        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert not coordinator.last_update_success
        assert hass.states.get("sensor.nhs_give_blood_blood_group").state == "unavailable"

    async def test_connection_failure_does_not_prompt_for_credentials(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)

    async def test_invalid_auth_starts_a_reauth_flow(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        mock_api.async_get_snapshot = AsyncMock(side_effect=InvalidAuth("expired"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert any(flow["context"]["source"] == "reauth" for flow in flows)

    async def test_an_unexpected_error_is_contained(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """A coordinator must never let an exception escape to the scheduler."""
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator

        mock_api.async_get_snapshot = AsyncMock(side_effect=RuntimeError("boom"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert not coordinator.last_update_success
        assert config_entry.state is ConfigEntryState.LOADED

    async def test_recovers_on_the_next_successful_poll(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock, snapshot: DonorSnapshot
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator

        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)
        assert not coordinator.last_update_success

        mock_api.async_get_snapshot = AsyncMock(return_value=snapshot)
        await _advance(hass, coordinator.update_interval or DEFAULT_SCAN_INTERVAL)

        assert coordinator.last_update_success


class TestBackoff:
    """Sustained failure must not mean sustained request volume."""

    async def test_interval_grows_after_repeated_failures(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator
        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))

        for _ in range(BACKOFF_FAILURE_THRESHOLD):
            await _advance(hass, coordinator.update_interval or DEFAULT_SCAN_INTERVAL)

        assert coordinator.update_interval is not None
        assert coordinator.update_interval > DEFAULT_SCAN_INTERVAL

    async def test_interval_is_capped(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator
        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))

        for _ in range(12):
            await _advance(hass, coordinator.update_interval or DEFAULT_SCAN_INTERVAL)

        assert coordinator.update_interval == MAX_BACKOFF_INTERVAL

    async def test_the_configured_interval_is_restored_after_recovery(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock, snapshot: DonorSnapshot
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator
        mock_api.async_get_snapshot = AsyncMock(side_effect=CannotConnect("down"))
        for _ in range(BACKOFF_FAILURE_THRESHOLD):
            await _advance(hass, coordinator.update_interval or DEFAULT_SCAN_INTERVAL)
        assert coordinator.update_interval != DEFAULT_SCAN_INTERVAL

        mock_api.async_get_snapshot = AsyncMock(return_value=snapshot)
        await _advance(hass, coordinator.update_interval or DEFAULT_SCAN_INTERVAL)

        assert coordinator.update_interval == DEFAULT_SCAN_INTERVAL

    async def test_invalid_auth_does_not_back_off(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Reauth is the fix; backing off would only delay the prompt."""
        await setup_integration(hass, config_entry)
        coordinator = config_entry.runtime_data.coordinator

        mock_api.async_get_snapshot = AsyncMock(side_effect=InvalidAuth("expired"))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert coordinator.update_interval == DEFAULT_SCAN_INTERVAL


class TestTokenPersistence:
    """Tokens rotate every ~30 minutes and must survive a restart."""

    async def test_rotated_tokens_are_written_to_the_entry(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        rotated = {"access_token": "rotated.access.token", "refresh_token": "rotated-refresh", "expires_at": 1.0}
        mock_api.token_data = rotated
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert config_entry.data[CONF_TOKENS] == rotated

    async def test_unchanged_tokens_are_not_rewritten(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """An unconditional write would fire the update listener on every poll."""
        await setup_integration(hass, config_entry)
        before = config_entry.data[CONF_TOKENS]
        coordinator_before = config_entry.runtime_data.coordinator

        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert config_entry.data[CONF_TOKENS] == before
        assert config_entry.runtime_data.coordinator is coordinator_before


class TestDegradedSnapshots:
    """A degraded snapshot is still a successful poll."""

    async def test_degradation_does_not_mark_the_poll_failed(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(degraded=("messages", "features")))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        coordinator = config_entry.runtime_data.coordinator
        assert coordinator.last_update_success
        assert coordinator.data is not None
        assert coordinator.data.partial

    async def test_core_entities_stay_available_when_degraded(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(degraded=("messages",)))
        await _advance(hass, DEFAULT_SCAN_INTERVAL)

        assert hass.states.get("sensor.nhs_give_blood_blood_group").state == "A-"
