"""Config and options flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.api import CannotConnect, InvalidAuth
from custom_components.nhs_give_blood.const import (
    CONF_INCLUDE_DONATION_HISTORY,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TOKENS,
    DOMAIN,
)

from .conftest import setup_integration
from .const import DONOR_ID, TEST_PASSWORD, TEST_USERNAME, make_tokens

USER_INPUT = {CONF_USERNAME: TEST_USERNAME, CONF_PASSWORD: TEST_PASSWORD}


class TestUserFlow:
    """Initial setup."""

    async def test_shows_the_form_first(self, hass: HomeAssistant, mock_api: AsyncMock) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert not result["errors"]

    async def test_creates_an_entry(self, hass: HomeAssistant, mock_api: AsyncMock) -> None:
        with patch("custom_components.nhs_give_blood.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
            result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "NHS Give Blood"
        assert result["data"][CONF_USERNAME] == TEST_USERNAME
        assert result["data"][CONF_TOKENS]

    async def test_unique_id_is_the_donor_id_not_the_email(self, hass: HomeAssistant, mock_api: AsyncMock) -> None:
        """The same account reached with a changed email must still be a duplicate."""
        with patch("custom_components.nhs_give_blood.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
            await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.unique_id == DONOR_ID

    async def test_whitespace_is_trimmed_from_the_email(self, hass: HomeAssistant, mock_api: AsyncMock) -> None:
        with patch("custom_components.nhs_give_blood.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {**USER_INPUT, CONF_USERNAME: f"  {TEST_USERNAME}  "}
            )

        assert result["data"][CONF_USERNAME] == TEST_USERNAME

    async def test_duplicate_account_is_rejected(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestUserFlowErrors:
    """Each failure mode gets its own message, and the form stays open."""

    async def test_invalid_auth(self, hass: HomeAssistant, mock_api_invalid_auth: AsyncMock) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_cannot_connect(self, hass: HomeAssistant, mock_api_cannot_connect: AsyncMock) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}

    async def test_unexpected_error_shows_a_message_not_a_traceback(
        self, hass: HomeAssistant, mock_api: AsyncMock
    ) -> None:
        mock_api.async_validate = AsyncMock(side_effect=RuntimeError("boom"))

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "unknown"}

    async def test_recovers_after_a_failed_attempt(self, hass: HomeAssistant, mock_api: AsyncMock) -> None:
        """A wrong password must not force the user to restart the flow."""
        mock_api.async_validate = AsyncMock(side_effect=InvalidAuth("nope"))
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        assert result["errors"] == {"base": "invalid_auth"}

        mock_api.async_validate = AsyncMock(return_value=DONOR_ID)
        with patch("custom_components.nhs_give_blood.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.CREATE_ENTRY


class TestReauthFlow:
    """Recovering from rejected credentials."""

    async def _start_reauth(self, hass: HomeAssistant, entry: MockConfigEntry) -> dict:
        return await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=dict(entry.data),
        )

    async def test_shows_the_confirm_form(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        result = await self._start_reauth(hass, config_entry)

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

    async def test_updates_credentials_and_tokens(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        new_tokens = make_tokens()
        mock_api.token_data = new_tokens

        result = await self._start_reauth(hass, config_entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: TEST_USERNAME, CONF_PASSWORD: "a-new-password"}
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert config_entry.data[CONF_PASSWORD] == "a-new-password"
        assert config_entry.data[CONF_TOKENS] == new_tokens

    async def test_rejects_credentials_for_a_different_account(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Otherwise every entity would silently start describing another donor."""
        config_entry.add_to_hass(hass)
        mock_api.async_validate = AsyncMock(return_value="D0000009")  # pii-allow - synthetic other account

        result = await self._start_reauth(hass, config_entry)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "other@example.invalid", CONF_PASSWORD: TEST_PASSWORD}
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "wrong_account"

    async def test_surfaces_invalid_auth(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        mock_api.async_validate = AsyncMock(side_effect=InvalidAuth("still wrong"))

        result = await self._start_reauth(hass, config_entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_surfaces_cannot_connect(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        mock_api.async_validate = AsyncMock(side_effect=CannotConnect("down"))

        result = await self._start_reauth(hass, config_entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["errors"] == {"base": "cannot_connect"}

    async def test_surfaces_unexpected_errors(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        config_entry.add_to_hass(hass)
        mock_api.async_validate = AsyncMock(side_effect=RuntimeError("boom"))

        result = await self._start_reauth(hass, config_entry)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["errors"] == {"base": "unknown"}


class TestOptionsFlow:
    """Polling options."""

    async def test_shows_current_values(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        result = await hass.config_entries.options.async_init(config_entry.entry_id)

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_saves_options(self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock) -> None:
        await setup_integration(hass, config_entry)

        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL_MINUTES: 90, CONF_INCLUDE_DONATION_HISTORY: False},
        )
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert config_entry.options[CONF_SCAN_INTERVAL_MINUTES] == 90
        assert config_entry.options[CONF_INCLUDE_DONATION_HISTORY] is False

    async def test_interval_is_stored_as_an_int(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """NumberSelector yields floats; a float would break the timedelta maths."""
        await setup_integration(hass, config_entry)

        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SCAN_INTERVAL_MINUTES: 45.0, CONF_INCLUDE_DONATION_HISTORY: True},
        )
        await hass.async_block_till_done()

        assert isinstance(config_entry.options[CONF_SCAN_INTERVAL_MINUTES], int)
