"""Schnellfunktionen des Reglers: Party und einmalige Pufferladung (UNGETESTET, standardmaessig deaktiviert)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .ebusd import EbusdError
from .entity import VaillantEntity
from .spec import QUICK_PARTY


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([PartySwitch(coordinator, entry.entry_id)])


class PartySwitch(VaillantEntity, SwitchEntity):
    """mc party: 'Quick - Party' des Reglers."""

    _attr_icon = "mdi:party-popper"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "party_active", "Party")

    @property
    def is_on(self) -> bool | None:
        v = self.value
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
