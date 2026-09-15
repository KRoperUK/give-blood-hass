"""Adapter between the ``nhs_give_blood`` library and Home Assistant.

The rest of the integration imports nothing from the library directly. Keeping
the boundary here means:

* the library's exception vocabulary is translated once, into the two errors
  Home Assistant config flows and coordinators actually branch on;
* ``manifest.json`` can pin a *floor* rather than an exact version, with any
  version-compatibility shims confined to this file.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from nhs_give_blood import (
    DonorSnapshot,
    GiveBloodApiError,
    GiveBloodAuthError,
    GiveBloodClient,
    GiveBloodConnectionError,
    GiveBloodError,
    GiveBloodRateLimitError,
    TokenBundle,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """The API could not be reached, or failed transiently.

    Retry later. Never surface this as a credential problem.
    """


class InvalidAuth(Exception):
    """Credentials or tokens are no longer usable and a human must intervene."""


@contextmanager
def translated_errors() -> Iterator[None]:
    """Map library exceptions onto the integration's two error types.

    The split follows the library's own classification rather than the exception
    class: a 5xx from the auth service is ``transient`` and must not trigger a
    reauth flow, even though it arrives as a ``GiveBloodAuthError``. Getting this
    backwards produces either spurious "reconfigure me" prompts during an NHSBT
    outage, or a silently stalled integration when a password really has changed.
    """
    try:
        yield
    except GiveBloodAuthError as err:
        if err.transient:
            raise CannotConnect(str(err)) from err
        raise InvalidAuth(str(err)) from err
    except (GiveBloodConnectionError, GiveBloodRateLimitError) as err:
        raise CannotConnect(str(err)) from err
    except GiveBloodApiError as err:
        raise CannotConnect(str(err)) from err
    except GiveBloodError as err:
        # Anything new the library grows: treat as transient rather than
        # forcing a reauth the user can't act on.
        raise CannotConnect(str(err)) from err


class GiveBloodApiClient:
    """Thin, HA-flavoured wrapper around :class:`GiveBloodClient`."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        username: str | None = None,
        password: str | None = None,
        tokens: dict[str, Any] | None = None,
    ) -> None:
        """Build a client on Home Assistant's shared aiohttp session."""
        self._hass = hass
        # Caller-owned session: HA manages its lifetime, so the library must not
        # close it. Never use async_create_clientsession here outside a flow.
        self._client = GiveBloodClient(
            async_get_clientsession(hass),
            username=username,
            password=password,
            token_bundle=TokenBundle.from_mapping(tokens),
        )

    @property
    def token_data(self) -> dict[str, Any]:
        """Current tokens, for persistence into the config entry."""
        return self._client.export_tokens().as_dict()

    @property
    def donor_id(self) -> str | None:
        """Donor identifier, read from the access token's claims.

        Available without an extra API call, which is what makes it usable as the
        config entry's unique id.
        """
        return self._client.donor_id

    async def async_validate(self) -> str | None:
        """Authenticate and return the donor id. Used by the config flow.

        Raises:
            InvalidAuth: credentials rejected.
            CannotConnect: transient failure.
        """
        with translated_errors():
            await self._client.async_ensure_authenticated()
            return self._client.donor_id

    async def async_get_snapshot(self, *, include_donations: bool = True) -> DonorSnapshot:
        """Fetch everything the entities need in one pass.

        Raises:
            InvalidAuth: re-authentication required.
            CannotConnect: transient failure.
        """
        with translated_errors():
            return await self._client.async_get_snapshot(include_donations=include_donations)

    async def async_logout(self) -> None:
        """Invalidate the refresh token server-side. Best effort."""
        try:
            with translated_errors():
                await self._client.async_logout()
        except (CannotConnect, InvalidAuth) as err:
            # Unloading an entry must not fail because sign-out didn't land.
            _LOGGER.debug("Sign-out on unload failed, continuing: %s", err)
