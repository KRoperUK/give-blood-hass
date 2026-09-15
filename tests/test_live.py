"""Live smoke test against a real NHS Give Blood account.

Deselected by default: it needs credentials and hits the real API. Run it with

    pytest -m live

after putting ``NHS_GIVE_BLOOD_EMAIL`` and ``NHS_GIVE_BLOOD_PASSWORD`` in a
``.env`` (searched upward from this repo) or the environment.

Read-only, and it deliberately asserts on *shapes and invariants* rather than on
values: a donor's real credits and appointment dates change, and hard-coding them
would both break constantly and risk committing personal data.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nhs_give_blood.const import DOMAIN

pytestmark = pytest.mark.live


def _credentials() -> tuple[str, str] | None:
    """Load credentials from the environment or a .env above this repo."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    email = os.environ.get("NHS_GIVE_BLOOD_EMAIL")
    password = os.environ.get("NHS_GIVE_BLOOD_PASSWORD")
    return (email, password) if email and password else None


@pytest.fixture
def unblock_network() -> Iterator[None]:
    """Undo the test harness's network block for the duration of a test.

    pytest-homeassistant-custom-component installs pytest-socket restrictions in an
    autouse fixture, so the ``socket_enabled`` fixture alone is not enough — the
    per-host ``connect`` guard has to be lifted too. Restored afterwards so no
    other test can reach the network by accident.
    """
    import socket

    import pytest_socket

    original_connect = socket.socket.connect
    pytest_socket.enable_socket()
    socket.socket.connect = pytest_socket._true_connect  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]


@pytest.fixture
async def real_session(unblock_network: None) -> AsyncIterator[None]:
    """Give the integration a working aiohttp session for the duration of a test.

    Home Assistant's shared session is built with an ``AsyncResolver`` that the test
    harness leaves uninitialised, so DNS fails even with sockets unblocked.
    Substituting a plain session is the smallest change that makes a live run
    possible; everything else — config entry, adapter, coordinator, entities,
    diagnostics — is the real code path.
    """
    async with aiohttp.ClientSession() as session:
        with patch(
            "custom_components.nhs_give_blood.api.async_get_clientsession",
            return_value=session,
        ):
            yield


@pytest.fixture
def live_entry(real_session: None) -> MockConfigEntry:
    """A config entry holding real credentials.

    ``socket_enabled`` lifts pytest-homeassistant-custom-component's network
    block, which nulls aiohttp's DNS resolver by default. Requesting it here rather
    than autouse keeps every other test hermetic.
    """
    credentials = _credentials()
    if credentials is None:
        pytest.skip("no NHS_GIVE_BLOOD_EMAIL / NHS_GIVE_BLOOD_PASSWORD available")
    email, password = credentials
    return MockConfigEntry(
        domain=DOMAIN,
        title="NHS Give Blood",
        data={CONF_USERNAME: email, CONF_PASSWORD: password},
    )


async def test_integration_loads_against_the_real_api(hass: HomeAssistant, live_entry: MockConfigEntry) -> None:
    """The whole stack: config entry → adapter → library → live API → entities."""
    from homeassistant.config_entries import ConfigEntryState

    live_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()

    assert live_entry.state is ConfigEntryState.LOADED

    snapshot = live_entry.runtime_data.coordinator.data
    assert snapshot is not None
    assert snapshot.account.donor_id, "the account payload should identify the donor"
    assert snapshot.account.blood_group, "every registered donor has a blood group"

    # Entities exist and are not stuck unavailable.
    for entity_id in ("sensor.nhs_give_blood_blood_group", "sensor.nhs_give_blood_donation_credits"):
        state = hass.states.get(entity_id)
        assert state is not None, f"{entity_id} was not created"
        assert state.state not in ("unavailable",), f"{entity_id} is unavailable"


async def test_tokens_are_persisted_for_restart_survival(hass: HomeAssistant, live_entry: MockConfigEntry) -> None:
    """Without this, every restart would need a fresh password login."""
    from custom_components.nhs_give_blood.const import CONF_TOKENS

    live_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()

    tokens = live_entry.data.get(CONF_TOKENS)
    assert tokens, "the coordinator should have written tokens back to the entry"
    assert tokens["access_token"] and tokens["refresh_token"]


async def test_diagnostics_leak_nothing_identifying(hass: HomeAssistant, live_entry: MockConfigEntry) -> None:
    """The strongest version of this check: real PII, real diagnostics output."""
    import json
    import re

    from custom_components.nhs_give_blood.diagnostics import async_get_config_entry_diagnostics

    live_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()

    snapshot = live_entry.runtime_data.coordinator.data
    assert snapshot is not None
    account = snapshot.account

    blob = json.dumps(await async_get_config_entry_diagnostics(hass, live_entry))

    # Values pulled from the live payload, so this fails on any real leak rather
    # than only the ones a fixture happens to contain.
    forbidden = {
        account.donor_id,
        account.surname,
        account.forenames.first_forename if account.forenames else None,
        live_entry.data[CONF_USERNAME],
        live_entry.data[CONF_PASSWORD],
        account.home_address.postcode if account.home_address else None,
    }
    forbidden |= {telephone.number for telephone in account.telephones}
    forbidden |= {email.address for email in account.emails}
    forbidden |= {appointment.venue.venue_name for appointment in snapshot.upcoming_appointments if appointment.venue}
    leaked = {value for value in forbidden if value and value in blob}
    assert not leaked, f"diagnostics leaked {len(leaked)} real value(s)"

    # And nothing merely *shaped* like contact detail, which catches new fields.
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", blob), "email-shaped value in diagnostics"
    assert not re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", blob), "postcode-shaped value"


async def test_entity_states_expose_no_contact_details(hass: HomeAssistant, live_entry: MockConfigEntry) -> None:
    """States and attributes are visible to every dashboard and voice assistant."""
    live_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()

    account = live_entry.runtime_data.coordinator.data.account
    forbidden = {value for value in (account.surname, account.donor_id) if value}
    forbidden |= {telephone.number for telephone in account.telephones if telephone.number}
    forbidden |= {email.address for email in account.emails if email.address}

    offenders: list[str] = []
    for entity_id in hass.states.async_entity_ids():
        if DOMAIN not in entity_id:
            continue
        blob = f"{hass.states.get(entity_id).state} {hass.states.get(entity_id).attributes}"
        offenders.extend(entity_id for value in forbidden if value in blob)

    assert not offenders, f"entities exposing donor contact detail: {sorted(set(offenders))}"


async def test_attributes_fit_the_recorder_budget_with_real_data(
    hass: HomeAssistant, live_entry: MockConfigEntry
) -> None:
    """Synthetic fixtures are small; a real account is the honest test."""
    import json

    live_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(live_entry.entry_id)
    await hass.async_block_till_done()

    for entity_id in hass.states.async_entity_ids():
        if DOMAIN not in entity_id:
            continue
        state = hass.states.get(entity_id)
        size = len(json.dumps(dict(state.attributes), default=str).encode())
        assert size < 16384, f"{entity_id} attributes are {size} bytes"
        assert len(state.state) <= 255, f"{entity_id} state exceeds 255 characters"
