"""Pytest fixtures for the NHS Give Blood integration tests.

Tests patch the *adapter* (``GiveBloodApiClient``) rather than HTTP. The library
already has 244 tests covering its transport, retry and auth behaviour; repeating
that here would test the library twice and the integration once. What matters on
this side is how Home Assistant reacts to each adapter outcome.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from nhs_give_blood import (
    AccountDetails,
    Appointment,
    DonationHistory,
    DonorSnapshot,
    FailoverBanner,
    FeatureFlags,
    MessageBundle,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.api import CannotConnect, InvalidAuth
from custom_components.nhs_give_blood.const import DOMAIN

from .const import (
    DONOR_ID,
    FAILOVER_PAYLOAD,
    FEATURES_PAYLOAD,
    MOCK_CONFIG,
    account_payload,
    appointments_payload,
    donation_history_payload,
    messages_payload,
)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Load the custom integration in every test."""
    return


@pytest.fixture(autouse=True)
def skip_notifications() -> Generator[None]:
    """Suppress persistent notifications, which tests don't assert on."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


def build_snapshot(
    *, degraded: tuple[str, ...] = (), include_donations: bool = True, **overrides: Any
) -> DonorSnapshot:
    """Build a snapshot from the synthetic payloads.

    ``account`` may be overridden with a raw payload dict; every other keyword
    replaces the corresponding snapshot field directly.
    """
    account = AccountDetails.model_validate(overrides.pop("account", account_payload()))
    fields: dict[str, Any] = {
        "account": account,
        "appointments": [Appointment.model_validate(item) for item in appointments_payload()],
        "donations": DonationHistory.model_validate(donation_history_payload()) if include_donations else None,
        "awards": account.awards_data,
        "messages": MessageBundle.model_validate(messages_payload()),
        "features": FeatureFlags.model_validate(FEATURES_PAYLOAD),
        "failover": FailoverBanner.model_validate(FAILOVER_PAYLOAD),
        "degraded": degraded,
    }
    fields.update(overrides)
    return DonorSnapshot(**fields)


@pytest.fixture
def snapshot() -> DonorSnapshot:
    """A clean, fully-populated snapshot."""
    return build_snapshot()


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry keyed by the synthetic donor id."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="NHS Give Blood",
        data=dict(MOCK_CONFIG),
        unique_id=DONOR_ID,
    )


@pytest.fixture
def mock_api(snapshot: DonorSnapshot) -> Generator[AsyncMock]:
    """Patch the adapter so setup succeeds and returns ``snapshot``.

    Patched at the two import sites that construct it — ``__init__`` for entry
    setup and ``config_flow`` for validation — because each module imported the
    class by name.
    """
    with (
        patch("custom_components.nhs_give_blood.GiveBloodApiClient", autospec=True) as init_mock,
        patch("custom_components.nhs_give_blood.config_flow.GiveBloodApiClient", autospec=True) as flow_mock,
    ):
        instance = init_mock.return_value
        instance.async_validate = AsyncMock(return_value=DONOR_ID)
        instance.async_get_snapshot = AsyncMock(return_value=snapshot)
        instance.async_logout = AsyncMock()
        instance.donor_id = DONOR_ID
        instance.token_data = dict(MOCK_CONFIG["tokens"])
        flow_mock.return_value = instance
        yield instance


@pytest.fixture
def mock_api_invalid_auth() -> Generator[AsyncMock]:
    """Patch the adapter so authentication is rejected."""
    with (
        patch("custom_components.nhs_give_blood.GiveBloodApiClient", autospec=True) as init_mock,
        patch("custom_components.nhs_give_blood.config_flow.GiveBloodApiClient", autospec=True) as flow_mock,
    ):
        instance = init_mock.return_value
        instance.async_validate = AsyncMock(side_effect=InvalidAuth("rejected"))
        instance.async_get_snapshot = AsyncMock(side_effect=InvalidAuth("rejected"))
        instance.async_logout = AsyncMock()
        instance.donor_id = None
        instance.token_data = {}
        flow_mock.return_value = instance
        yield instance


@pytest.fixture
def mock_api_cannot_connect() -> Generator[AsyncMock]:
    """Patch the adapter so the API is unreachable."""
    with (
        patch("custom_components.nhs_give_blood.GiveBloodApiClient", autospec=True) as init_mock,
        patch("custom_components.nhs_give_blood.config_flow.GiveBloodApiClient", autospec=True) as flow_mock,
    ):
        instance = init_mock.return_value
        instance.async_validate = AsyncMock(side_effect=CannotConnect("unreachable"))
        instance.async_get_snapshot = AsyncMock(side_effect=CannotConnect("unreachable"))
        instance.async_logout = AsyncMock()
        instance.donor_id = None
        instance.token_data = {}
        flow_mock.return_value = instance
        yield instance


async def setup_integration(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up a config entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
