"""Synthetic test data for the NHS Give Blood integration.

Nothing here is derived from a real donor account. Values use ranges reserved by
standard so they can never collide with a real person: RFC 6761 ``.invalid`` for
the email, Royal Mail's ``ZZ99`` outcode for the postcode, and an all-zero donor
identifier.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.nhs_give_blood.const import CONF_TOKENS

LONDON = ZoneInfo("Europe/London")

DONOR_ID = "D0000000"
TEST_USERNAME = "donor@example.invalid"
TEST_PASSWORD = "not-a-real-password"  # noqa: S105 - synthetic


def _b64(payload: dict[str, Any]) -> str:
    """URL-safe base64 without padding, the way JWTs encode segments."""
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def make_access_token(*, ttl: float = 1800.0, donor_id: str = DONOR_ID) -> str:
    """Build an unsigned JWT shaped like a real access token.

    The signature is meaningless — the library reads ``exp`` without verifying —
    but the *shape* matters, because the donor id used for the config entry's
    unique id is read out of the claims.
    """
    header = _b64({"typ": "JWT", "alg": "RS256"})
    claims = _b64({"exp": int(time.time() + ttl), "donor_id": donor_id, "user_id": "U0000000", "can_book": True})
    return f"{header}.{claims}.synthetic-signature"


def make_tokens() -> dict[str, Any]:
    """A persisted token bundle."""
    return {
        "access_token": make_access_token(),
        "refresh_token": "synthetic-refresh-token",
        "expires_at": time.time() + 1800,
    }


MOCK_CONFIG: dict[str, Any] = {
    CONF_USERNAME: TEST_USERNAME,
    CONF_PASSWORD: TEST_PASSWORD,
    CONF_TOKENS: {
        "access_token": "synthetic.access.token",
        "refresh_token": "synthetic-refresh-token",
        "expires_at": 0,
    },
}


def _iso(value: datetime) -> str:
    """Render a naive local datetime the way the API does."""
    return value.replace(tzinfo=None).isoformat()


def _venue(*, venue_id: str = "TSTV1", donor_centre: bool = True) -> dict[str, Any]:
    """A synthetic venue."""
    return {
        "venueId": venue_id,
        "venueName": "Testville, Example Donor Centre",
        "donorPreferred": True,
        "externalLocation": "Example Building",
        "internalLocation": "Main Hall",
        "address": {
            "type": "V",
            "companyName": None,
            "lines": ["1 Example Street", "Testville"],
            "postcode": "ZZ99 3WZ",
            "latitude": "53.46",
            "longitude": "-2.21",
        },
        "latitude": "53.46",
        "longitude": "-2.21",
        "notes": ["Parking available", "Step-free access"],
        "isWholeBloodSupported": True,
        "isPlasmaSupported": False,
        "isPlateletSupported": True,
        "isDonorCentre": donor_centre,
    }


def _appointment(*, days_ahead: int, clock: str = "T1730", procedure: str = "PLT") -> dict[str, Any]:
    """A synthetic appointment ``days_ahead`` days from now."""
    session_date = (datetime.now(LONDON) + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return {
        "status": "A",
        "time": clock,
        "procedureCode": procedure,
        "procedureType": "Platelet" if procedure == "PLT" else "Whole Blood",
        "procedureDescription": "Platelet" if procedure == "PLT" else "Whole Blood",
        "cancellationCode": None,
        "session": {
            "sessionId": f"CS{1000 + days_ahead}",
            "sessionDate": _iso(session_date),
            "venue": _venue(),
            "periods": [
                {"startTime": "1130", "endTime": "1500", "freeSlots": "-1", "availableSlots": 0},
                {"startTime": "1545", "endTime": "1930", "freeSlots": "4", "availableSlots": 4},
            ],
            "sessionStatus": "C",
            "bookingFlag": "Y",
            "appointmentStatus": "Y",
            "availability": "Y",
            "weightingFactor": None,
            "notes": [],
        },
    }


AWARDS_PAYLOAD: dict[str, Any] = {
    "registrationDate": "2020-02-01T00:00:00",
    "awardState": "Bronze",
    "showAsAchievement": True,
    "totalCredits": 15,
    "totalAwards": 6,
    "awards": [
        {"isAchieved": True, "title": "1 Credit", "awardedDate": "2020-10-15T00:00:00", "creditCriteria": 1},
        {"isAchieved": True, "title": "Bronze", "awardedDate": "2025-03-10T00:00:00", "creditCriteria": 10},
        {"isAchieved": False, "title": "Silver", "awardedDate": None, "creditCriteria": 25},
        {"isAchieved": False, "title": "Gold", "awardedDate": None, "creditCriteria": 50},
    ],
    "highestAchieved": {
        "isAchieved": True,
        "title": "Bronze",
        "awardedDate": "2025-03-10T00:00:00",
        "creditCriteria": 10,
    },
}


def account_payload(**overrides: Any) -> dict[str, Any]:
    """A synthetic ``/api/account/v2/details`` payload."""
    now = datetime.now(LONDON)
    payload: dict[str, Any] = {
        "donorID": DONOR_ID,
        "title": "Ms",
        "forenames": {"firstForename": "Ada", "secondForename": "", "otherForenames": ""},
        "surname": "Testerson",
        "bloodGroup": "A-",
        "serology": {"shortHand": "rr", "roEnabled": False},
        "gender": "Not specified",
        "genderIdentity": "Not specified",
        "sexAtBirth": "Not specified",
        "ethnicOrigin": "00",
        "ethnicOriginDescription": "Not specified",
        "dateOfBirth": "1990-01-01T00:00:00",
        "registrationDate": "2020-02-01T00:00:00",
        "donationCredit": 15,
        "eligibility": {
            "nextPossibleDonationDate": _iso(
                (now - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
            ),
            "nextPossibleAppointmentDate": _iso(
                (now + timedelta(days=40)).replace(hour=0, minute=0, second=0, microsecond=0)
            ),
        },
        "searchDatesFrom": {
            "donationIntent": None,
            "wholeBlood": _iso((now + timedelta(days=27)).replace(hour=0, minute=0, second=0, microsecond=0)),
            "plasma": _iso((now + timedelta(days=27)).replace(hour=0, minute=0, second=0, microsecond=0)),
        },
        "hasDonationIntent": False,
        "hasPreviousDonations": True,
        "procedureType": "Platelet",
        "procedureCode": "PL1",
        "procedureDescription": "Platelet",
        "showBookingCTA": True,
        "showWelcomePage": False,
        "isPlateletPlus": False,
        "referToCallCentre": "N",
        "emailChangePending": False,
        "lastDonatedVenueId": "TSTV1",
        "appointments": [_appointment(days_ahead=23), _appointment(days_ahead=39, clock="T1015")],
        "awardsData": AWARDS_PAYLOAD,
        "nearestPlasmaVenue": {
            "venue": _venue(venue_id="TSTV2", donor_centre=False),
            "sessionDayCount": 0,
            "venueDistance": 9.929378421397633,
            "venueDistanceFromHome": None,
            "dateOfNextSession": "0001-01-01T00:00:00",
            "isDonorCentre": False,
            "isCommunityCentre": True,
            "isWholeBloodSupported": False,
            "isPlasmaSupported": True,
            "isPlateletSupported": False,
        },
        "registrationVenue": None,
        "addresses": [
            {
                "type": "H",
                "companyName": None,
                "lines": ["1 Example Street", "Testville", "Example County"],
                "postcode": "ZZ99 3WZ",
                "latitude": "53.46",
                "longitude": "-2.21",
            }
        ],
        "telephones": [{"type": "M", "number": "07700900000"}],
        "emails": [{"type": "H", "address": TEST_USERNAME}],
        "venues": [],
        "language": "EN",
        "correspondence": "H",
    }
    payload.update(overrides)
    return payload


def appointments_payload() -> list[dict[str, Any]]:
    """A synthetic ``/api/appointments/future`` payload."""
    return [_appointment(days_ahead=23), _appointment(days_ahead=39, clock="T1015")]


def donation_history_payload() -> dict[str, Any]:
    """A synthetic ``/api/account/donation-history`` payload."""
    now = datetime.now(LONDON)
    return {
        "donorID": DONOR_ID,
        "hasFurtherDonations": True,
        "donation": [
            {
                "donationId": "G000000000000X",
                "type": "A",
                "session": {
                    "sessionId": "CS0000",
                    "sessionDate": _iso((now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)),
                    "venue": _venue(),
                    "periods": [],
                    "sessionStatus": None,
                    "bookingFlag": None,
                    "appointmentStatus": None,
                    "availability": None,
                    "weightingFactor": None,
                    "notes": [],
                },
            },
            {
                "donationId": "G000000000000X",
                "type": "R",
                "session": {
                    "sessionId": "CS0001",
                    "sessionDate": _iso((now - timedelta(days=45)).replace(hour=0, minute=0, second=0, microsecond=0)),
                    "venue": _venue(),
                    "periods": [],
                    "sessionStatus": None,
                    "bookingFlag": None,
                    "appointmentStatus": None,
                    "availability": None,
                    "weightingFactor": None,
                    "notes": [],
                },
            },
        ],
    }


def messages_payload() -> dict[str, Any]:
    """A synthetic ``/api/messages`` payload."""
    return {
        "donorMessages": [
            {
                "type": "donorMessages",
                "title": "A negative donors!",
                "text": "Your blood type is in high demand.",
                "showOnlyOnce": False,
                "id": "00000000-0000-0000-0000-000000000001",
                "bloodGroups": ["A-"],
            },
            {
                "type": "donorMessages",
                "title": "Great news!",
                "text": "Not for this blood group.",
                "showOnlyOnce": False,
                "id": "00000000-0000-0000-0000-000000000002",
                "bloodGroups": ["O-"],
            },
        ],
        "endOfBooking": [],
        "endOfSignUp": [],
    }


FEATURES_PAYLOAD: dict[str, Any] = {
    "appointmentRequestBetaBanner": False,
    "chatbot": True,
    "checkIn": True,
    "failover": False,
    "parFullSessions": False,
    "waitingList": True,
}

FAILOVER_PAYLOAD: dict[str, Any] = {
    "header": "Booking system unavailable",
    "content": "Our online appointment service is unavailable while we make some important system updates.",
    "isActive": False,
}

# Reference instant used by tests that assert on relative dates.
FIXED_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
