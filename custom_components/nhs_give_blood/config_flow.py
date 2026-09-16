"""Config and options flows for the NHS Give Blood integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CannotConnect, GiveBloodApiClient, InvalidAuth
from .const import (
    CONF_INCLUDE_DONATION_HISTORY,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_TOKENS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
    NAME,
)
from .coordinator import GiveBloodConfigEntry

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def _validate(hass: HomeAssistant, username: str, password: str) -> tuple[str | None, dict[str, Any]]:
    """Authenticate and return ``(donor_id, tokens)``.

    Raises:
        InvalidAuth: credentials rejected.
        CannotConnect: transient failure.
    """
    client = GiveBloodApiClient(hass, username=username, password=password)
    donor_id = await client.async_validate()
    return donor_id, client.token_data


def _belongs_to_another_donor(entry: GiveBloodConfigEntry, donor_id: str | None) -> bool:
    """Whether freshly validated credentials are for a different donor account.

    Shared by the reauth and reconfigure paths on purpose. Both rewrite the
    entry's stored credentials, and letting either re-point an existing entry at
    another account would keep every entity id and all of its recorded history
    while silently changing whose data they describe. Nothing would appear to
    break, which is what makes it worth one implementation rather than two that
    can drift apart.
    """
    return bool(donor_id and entry.unique_id and donor_id != entry.unique_id)


class GiveBloodConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and re-authentication for a donor account."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect credentials and verify them against the API."""
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                donor_id, tokens = await _validate(self.hass, username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - a flow must never show a traceback
                _LOGGER.exception("Unexpected error validating NHS Give Blood credentials")
                errors["base"] = "unknown"
            else:
                # Donor id keyed rather than email: the same account reached with
                # a changed email address must still be recognised as a duplicate.
                if donor_id:
                    await self.async_set_unique_id(donor_id)
                    self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=NAME,
                    data={
                        CONF_USERNAME: username,
                        # Stored so the integration can recover unattended when a
                        # refresh token is rejected — NHSBT rotates them, and
                        # without the password a rotation means a manual reauth.
                        CONF_PASSWORD: password,
                        CONF_TOKENS: tokens,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=CREDENTIALS_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the coordinator raised auth failure."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Collect fresh credentials for an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                donor_id, tokens = await _validate(self.hass, username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error re-validating NHS Give Blood credentials")
                errors["base"] = "unknown"
            else:
                # Guard against re-authenticating an entry against a *different*
                # donor account, which would silently rewrite every entity's
                # meaning while keeping their ids.
                if _belongs_to_another_donor(entry, donor_id):
                    return self.async_abort(reason="wrong_account")

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_TOKENS: tokens,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA,
                {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the credentials on an existing entry, deliberately.

        The reauth flow does the same work, but it only opens reactively when the
        coordinator raises ``ConfigEntryAuthFailed``. There is otherwise no way to
        get to it: change the password in the app and the integration keeps going
        on its stored refresh token until NHSBT next rejects one. This is the
        deliberate path, offered as **Reconfigure** in the entry's overflow menu.

        Rejecting credentials for a different donor matters more here than
        anywhere: reconfigure exists to change credentials, so it is the flow
        someone reaches for when they have *another* account's details to hand.
        """
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                donor_id, tokens = await _validate(self.hass, username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - a flow must never show a traceback
                _LOGGER.exception("Unexpected error reconfiguring NHS Give Blood credentials")
                errors["base"] = "unknown"
            else:
                if _belongs_to_another_donor(entry, donor_id):
                    return self.async_abort(reason="wrong_account")

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_TOKENS: tokens,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA,
                {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: GiveBloodConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return GiveBloodOptionsFlow()


class GiveBloodOptionsFlow(OptionsFlow):
    """Polling and payload options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_MINUTES: int(user_input[CONF_SCAN_INTERVAL_MINUTES]),
                    CONF_INCLUDE_DONATION_HISTORY: user_input[CONF_INCLUDE_DONATION_HISTORY],
                }
            )

        options = self.config_entry.options
        current_interval = options.get(
            CONF_SCAN_INTERVAL_MINUTES,
            int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60),
        )

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL_MINUTES, default=current_interval): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MINUTES,
                        max=MAX_SCAN_INTERVAL_MINUTES,
                        step=5,
                        unit_of_measurement="minutes",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_INCLUDE_DONATION_HISTORY,
                    default=options.get(CONF_INCLUDE_DONATION_HISTORY, True),
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
