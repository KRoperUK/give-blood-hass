"""Base entity for the NHS Give Blood integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from nhs_give_blood import AccountDetails, DonorSnapshot

from .const import DOMAIN, MANUFACTURER, NAME, VERSION
from .coordinator import GiveBloodConfigEntry, GiveBloodCoordinator


class GiveBloodEntity(CoordinatorEntity[GiveBloodCoordinator]):
    """Shared behaviour for every entity in this integration.

    One config entry represents one donor account and produces exactly one
    device, so there is no device hierarchy and no ``via_device`` to resolve.

    Unique ids are ``{donor_id}_{key}``, not ``{entry_id}_{key}``: the donor id is
    stable across removing and re-adding the integration, so entity history and
    customisations survive it.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: GiveBloodCoordinator, entry: GiveBloodConfigEntry, key: str) -> None:
        """Attach to the coordinator and derive identity."""
        super().__init__(coordinator)
        self._entry = entry
        # Falls back to the entry id if the token carried no donor claim, so a
        # unique id always exists.
        self._account_key = coordinator.api.donor_id or entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{self._account_key}_{key}"

    @property
    def snapshot(self) -> DonorSnapshot | None:
        """The latest snapshot, or ``None`` before the first successful poll."""
        return self.coordinator.data

    @property
    def account(self) -> AccountDetails | None:
        """The donor account payload from the latest snapshot."""
        return self.coordinator.data.account if self.coordinator.data else None

    @property
    def available(self) -> bool:
        """Available when the last poll succeeded and produced an account.

        Both halves are needed: the coordinator can report success while the
        snapshot is degraded, but a snapshot without an account payload means
        there is nothing to render.
        """
        return super().available and self.account is not None

    @property
    def device_info(self) -> DeviceInfo:
        """One device per donor account.

        Deliberately does not include the donor's name: device names appear in
        logs, diagnostics and screenshots, and "NHS Give Blood" plus the account
        suffix is enough to tell two accounts apart without publishing a person's
        identity.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, self._account_key)},
            name=NAME,
            manufacturer=MANUFACTURER,
            model="Donor account",
            sw_version=VERSION,
            configuration_url="https://my.blood.co.uk/your-account",
        )
