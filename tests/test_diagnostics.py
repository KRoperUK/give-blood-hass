"""Diagnostics tests.

Diagnostics get pasted into public GitHub issues, so these tests are less about
completeness than about proving that nothing identifying escapes. The strongest
check is :meth:`TestNoPiiEscapes.test_no_synthetic_pii_appears_anywhere`: it walks
the whole output looking for the synthetic values that stand in for real PII.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.nhs_give_blood.diagnostics import async_get_config_entry_diagnostics

from .conftest import build_snapshot, setup_integration
from .const import DONOR_ID, TEST_PASSWORD, TEST_USERNAME


class TestStructure:
    """The parts a maintainer actually needs."""

    async def test_reports_versions(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

        assert diagnostics["integration"]["domain"] == "nhs_give_blood"
        assert diagnostics["integration"]["version"]
        assert diagnostics["integration"]["library_version"]

    async def test_reports_credential_presence_not_values(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        entry_section = (await async_get_config_entry_diagnostics(hass, config_entry))["entry"]

        assert entry_section["has_username"] is True
        assert entry_section["has_password"] is True
        assert entry_section["has_stored_tokens"] is True
        assert "username" not in entry_section
        assert "password" not in entry_section
        assert "tokens" not in entry_section

    async def test_account_is_fingerprinted_not_named(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """A hash lets two reports be correlated without publishing the id."""
        await setup_integration(hass, config_entry)
        fingerprint = (await async_get_config_entry_diagnostics(hass, config_entry))["entry"]["account_fingerprint"]

        assert fingerprint is not None
        assert fingerprint != DONOR_ID
        assert len(fingerprint) == 12

    async def test_reports_coordinator_health(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        coordinator = (await async_get_config_entry_diagnostics(hass, config_entry))["coordinator"]

        assert coordinator["last_update_success"] is True
        assert coordinator["update_interval_seconds"] == 1800
        assert coordinator["has_data"] is True

    async def test_summarises_the_snapshot(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        snapshot = (await async_get_config_entry_diagnostics(hass, config_entry))["snapshot"]

        assert snapshot["account"]["blood_group"] == "A-"
        assert snapshot["account"]["donation_credit"] == 15
        assert snapshot["appointments"]["upcoming_count"] == 2
        assert snapshot["awards"]["award_state"] == "Bronze"
        assert snapshot["donations"]["truncated_by_api"] is True

    async def test_counts_contact_details_without_listing_them(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """The count is the diagnostic signal; the values never are."""
        await setup_integration(hass, config_entry)
        account = (await async_get_config_entry_diagnostics(hass, config_entry))["snapshot"]["account"]

        assert account["address_count"] == 1
        assert account["telephone_count"] == 1
        assert account["email_count"] == 1

    async def test_names_unmodelled_api_fields(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """When NHSBT adds a field, the key names are the useful signal."""
        await setup_integration(hass, config_entry)
        account = (await async_get_config_entry_diagnostics(hass, config_entry))["snapshot"]["account"]

        assert isinstance(account["unmodelled_fields"], list)

    async def test_reports_degraded_endpoints(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        mock_api.async_get_snapshot = AsyncMock(return_value=build_snapshot(degraded=("messages",)))
        await setup_integration(hass, config_entry)
        snapshot = (await async_get_config_entry_diagnostics(hass, config_entry))["snapshot"]

        assert snapshot["degraded_endpoints"] == ["messages"]

    async def test_handles_no_data_yet(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        await setup_integration(hass, config_entry)
        config_entry.runtime_data.coordinator.data = None

        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
        assert diagnostics["snapshot"] is None

    async def test_output_is_json_serialisable(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Home Assistant serialises this for download; an unserialisable value 500s."""
        await setup_integration(hass, config_entry)
        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

        json.dumps(diagnostics)


class TestNoPiiEscapes:
    """The reason this module uses an allowlist rather than a redaction list."""

    @staticmethod
    def _values(node: Any) -> list[str]:
        """Every string value in the output, at any depth."""
        found: list[str] = []
        if isinstance(node, dict):
            for value in node.values():
                found.extend(TestNoPiiEscapes._values(value))
        elif isinstance(node, list):
            for item in node:
                found.extend(TestNoPiiEscapes._values(item))
        elif isinstance(node, str):
            found.append(node)
        return found

    async def test_no_synthetic_pii_appears_anywhere(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Each value below stands in for real PII in the same field."""
        await setup_integration(hass, config_entry)
        blob = json.dumps(await async_get_config_entry_diagnostics(hass, config_entry))

        forbidden = {
            TEST_USERNAME,  # email address
            TEST_PASSWORD,  # password
            DONOR_ID,  # donor identifier
            "Testerson",  # surname
            "Ada",  # forename
            "ZZ99 3WZ",  # postcode
            "07700900000",  # phone number
            "1990-01-01",  # date of birth
            "G000000000000X",  # donation id
            "synthetic.access.token",  # access token
            "synthetic-refresh-token",  # refresh token
            "Testville",  # venue town, which locates the donor
            "1 Example Street",  # street address
        }
        leaked = {value for value in forbidden if value in blob}
        assert not leaked, f"diagnostics leaked: {sorted(leaked)}"

    async def test_no_value_looks_like_an_email_or_postcode(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Catches a *newly added* identifying field, not just the known ones."""
        import re

        await setup_integration(hass, config_entry)
        diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)

        email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
        postcode = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b")

        for value in self._values(diagnostics):
            assert not email.search(value), f"email-shaped value in diagnostics: {value}"
            assert not postcode.search(value), f"postcode-shaped value in diagnostics: {value}"

    async def test_venue_identity_is_reduced_to_capabilities(
        self, hass: HomeAssistant, config_entry: MockConfigEntry, mock_api: AsyncMock
    ) -> None:
        """Venue name plus appointment dates is enough to place a person."""
        await setup_integration(hass, config_entry)
        appointment = (await async_get_config_entry_diagnostics(hass, config_entry))["snapshot"]["appointments"][
            "items"
        ][0]

        assert appointment["venue_present"] is True
        assert "venue_name" not in appointment
        assert "venue_id" not in appointment
        assert set(appointment["venue_supports"]) == {"whole_blood", "plasma", "platelet"}


class TestDownload:
    """The full HTTP path Home Assistant actually uses."""

    async def test_diagnostics_download_succeeds(
        self,
        hass: HomeAssistant,
        hass_client: ClientSessionGenerator,
        config_entry: MockConfigEntry,
        mock_api: AsyncMock,
    ) -> None:
        from pytest_homeassistant_custom_component.components.diagnostics import (
            get_diagnostics_for_config_entry,
        )

        await setup_integration(hass, config_entry)
        result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

        assert result["integration"]["domain"] == "nhs_give_blood"
