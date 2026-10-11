"""Schnellfunktionen des Reglers: Party und einmalige Pufferladung (UNGETESTET, standardmaessig deaktiviert)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .ebusd import EbusdError
from .entity import VaillantEntity
from .shower import ShowerSwitch
from .spec import QUICK_PARTY


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([
        PartySwitch(coordinator, entry.entry_id),
        ParallelChargingSwitch(coordinator, entry.entry_id),
        ShowerSwitch(coordinator, entry.entry_id, entry.runtime_data.shower),
    ])


class PartySwitch(VaillantEntity, SwitchEntity):
    """mc party: 'Quick - Party' des Reglers."""

    _attr_icon = "mdi:party-popper"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "party_active", "Party")

    @property
    def is_on(self) -> bool | None:
        v = self.data_value
        return None if v is None else str(v) == "1"

    async def _set(self, on: bool) -> None:
        try:
            await self.coordinator.client.write(*QUICK_PARTY, "1" if on else "0")
            await self.coordinator.async_refresh_after_write("party_active")
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class ParallelChargingSwitch(VaillantEntity, SwitchEntity):
    """Parallele Ladung (hwc): AN = Heizung laeuft waehrend der Pufferladung weiter, AUS = Pufferladung hat Vorrang."""

    _attr_icon = "mdi:source-branch"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "parallel_charging", "Parallele Ladung")

    @property
    def is_on(self) -> bool | None:
        v = self.data_value
        return None if v is None else str(v).lower() in ("yes", "on", "1")

    async def _set(self, on: bool) -> None:
        try:
            await self.coordinator.async_write("parallel_charging", "yes" if on else "no")
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
