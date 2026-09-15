"""Constants for the NHS Give Blood integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

NAME: Final = "NHS Give Blood"
DOMAIN: Final = "nhs_give_blood"
VERSION: Final = "1.1.0"  # x-release-please-version
MANUFACTURER: Final = "NHS Blood and Transplant"

DOCS_URL: Final = "https://github.com/KRoperUK/give-blood-hass"
ISSUE_URL: Final = "https://github.com/KRoperUK/give-blood-hass/issues"

PLATFORMS: Final = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

# --- config entry keys -------------------------------------------------------

CONF_TOKENS: Final = "tokens"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"
CONF_INCLUDE_DONATION_HISTORY: Final = "include_donation_history"

# --- polling -----------------------------------------------------------------

# Donor data changes on the order of days: eligibility dates move after a
# donation, appointments when the donor books. Polling faster than this asks a
# public health service for data that cannot have changed. 30 minutes keeps
# "I just booked in the app" feeling responsive without being rude.
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)
MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 1440

# On repeated failures the coordinator backs off to this, so an NHSBT outage
# doesn't mean a request every 30 minutes for hours.
MAX_BACKOFF_INTERVAL: Final = timedelta(hours=4)
BACKOFF_FAILURE_THRESHOLD: Final = 3

# --- attribute budget --------------------------------------------------------

# HA's recorder silently discards an entity's *entire* attribute blob when the
# serialised JSON exceeds 16,384 bytes: no error is logged, the entity looks
# healthy, and the attributes are simply gone after a restart. Staying well
# under leaves room for HA's own added keys.
ATTRIBUTE_BYTE_BUDGET: Final = 12_000

# Caps on list-valued attributes, applied before the byte budget so the common
# case never needs truncating at all.
MAX_APPOINTMENT_ATTRS: Final = 10
MAX_DONATION_ATTRS: Final = 20
MAX_MESSAGE_ATTRS: Final = 10

# A state value over 255 characters is rejected by HA. Message titles and venue
# names are the realistic candidates.
MAX_STATE_LENGTH: Final = 255

# --- attribute names ---------------------------------------------------------

ATTR_APPOINTMENTS: Final = "appointments"
ATTR_AWARDED_ON: Final = "awarded_on"
ATTR_CREDITS_REQUIRED: Final = "credits_required"
ATTR_DEGRADED_ENDPOINTS: Final = "degraded_endpoints"
ATTR_DONATIONS: Final = "donations"
ATTR_HISTORY_TRUNCATED: Final = "history_truncated"
ATTR_MESSAGES: Final = "messages"
ATTR_POSTCODE: Final = "postcode"
ATTR_PROCEDURE: Final = "procedure"
ATTR_SESSION_ID: Final = "session_id"
ATTR_TRUNCATED: Final = "truncated"
ATTR_VENUE: Final = "venue"
ATTR_VENUE_ADDRESS: Final = "venue_address"
ATTR_VENUE_ID: Final = "venue_id"
ATTR_VENUE_LATITUDE: Final = "venue_latitude"
ATTR_VENUE_LONGITUDE: Final = "venue_longitude"

STARTUP_MESSAGE: Final = f"""
{NAME} {VERSION} — unofficial integration for the NHS Give Blood donor API.
This is not supported by NHS Blood and Transplant.
Issues: {ISSUE_URL}
"""
