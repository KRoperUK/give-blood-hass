"""Diagnostics for the NHS Give Blood integration.

Diagnostics get pasted into public GitHub issues, and every account endpoint in
this API returns the donor's name, address, phone number, date of birth and donor
ID. So this module inverts the usual approach: instead of dumping the payload and
redacting known-bad keys, it builds a summary from an explicit allowlist of
non-identifying fields.

An allowlist fails safe. A redaction list fails open the moment NHSBT adds a
field — and this is a reverse-engineered API, so it will.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from nhs_give_blood import Appointment, DonorSnapshot

from .const import CONF_TOKENS, DOMAIN, VERSION
from .coordinator import GiveBloodConfigEntry


def _fingerprint(value: str | None) -> str | None:
    """Stable, non-reversible short hash.

    Lets two reports be correlated as the same account without publishing the
    identifier.
    """
    if not value:
        return None
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def _library_version() -> str:
    """Installed version of the client library."""
    try:
        return version("nhs-give-blood")
    except PackageNotFoundError:  # pragma: no cover - always installed at runtime
        return "unknown"


def _appointment_summary(appointment: Appointment) -> dict[str, Any]:
    """Shape of an appointment, without the venue's identity.

    Venue name plus appointment dates is enough to place a person, so the venue
    is reduced to its capability flags.
    """
    venue = appointment.venue
    return {
        "starts_at": appointment.starts_at.isoformat() if appointment.starts_at else None,
        "procedure_code": appointment.procedure_code,
        "procedure_type": appointment.procedure_type,
        "status": appointment.status,
        "is_cancelled": appointment.is_cancelled,
        "has_session": appointment.session is not None,
        "session_status_combo": appointment.session.status_combo if appointment.session else None,
        "venue_present": venue is not None,
        "venue_is_donor_centre": venue.is_donor_centre if venue else None,
        "venue_supports": (
            {
                "whole_blood": venue.is_whole_blood_supported,
                "plasma": venue.is_plasma_supported,
                "platelet": venue.is_platelet_supported,
            }
            if venue
            else None
        ),
        "period_count": len(appointment.session.periods) if appointment.session else 0,
    }


def _snapshot_summary(snapshot: DonorSnapshot) -> dict[str, Any]:
    """Non-identifying summary of a snapshot."""
    account = snapshot.account
    awards = snapshot.awards_data
    eligibility = account.eligibility
    nearest = account.nearest_plasma_venue

    return {
        "degraded_endpoints": list(snapshot.degraded),
        "account": {
            # Blood group is one of eight values and drives most of the logic, so
            # it earns its place; nothing else identifying is included.
            "blood_group": account.blood_group,
            "donation_credit": account.donation_credit,
            "procedure_code": account.procedure_code,
            "procedure_type": account.procedure_type,
            "has_previous_donations": account.has_previous_donations,
            "has_donation_intent": account.has_donation_intent,
            "show_booking_cta": account.show_booking_cta,
            "is_platelet_plus": account.is_platelet_plus,
            "email_change_pending": account.email_change_pending,
            "serology_ro_enabled": account.serology.ro_enabled if account.serology else None,
            "address_count": len(account.addresses),
            "telephone_count": len(account.telephones),
            "email_count": len(account.emails),
            "registered_since_year": account.registration_date.year if account.registration_date else None,
            # Unmodelled keys are the useful signal when the API changes; the key
            # names are safe to publish, the values are not.
            "unmodelled_fields": sorted(account.model_extra or {}),
        },
        "eligibility": {
            "next_possible_donation_date": (
                eligibility.next_possible_donation_date.isoformat()
                if eligibility and eligibility.next_possible_donation_date
                else None
            ),
            "next_possible_appointment_date": (
                eligibility.next_possible_appointment_date.isoformat()
                if eligibility and eligibility.next_possible_appointment_date
                else None
            ),
        },
        "awards": (
            {
                "award_state": awards.award_state,
                "total_credits": awards.total_credits,
                "total_awards": awards.total_awards,
                "award_count": len(awards.awards),
                "next_award": awards.next_award.title if awards.next_award else None,
                "credits_to_next_award": awards.credits_to_next_award,
            }
            if awards
            else None
        ),
        "appointments": {
            "upcoming_count": len(snapshot.upcoming_appointments),
            "items": [_appointment_summary(item) for item in snapshot.upcoming_appointments],
        },
        "donations": (
            {
                "returned_count": len(snapshot.donations.donation),
                "truncated_by_api": snapshot.donations.has_further_donations,
                "type_codes": sorted({item.type for item in snapshot.donations.donation if item.type}),
            }
            if snapshot.donations
            else None
        ),
        "messages": (
            {
                "donor_message_count": len(snapshot.messages.donor_messages),
                "relevant_count": len(snapshot.messages.for_blood_group(account.blood_group)),
            }
            if snapshot.messages
            else None
        ),
        "features": snapshot.features.model_dump(mode="json") if snapshot.features else None,
        "failover_active": snapshot.failover.is_active if snapshot.failover else None,
        "nearest_plasma_venue": (
            {
                "distance": nearest.venue_distance,
                "session_day_count": nearest.session_day_count,
                "is_donor_centre": nearest.is_donor_centre,
                "is_community_centre": nearest.is_community_centre,
            }
            if nearest
            else None
        ),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: GiveBloodConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    snapshot = coordinator.data

    return {
        "integration": {
            "domain": DOMAIN,
            "version": VERSION,
            "library_version": _library_version(),
        },
        "entry": {
            # Every credential-bearing key is reported as presence only. The
            # username is an email address and the tokens are live credentials,
            # so neither value appears at any level of detail.
            "account_fingerprint": _fingerprint(entry.unique_id),
            "has_username": bool(entry.data.get(CONF_USERNAME)),
            "has_password": bool(entry.data.get(CONF_PASSWORD)),
            "has_stored_tokens": bool(entry.data.get(CONF_TOKENS)),
            "options": dict(entry.options),
            "entry_version": entry.version,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "has_data": snapshot is not None,
        },
        "snapshot": _snapshot_summary(snapshot) if snapshot is not None else None,
    }
