"""Entry lifecycle tests: setup, unload, reauth signalling, options reload."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.const import (
    CONF_INCLUDE_DONATION_HISTORY,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TOKENS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

from .conftest import setup_integration


class TestSetup:
    """Happy-path setup."""

    async def test_entry_loads(self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock) -> None:
        await setup_integration(hass, config_entry)
        assert config_entry.state is ConfigEntryState.LOADED

    async def test_runtime_data_is_populated(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        runtime = config_entry.runtime_data
        assert runtime.coordinator.data is not None
        assert runtime.platforms

    async def test_entities_are_created(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        entities = hass.states.async_entity_ids()
        assert any(entity.startswith("sensor.") for entity in entities)
        assert any(entity.startswith("binary_sensor.") for entity in entities)
        assert any(entity.startswith("calendar.") for entity in entities)

    async def test_one_device_per_account(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """A donor account is one device; there is no hierarchy to get wrong."""
        from homeassistant.helpers import device_registry as dr

        await setup_integration(hass, config_entry)
        devices = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
        assert len(devices) == 1

    async def test_device_name_does_not_expose_the_donor(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Device names surface in logs, diagnostics and screenshots."""
        from homeassistant.helpers import device_registry as dr

        await setup_integration(hass, config_entry)
        device = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)[0]
        assert device.name == "NHS Give Blood"
        assert "Testerson" not in (device.name or "")


class TestSetupFailures:
    """Failures must map onto the right Home Assistant retry behaviour."""

    async def test_invalid_auth_starts_a_reauth_flow(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api_invalid_auth: AsyncMock
    ) -> None:
        """Rejected credentials need a human, so HA must ask rather than retry."""
        await setup_integration(hass, config_entry)

        assert config_entry.state is ConfigEntryState.SETUP_ERROR
        flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert any(flow["context"]["source"] == "reauth" for flow in flows)

    async def test_connection_failure_schedules_a_retry(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api_cannot_connect: AsyncMock
    ) -> None:
        """A transient failure must retry, not prompt the user."""
        await setup_integration(hass, config_entry)

        assert config_entry.state is ConfigEntryState.SETUP_RETRY
        assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


class TestUnload:
    """Teardown."""

    async def test_unload_removes_entities(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.NOT_LOADED

    async def test_unload_signs_out(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

        mock_api.async_logout.assert_awaited()


class TestScanInterval:
    """Interval resolution from options."""

    async def test_defaults_when_unset(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        assert config_entry.runtime_data.coordinator.update_interval == DEFAULT_SCAN_INTERVAL

    async def test_honours_a_configured_interval(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL_MINUTES: 120})
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.runtime_data.coordinator.update_interval == timedelta(minutes=120)

    async def test_clamps_a_too_small_interval(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Nobody should be able to poll a public health service every minute."""
        config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL_MINUTES: 1})
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.runtime_data.coordinator.update_interval == timedelta(minutes=MIN_SCAN_INTERVAL_MINUTES)

    async def test_clamps_a_too_large_interval(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL_MINUTES: 99999})
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.runtime_data.coordinator.update_interval == timedelta(minutes=MAX_SCAN_INTERVAL_MINUTES)

    async def test_ignores_a_non_numeric_interval(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL_MINUTES: "soon"})
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.runtime_data.coordinator.update_interval == DEFAULT_SCAN_INTERVAL


class TestOptionsReload:
    """The update listener must distinguish options changes from token writes."""

    async def test_changing_options_reloads(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)

        hass.config_entries.async_update_entry(config_entry, options={CONF_SCAN_INTERVAL_MINUTES: 60})
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED
        assert config_entry.runtime_data.coordinator.update_interval == timedelta(minutes=60)

    async def test_a_data_only_write_does_not_reload(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Otherwise every poll's token write would trigger a reload loop."""
        await setup_integration(hass, config_entry)
        coordinator_before = config_entry.runtime_data.coordinator

        hass.config_entries.async_update_entry(
            config_entry,
            data={**config_entry.data, CONF_TOKENS: {"access_token": "rotated", "refresh_token": "r"}},
        )
        await hass.async_block_till_done()

        assert config_entry.runtime_data.coordinator is coordinator_before


class TestDonationHistoryOption:
    """Turning history off must reach the adapter, not just the UI."""

    async def test_option_is_passed_through(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(config_entry, options={CONF_INCLUDE_DONATION_HISTORY: False})
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        mock_api.async_get_snapshot.assert_awaited_with(include_donations=False)
