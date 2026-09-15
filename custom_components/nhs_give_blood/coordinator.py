"""Data update coordinator for the NHS Give Blood integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from nhs_give_blood import DonorSnapshot

from .api import CannotConnect, GiveBloodApiClient, InvalidAuth
from .const import (
    BACKOFF_FAILURE_THRESHOLD,
    CONF_TOKENS,
    DOMAIN,
    MAX_BACKOFF_INTERVAL,
)

if TYPE_CHECKING:
    # Imported for typing only: `GiveBloodRuntimeData` lives in __init__ and
    # holds a coordinator, so a runtime import would be circular. PEP 695 `type`
    # aliases are lazily evaluated, so the forward reference is fine.
    from . import GiveBloodRuntimeData

_LOGGER = logging.getLogger(__name__)

type GiveBloodConfigEntry = ConfigEntry["GiveBloodRuntimeData"]


class GiveBloodCoordinator(DataUpdateCoordinator[DonorSnapshot]):
    """Polls the donor account and adapts the update interval to failures.

    Error mapping is the important part:

    * ``InvalidAuth`` becomes :class:`ConfigEntryAuthFailed`, which is what makes
      Home Assistant open a reauth flow instead of retrying forever.
    * ``CannotConnect`` becomes :class:`UpdateFailed`, which marks entities
      unavailable and retries on the next interval.

    On sustained failure the interval backs off toward
    :data:`MAX_BACKOFF_INTERVAL`. NHSBT maintenance windows last hours, and
    hammering a public health service every 30 minutes through one is both rude
    and pointless.
    """

    config_entry: GiveBloodConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GiveBloodConfigEntry,
        client: GiveBloodApiClient,
        *,
        update_interval: timedelta,
        include_donations: bool = True,
    ) -> None:
        """Set up the coordinator."""
        self.api = client
        self._include_donations = include_donations
        self._base_interval = update_interval
        self._consecutive_failures = 0
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_donor",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> DonorSnapshot:
        """Fetch a snapshot, mapping failures onto HA's coordinator contract."""
        try:
            snapshot = await self.api.async_get_snapshot(include_donations=self._include_donations)
        except InvalidAuth as err:
            # Do not back off: a reauth flow is the only thing that fixes this,
            # and HA stops polling once it's raised.
            _LOGGER.warning("Authentication is no longer valid; requesting reauthentication")
            raise ConfigEntryAuthFailed(str(err)) from err
        except CannotConnect as err:
            self._register_failure()
            raise UpdateFailed(f"Could not reach the NHS Give Blood API: {err}") from err
        except Exception as err:  # noqa: BLE001 - a coordinator must never leak
            self._register_failure()
            raise UpdateFailed(f"Unexpected error fetching donor data: {err}") from err

        self._register_success()

        if snapshot.partial:
            # A degraded snapshot is still usable: the account payload arrived.
            # Log once per poll at debug so it's diagnosable without being noisy.
            _LOGGER.debug("Snapshot degraded; these endpoints failed: %s", ", ".join(snapshot.degraded))

        self._persist_tokens()
        return snapshot

    # -- interval adaptation ----------------------------------------------

    def _register_failure(self) -> None:
        """Grow the poll interval after repeated failures."""
        self._consecutive_failures += 1
        if self._consecutive_failures < BACKOFF_FAILURE_THRESHOLD:
            return
        if self.update_interval is None or self.update_interval >= MAX_BACKOFF_INTERVAL:
            return
        self.update_interval = min(self.update_interval * 2, MAX_BACKOFF_INTERVAL)
        _LOGGER.info(
            "%s consecutive failures; backing off to polling every %s",
            self._consecutive_failures,
            self.update_interval,
        )

    def _register_success(self) -> None:
        """Restore the configured interval after recovery."""
        if self._consecutive_failures and self.update_interval != self._base_interval:
            _LOGGER.info("Recovered; restoring the %s poll interval", self._base_interval)
            self.update_interval = self._base_interval
        self._consecutive_failures = 0

    # -- token persistence -------------------------------------------------

    def _persist_tokens(self) -> None:
        """Write rotated tokens back to the config entry.

        Called after every successful poll. Tokens rotate roughly every 30
        minutes; without persisting them a Home Assistant restart would force a
        fresh password login, and if the stored password ever became stale that
        restart is when the integration would break.

        The write is skipped when nothing changed, because
        ``async_update_entry`` fires update listeners and an unconditional write
        would reload the entry on every poll.
        """
        entry = self.config_entry
        tokens = self.api.token_data
        if entry.data.get(CONF_TOKENS) == tokens:
            return
        self.hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_TOKENS: tokens})
