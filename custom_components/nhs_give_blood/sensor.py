"""Sensor platform for the NHS Give Blood integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from nhs_give_blood import DonorSnapshot

from .const import (
    ATTR_APPOINTMENTS,
    ATTR_AWARDED_ON,
    ATTR_CREDITS_REQUIRED,
    ATTR_DONATIONS,
    ATTR_HISTORY_TRUNCATED,
    ATTR_MESSAGES,
    ATTR_POSTCODE,
    ATTR_PROCEDURE,
    ATTR_SESSION_ID,
    ATTR_VENUE,
    ATTR_VENUE_ADDRESS,
    ATTR_VENUE_ID,
    ATTR_VENUE_LATITUDE,
    ATTR_VENUE_LONGITUDE,
    MAX_APPOINTMENT_ATTRS,
    MAX_DONATION_ATTRS,
    MAX_MESSAGE_ATTRS,
)
from .coordinator import GiveBloodConfigEntry, GiveBloodCoordinator
from .entity import GiveBloodEntity
from .helpers import limit_attributes, safe_datetime, safe_number, safe_state

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class GiveBloodSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor, including how to derive its value.

    ``value_fn`` takes the whole snapshot rather than the account payload, because
    several sensors span multiple endpoints (award progress, degradation state).
    """

    value_fn: Callable[[DonorSnapshot], Any]
    attributes_fn: Callable[[DonorSnapshot], dict[str, Any]] | None = None
    #: Attribute keys that may be halved to fit the recorder's byte budget.
    shrinkable_attributes: tuple[str, ...] = ()


# --- value helpers ----------------------------------------------------------
#
# Each of these must tolerate a partially-populated payload: every field in this
# API is optional in practice, and a raised exception inside a `native_value`
# property breaks the whole state write, not just one attribute.


def _blood_group(snapshot: DonorSnapshot) -> str | None:
    """Donor blood group."""
    return safe_state(snapshot.account.blood_group)


def _award_level(snapshot: DonorSnapshot) -> str | None:
    """Current award tier, or "None" before the first tier is reached."""
    awards = snapshot.awards_data
    return safe_state(awards.award_state) if awards else None


def _next_award(snapshot: DonorSnapshot) -> str | None:
    """Title of the next unachieved milestone."""
    awards = snapshot.awards_data
    if awards is None or (nxt := awards.next_award) is None:
        return None
    return safe_state(nxt.title)


def _next_award_attributes(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Credit threshold and, for context, when the current tier was awarded."""
    awards = snapshot.awards_data
    if awards is None:
        return {}
    attributes: dict[str, Any] = {}
    if (nxt := awards.next_award) is not None:
        attributes[ATTR_CREDITS_REQUIRED] = nxt.credit_criteria
    if (highest := awards.highest_achieved) is not None and highest.awarded_date:
        attributes[ATTR_AWARDED_ON] = highest.awarded_date.date().isoformat()
    return attributes


def _credits_to_next_award(snapshot: DonorSnapshot) -> int | None:
    """Credits still needed for the next milestone."""
    awards = snapshot.awards_data
    return awards.credits_to_next_award if awards else None


def _next_appointment(snapshot: DonorSnapshot) -> datetime | None:
    """Start time of the soonest upcoming appointment."""
    appointment = snapshot.next_appointment
    return safe_datetime(appointment.starts_at) if appointment else None


def _appointment_attributes(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Venue and procedure detail for the next appointment, plus the full list."""
    appointment = snapshot.next_appointment
    attributes: dict[str, Any] = {}
    if appointment is not None:
        attributes[ATTR_PROCEDURE] = appointment.procedure_description
        attributes[ATTR_SESSION_ID] = appointment.session_id
        if (venue := appointment.venue) is not None:
            attributes[ATTR_VENUE] = venue.display_name
            attributes[ATTR_VENUE_ID] = venue.venue_id
            attributes[ATTR_VENUE_LATITUDE] = venue.latitude
            attributes[ATTR_VENUE_LONGITUDE] = venue.longitude
            if venue.address is not None:
                attributes[ATTR_VENUE_ADDRESS] = venue.address.one_line
                attributes[ATTR_POSTCODE] = venue.address.postcode

    attributes[ATTR_APPOINTMENTS] = [
        {
            "starts_at": item.starts_at.isoformat() if item.starts_at else None,
            "procedure": item.procedure_description,
            "venue": item.venue.display_name if item.venue else None,
            "session_id": item.session_id,
        }
        for item in snapshot.upcoming_appointments[:MAX_APPOINTMENT_ATTRS]
    ]
    return attributes


def _next_appointment_venue(snapshot: DonorSnapshot) -> str | None:
    """Venue name for the next appointment."""
    appointment = snapshot.next_appointment
    if appointment is None or (venue := appointment.venue) is None:
        return None
    return safe_state(venue.display_name)


def _upcoming_count(snapshot: DonorSnapshot) -> int:
    """Number of upcoming appointments."""
    return len(snapshot.upcoming_appointments)


def _eligible_from(snapshot: DonorSnapshot) -> datetime | None:
    """Clinical eligibility date — when the donor may next donate."""
    return safe_datetime(snapshot.account.can_donate_from)


def _bookable_from(snapshot: DonorSnapshot) -> datetime | None:
    """Earliest date the donor may book, which is not the same as eligibility."""
    eligibility = snapshot.account.eligibility
    return safe_datetime(eligibility.next_possible_appointment_date) if eligibility else None


def _last_donation(snapshot: DonorSnapshot) -> datetime | None:
    """Date of the most recent recorded donation."""
    history = snapshot.donations
    if history is None or (recent := history.most_recent) is None:
        return None
    return safe_datetime(recent.donated_at)


def _donations_recorded(snapshot: DonorSnapshot) -> int | None:
    """How many donations the API returned.

    A lower bound, not a lifetime total: the API truncates long histories. Use
    the credits sensor for the authoritative count.
    """
    history = snapshot.donations
    return len(history.donation) if history else None


def _donation_attributes(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Recent donations, and whether the API truncated the list."""
    history = snapshot.donations
    if history is None:
        return {}
    ordered = sorted(
        (item for item in history.donation if item.donated_at is not None),
        key=lambda item: item.donated_at,  # type: ignore[arg-type,return-value]
        reverse=True,
    )
    return {
        ATTR_HISTORY_TRUNCATED: history.has_further_donations,
        ATTR_DONATIONS: [
            {
                "date": item.donated_at.date().isoformat() if item.donated_at else None,
                "venue": item.venue_name,
                "type": item.type,
            }
            for item in ordered[:MAX_DONATION_ATTRS]
        ],
    }


def _message_count(snapshot: DonorSnapshot) -> int | None:
    """Messages targeted at this donor's blood group."""
    messages = snapshot.messages
    if messages is None:
        return None
    return len(messages.for_blood_group(snapshot.account.blood_group))


def _message_attributes(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Titles and bodies of the donor's messages."""
    messages = snapshot.messages
    if messages is None:
        return {}
    relevant = messages.for_blood_group(snapshot.account.blood_group)
    return {
        ATTR_MESSAGES: [
            {"title": item.title, "text": item.text, "id": item.id} for item in relevant[:MAX_MESSAGE_ATTRS]
        ]
    }


def _plasma_venue_distance(snapshot: DonorSnapshot) -> float | None:
    """Distance to the nearest plasma venue.

    The API reports distances unitless; the app renders them as miles, so that is
    what is assumed here.
    """
    nearest = snapshot.account.nearest_plasma_venue
    if nearest is None:
        return None
    value = safe_number(nearest.venue_distance)
    return round(float(value), 1) if value is not None else None


def _plasma_venue_name(snapshot: DonorSnapshot) -> str | None:
    """Name of the nearest plasma venue."""
    nearest = snapshot.account.nearest_plasma_venue
    if nearest is None or nearest.venue is None:
        return None
    return safe_state(nearest.venue.display_name)


SENSORS: tuple[GiveBloodSensorEntityDescription, ...] = (
    GiveBloodSensorEntityDescription(
        key="donation_credits",
        translation_key="donation_credits",
        icon="mdi:water-plus",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="credits",
        value_fn=lambda snapshot: snapshot.account.donation_credit,
    ),
    GiveBloodSensorEntityDescription(
        key="blood_group",
        translation_key="blood_group",
        icon="mdi:blood-bag",
        value_fn=_blood_group,
    ),
    GiveBloodSensorEntityDescription(
        key="award_level",
        translation_key="award_level",
        icon="mdi:medal",
        value_fn=_award_level,
    ),
    GiveBloodSensorEntityDescription(
        key="next_award",
        translation_key="next_award",
        icon="mdi:medal-outline",
        value_fn=_next_award,
        attributes_fn=_next_award_attributes,
    ),
    GiveBloodSensorEntityDescription(
        key="credits_to_next_award",
        translation_key="credits_to_next_award",
        icon="mdi:counter",
        native_unit_of_measurement="credits",
        value_fn=_credits_to_next_award,
    ),
    GiveBloodSensorEntityDescription(
        key="total_awards",
        translation_key="total_awards",
        icon="mdi:trophy",
        value_fn=lambda snapshot: snapshot.awards_data.total_awards if snapshot.awards_data else None,
    ),
    GiveBloodSensorEntityDescription(
        key="next_appointment",
        translation_key="next_appointment",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_appointment,
        attributes_fn=_appointment_attributes,
        shrinkable_attributes=(ATTR_APPOINTMENTS,),
    ),
    GiveBloodSensorEntityDescription(
        key="next_appointment_venue",
        translation_key="next_appointment_venue",
        icon="mdi:map-marker",
        value_fn=_next_appointment_venue,
    ),
    GiveBloodSensorEntityDescription(
        key="upcoming_appointments",
        translation_key="upcoming_appointments",
        icon="mdi:calendar-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_upcoming_count,
    ),
    GiveBloodSensorEntityDescription(
        key="eligible_from",
        translation_key="eligible_from",
        icon="mdi:calendar-check",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_eligible_from,
    ),
    GiveBloodSensorEntityDescription(
        key="bookable_from",
        translation_key="bookable_from",
        icon="mdi:calendar-plus",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_bookable_from,
    ),
    GiveBloodSensorEntityDescription(
        key="last_donation",
        translation_key="last_donation",
        icon="mdi:history",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_donation,
    ),
    GiveBloodSensorEntityDescription(
        key="donations_recorded",
        translation_key="donations_recorded",
        icon="mdi:format-list-numbered",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_donations_recorded,
        attributes_fn=_donation_attributes,
        shrinkable_attributes=(ATTR_DONATIONS,),
    ),
    GiveBloodSensorEntityDescription(
        key="donor_messages",
        translation_key="donor_messages",
        icon="mdi:message-text",
        value_fn=_message_count,
        attributes_fn=_message_attributes,
        shrinkable_attributes=(ATTR_MESSAGES,),
    ),
    GiveBloodSensorEntityDescription(
        key="nearest_plasma_venue_distance",
        translation_key="nearest_plasma_venue_distance",
        icon="mdi:map-marker-distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILES,
        # Off by default: only relevant to donors considering plasma.
        entity_registry_enabled_default=False,
        value_fn=_plasma_venue_distance,
    ),
    GiveBloodSensorEntityDescription(
        key="nearest_plasma_venue",
        translation_key="nearest_plasma_venue",
        icon="mdi:map-marker-radius",
        entity_registry_enabled_default=False,
        value_fn=_plasma_venue_name,
    ),
    GiveBloodSensorEntityDescription(
        key="donation_type",
        translation_key="donation_type",
        icon="mdi:needle",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda snapshot: safe_state(snapshot.account.procedure_description),
    ),
    GiveBloodSensorEntityDescription(
        key="registered_since",
        translation_key="registered_since",
        icon="mdi:card-account-details",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda snapshot: safe_datetime(snapshot.account.registration_date),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GiveBloodConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors for a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(GiveBloodSensor(coordinator, entry, description) for description in SENSORS)


class GiveBloodSensor(GiveBloodEntity, SensorEntity):
    """A sensor whose value and attributes come from its description."""

    entity_description: GiveBloodSensorEntityDescription

    def __init__(
        self,
        coordinator: GiveBloodCoordinator,
        entry: GiveBloodConfigEntry,
        description: GiveBloodSensorEntityDescription,
    ) -> None:
        """Bind the description."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Value derived from the latest snapshot.

        A value function that raises is contained here: one broken sensor becomes
        ``unknown`` rather than breaking every entity's state write.
        """
        snapshot = self.snapshot
        if snapshot is None:
            return None
        try:
            return self.entity_description.value_fn(snapshot)
        except Exception:  # noqa: BLE001 - one bad field must not sink the platform
            _LOGGER.exception("Could not derive a value for %s", self.entity_description.key)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes, trimmed to fit the recorder's byte budget."""
        snapshot = self.snapshot
        if snapshot is None or self.entity_description.attributes_fn is None:
            return None
        try:
            attributes = self.entity_description.attributes_fn(snapshot)
        except Exception:  # noqa: BLE001 - attributes are supplementary
            _LOGGER.exception("Could not build attributes for %s", self.entity_description.key)
            return None
        if not attributes:
            return None
        return limit_attributes(attributes, shrinkable=self.entity_description.shrinkable_attributes)
