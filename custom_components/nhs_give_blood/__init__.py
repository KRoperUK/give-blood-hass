"""The NHS Give Blood integration.

Read-only by design. The underlying API can book, reschedule and cancel
appointments, and the ``nhs-give-blood`` library exposes all three — but a
mis-fired automation there releases a real clinic slot at a real NHS donation
centre, with no undo. That risk does not belong behind an entity that a template
error can toggle, so this integration only reads.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import CannotConnect, GiveBloodApiClient, InvalidAuth
from .const import (
    CONF_INCLUDE_DONATION_HISTORY,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TOKENS,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    PLATFORMS,
    STARTUP_MESSAGE,
)
from .coordinator import GiveBloodConfigEntry, GiveBloodCoordinator

_LOGGER = logging.getLogger(__name__)

_STARTUP_LOGGED = False


@dataclass
class GiveBloodRuntimeData:
    """Runtime objects for one config entry."""

    api: GiveBloodApiClient
    coordinator: GiveBloodCoordinator
    platforms: list[Platform]
    #: Snapshot of the options at setup, so the update listener can tell an
    #: options change from a token write. See :func:`async_reload_entry`.
    options: dict[str, Any] = field(default_factory=dict)


def _scan_interval(options: dict[str, Any]) -> timedelta:
    """Resolve the poll interval from options, clamped to sane bounds."""
    raw = options.get(CONF_SCAN_INTERVAL_MINUTES)
    if raw is None:
        return DEFAULT_SCAN_INTERVAL
    try:
        minutes = int(raw)
    except TypeError, ValueError:
        _LOGGER.warning("Ignoring non-numeric scan interval %r; using the default", raw)
        return DEFAULT_SCAN_INTERVAL
    clamped = max(MIN_SCAN_INTERVAL_MINUTES, min(minutes, MAX_SCAN_INTERVAL_MINUTES))
    if clamped != minutes:
        _LOGGER.warning("Scan interval %s minutes is out of range; using %s", minutes, clamped)
    return timedelta(minutes=clamped)


async def _preload_platforms(platforms: list[Platform]) -> None:
    """Import platform modules off the event loop.

    ``async_forward_entry_setups`` imports each platform lazily, which happens on
    the event loop and trips Home Assistant's "detected blocking call to
    import_module" warning on a cold start. Importing them in an executor first
    avoids it.
    """
    import importlib

    def _import() -> None:
        for platform in platforms:
            importlib.import_module(f".{platform.value}", package=__package__)

    await asyncio.to_thread(_import)


async def async_setup_entry(hass: HomeAssistant, entry: GiveBloodConfigEntry) -> bool:
    """Set up a donor account from a config entry."""
    global _STARTUP_LOGGED  # noqa: PLW0603 - once-per-process banner
    if not _STARTUP_LOGGED:
        _LOGGER.info(STARTUP_MESSAGE)
        _STARTUP_LOGGED = True

    client = GiveBloodApiClient(
        hass,
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
        tokens=entry.data.get(CONF_TOKENS),
    )

    try:
        await client.async_validate()
    except InvalidAuth as err:
        # Raising this rather than returning False is what opens a reauth flow.
        raise ConfigEntryAuthFailed(str(err)) from err
    except CannotConnect as err:
        raise ConfigEntryNotReady(str(err)) from err

    options = dict(entry.options)
    coordinator = GiveBloodCoordinator(
        hass,
        entry,
        client,
        update_interval=_scan_interval(options),
        include_donations=options.get(CONF_INCLUDE_DONATION_HISTORY, True),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = GiveBloodRuntimeData(
        api=client,
        coordinator=coordinator,
        platforms=list(PLATFORMS),
        options=options,
    )

    await _preload_platforms(entry.runtime_data.platforms)
    await hass.config_entries.async_forward_entry_setups(entry, entry.runtime_data.platforms)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GiveBloodConfigEntry) -> bool:
    """Tear down a config entry."""
    runtime = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, runtime.platforms)
    if unloaded:
        # Best effort; a failed sign-out must not block the unload.
        await runtime.api.async_logout()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: GiveBloodConfigEntry) -> None:
    """Reload the entry, but only when the *options* actually changed.

    This listener fires for any ``async_update_entry`` call, including the token
    write the coordinator performs after each poll. Reloading on those would
    produce an endless loop: reload → poll → tokens rotate → update entry →
    reload. Comparing against the options snapshot taken at setup breaks it.
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and dict(entry.options) == runtime.options:
        return
    await hass.config_entries.async_reload(entry.entry_id)
