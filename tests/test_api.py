"""Adapter tests: library exceptions to Home Assistant error vocabulary.

This mapping is the highest-leverage code in the integration. Get it backwards and
either an NHSBT outage produces a stream of "reconfigure me" prompts the user
can't act on, or a genuinely changed password leaves the integration silently
retrying forever.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from nhs_give_blood import (
    GiveBloodApiError,
    GiveBloodAuthError,
    GiveBloodBookingError,
    GiveBloodConnectionError,
    GiveBloodError,
    GiveBloodInvalidCredentialsError,
    GiveBloodRateLimitError,
    GiveBloodTokenExpiredError,
)

from custom_components.nhs_give_blood.api import (
    CannotConnect,
    GiveBloodApiClient,
    InvalidAuth,
    translated_errors,
)

from .const import TEST_PASSWORD, TEST_USERNAME


class TestErrorTranslation:
    """The transient/reauth split, exercised exception by exception."""

    @pytest.mark.parametrize(
        "error",
        [
            GiveBloodConnectionError("socket died"),
            GiveBloodApiError(500, "server error"),
            GiveBloodApiError(404, "not found"),
            GiveBloodRateLimitError(429, "slow down", retry_after=30.0),
            GiveBloodBookingError(400, "refused"),
        ],
    )
    def test_transport_failures_become_cannot_connect(self, error: Exception) -> None:
        with pytest.raises(CannotConnect):  # noqa: SIM117 - context manager under test
            with translated_errors():
                raise error

    @pytest.mark.parametrize(
        "error",
        [
            GiveBloodInvalidCredentialsError(),
            GiveBloodTokenExpiredError(),
            GiveBloodAuthError("dead", reauth_required=True, transient=False),
        ],
    )
    def test_credential_failures_become_invalid_auth(self, error: Exception) -> None:
        with pytest.raises(InvalidAuth):  # noqa: SIM117
            with translated_errors():
                raise error

    def test_a_transient_auth_error_is_not_a_credential_problem(self) -> None:
        """A 5xx from the auth service must not trigger a reauth prompt."""
        error = GiveBloodAuthError("auth service down", reauth_required=False, transient=True)

        with pytest.raises(CannotConnect):  # noqa: SIM117
            with translated_errors():
                raise error

    def test_an_unknown_library_error_defaults_to_transient(self) -> None:
        """A new exception type must not strand the user in a reauth loop."""

        class FutureError(GiveBloodError):
            """Something a later library version might raise."""

        with pytest.raises(CannotConnect):  # noqa: SIM117
            with translated_errors():
                raise FutureError("new failure mode")

    def test_unrelated_exceptions_pass_through(self) -> None:
        """Only library errors are translated; a bug should still look like a bug."""
        with pytest.raises(ValueError):  # noqa: SIM117
            with translated_errors():
                raise ValueError("a real bug")

    def test_the_original_error_is_chained(self) -> None:
        """The cause has to survive, or the log line loses the actual reason."""
        original = GiveBloodConnectionError("socket died")

        with pytest.raises(CannotConnect) as excinfo:  # noqa: SIM117
            with translated_errors():
                raise original

        assert excinfo.value.__cause__ is original

    def test_nothing_is_raised_on_success(self) -> None:
        with translated_errors():
            pass


class TestClient:
    """Construction and delegation."""

    def test_uses_home_assistants_shared_session(self, hass: HomeAssistant) -> None:
        """Creating a session here would leak one per config entry."""
        with patch("custom_components.nhs_give_blood.api.async_get_clientsession") as get_session:
            GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)

        get_session.assert_called_once_with(hass)

    async def test_validate_returns_the_donor_id(self, hass: HomeAssistant) -> None:
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)

        with (
            patch.object(client._client, "async_ensure_authenticated", AsyncMock()),
            patch.object(type(client._client), "donor_id", "D0000000"),
        ):
            assert await client.async_validate() == "D0000000"

    async def test_validate_translates_an_auth_failure(self, hass: HomeAssistant) -> None:
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)

        with (
            patch.object(
                client._client,
                "async_ensure_authenticated",
                AsyncMock(side_effect=GiveBloodInvalidCredentialsError()),
            ),
            pytest.raises(InvalidAuth),
        ):
            await client.async_validate()

    async def test_snapshot_translates_a_connection_failure(self, hass: HomeAssistant) -> None:
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)

        with (
            patch.object(
                client._client,
                "async_get_snapshot",
                AsyncMock(side_effect=GiveBloodConnectionError("down")),
            ),
            pytest.raises(CannotConnect),
        ):
            await client.async_get_snapshot()

    async def test_snapshot_passes_the_donation_history_flag_through(self, hass: HomeAssistant) -> None:
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)
        inner = AsyncMock(return_value="snapshot")

        with patch.object(client._client, "async_get_snapshot", inner):
            await client.async_get_snapshot(include_donations=False)

        inner.assert_awaited_once_with(include_donations=False)

    async def test_token_data_is_a_plain_mapping(self, hass: HomeAssistant) -> None:
        """It gets stored in the config entry, so it must be JSON-friendly."""
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)
        tokens = client.token_data

        assert set(tokens) == {"access_token", "refresh_token", "expires_at"}

    async def test_stored_tokens_are_loaded(self, hass: HomeAssistant) -> None:
        client = GiveBloodApiClient(
            hass,
            tokens={"access_token": "a", "refresh_token": "r", "expires_at": 1.0},
        )
        assert client.token_data["refresh_token"] == "r"

    async def test_malformed_stored_tokens_do_not_raise(self, hass: HomeAssistant) -> None:
        """A corrupt config entry should degrade to "no tokens", not crash setup."""
        client = GiveBloodApiClient(hass, tokens={"expires_at": "not a number"})
        assert client.token_data["expires_at"] == 0.0

    async def test_logout_swallows_failures(self, hass: HomeAssistant) -> None:
        """Unloading an entry must not fail because sign-out didn't land."""
        client = GiveBloodApiClient(hass, username=TEST_USERNAME, password=TEST_PASSWORD)

        with patch.object(
            client._client,
            "async_logout",
            AsyncMock(side_effect=GiveBloodConnectionError("down")),
        ):
            await client.async_logout()
