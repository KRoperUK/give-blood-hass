"""Binary sensor platform for the NHS Give Blood integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from nhs_give_blood import DonorSnapshot

from .const import ATTR_DEGRADED_ENDPOINTS
from .coordinator import GiveBloodConfigEntry, GiveBloodCoordinator
from .entity import GiveBloodEntity

_LOGGER = logging.getLogger(__name__)

# Read-only entities fed by a single coordinator fetch: there are no per-entity
# requests to serialise, and no actions that could write. Home Assistant's
# quality scale asks for this to be explicit rather than left to the default.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GiveBloodBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a binary sensor and how to derive its state."""

    value_fn: Callable[[DonorSnapshot], bool | None]
    attributes_fn: Callable[[DonorSnapshot], dict[str, Any]] | None = None


def _has_appointment(snapshot: DonorSnapshot) -> bool:
    """Whether any upcoming appointment is booked."""
    return bool(snapshot.upcoming_appointments)


def _is_eligible(snapshot: DonorSnapshot) -> bool | None:
    """Whether the donor is past their clinical deferral date.

    Compared date-to-date, not instant-to-instant: the API returns a midnight
    boundary, so comparing full timestamps would report "not eligible" for the whole
    of the eligible day.

    Both sides are converted into the *eligibility date's own* timezone first. That
    is Europe/London — NHSBT's dates are venue-local — whereas ``dt_util.now()``
    returns time in Home Assistant's configured timezone. Taking ``.date()`` of each
    without aligning them is wrong by up to a day for any instance not set to London,
    and wrong for everyone during the hour after London midnight in summer. Which is
    the same off-by-one this function comparing dates was meant to avoid.
    """
    eligible_from = snapshot.account.can_donate_from
    if eligible_from is None:
        return None
    now_there = dt_util.now().astimezone(eligible_from.tzinfo)
    return now_there.date() >= eligible_from.date()


def _booking_system_problem(snapshot: DonorSnapshot) -> bool | None:
    """Whether NHSBT has taken the booking system down.

    ``None`` when the banner endpoint was unreachable — reporting "no problem"
    from a failed check would be a false all-clear.
    """
    failover = snapshot.failover
    return failover.is_active if failover is not None else None


def _data_degraded(snapshot: DonorSnapshot) -> bool:
    """Whether any supplementary endpoint failed on the last poll."""
    return snapshot.partial


def _degraded_attributes(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Which endpoints failed, so the cause is diagnosable from the UI."""
    return {ATTR_DEGRADED_ENDPOINTS: list(snapshot.degraded)}


BINARY_SENSORS: tuple[GiveBloodBinarySensorEntityDescription, ...] = (
    GiveBloodBinarySensorEntityDescription(
        key="appointment_booked",
        translation_key="appointment_booked",
        icon="mdi:calendar-check",
        value_fn=_has_appointment,
    ),
    GiveBloodBinarySensorEntityDescription(
        key="eligible_to_donate",
        translation_key="eligible_to_donate",
        icon="mdi:account-check",
        value_fn=_is_eligible,
    ),
    GiveBloodBinarySensorEntityDescription(
        key="booking_system_problem",
        translation_key="booking_system_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_booking_system_problem,
    ),
    GiveBloodBinarySensorEntityDescription(
        key="data_degraded",
        translation_key="data_degraded",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_data_degraded,
        attributes_fn=_degraded_attributes,
    ),
    GiveBloodBinarySensorEntityDescription(
        key="platelet_plus",
        translation_key="platelet_plus",
        icon="mdi:star-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: snapshot.account.is_platelet_plus,
    ),
    GiveBloodBinarySensorEntityDescription(
        key="email_change_pending",
        translation_key="email_change_pending",
        icon="mdi:email-sync",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda snapshot: snapshot.account.email_change_pending,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiveBloodConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors for a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(GiveBloodBinarySensor(coordinator, entry, description) for description in BINARY_SENSORS)


class GiveBloodBinarySensor(GiveBloodEntity, BinarySensorEntity):
    """A binary sensor whose state comes from its description."""

    entity_description: GiveBloodBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: GiveBloodCoordinator,
        entry: GiveBloodConfigEntry,
        description: GiveBloodBinarySensorEntityDescription,
    ) -> None:
        """Bind the description."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """State derived from the latest snapshot."""
        snapshot = self.snapshot
        if snapshot is None:
            return None
        try:
            return self.entity_description.value_fn(snapshot)
        except Exception:  # noqa: BLE001 - one bad field must not sink the platform
            _LOGGER.exception("Could not derive a state for %s", self.entity_description.key)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Supplementary attributes, if the description supplies any."""
        snapshot = self.snapshot
        if snapshot is None or self.entity_description.attributes_fn is None:
            return None
        try:
            return self.entity_description.attributes_fn(snapshot) or None
        except Exception:  # noqa: BLE001 - attributes are supplementary
            _LOGGER.exception("Could not build attributes for %s", self.entity_description.key)
            return None
