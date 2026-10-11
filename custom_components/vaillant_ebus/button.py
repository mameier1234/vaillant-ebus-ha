"""Button: einmalige Pufferladung (Quick - WW Speicherladung). UNGETESTET, standardmaessig deaktiviert."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .ebusd import EbusdError
from .entity import VaillantEntity
from .spec import QUICK_LOAD


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([QuickLoadButton(entry.runtime_data.coordinator, entry.entry_id)])


class QuickLoadButton(VaillantEntity, ButtonEntity):
    _attr_icon = "mdi:water-boiler-auto"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "quick_load", "Puffer einmalig laden")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.write(*QUICK_LOAD, "1")
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err
