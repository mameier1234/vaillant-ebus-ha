"""Binaere Zustaende: Brenner, Pumpen, Party, Ferien, Parallele Ladung."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .entity import VaillantEntity
from .mixer import MixerStuckBinary

ON_VALUES = {"on", "yes", "1"}


@dataclass(frozen=True)
class BinaryDef:
    key: str
    name: str
    device_class: BinarySensorDeviceClass | None = None
    diagnostic: bool = False


BINARIES = (
    BinaryDef("flame", "Brenner", BinarySensorDeviceClass.RUNNING),
    BinaryDef("heating_pump", "Heizkreispumpe", BinarySensorDeviceClass.RUNNING),
    BinaryDef("charge_pump", "Ladepumpe Puffer", BinarySensorDeviceClass.RUNNING),
    BinaryDef("circulation_pump", "Zirkulationspumpe", BinarySensorDeviceClass.RUNNING),
    BinaryDef("holiday_active", "Ferienprogramm aktiv"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([VaillantBinary(coordinator, entry.entry_id, d) for d in BINARIES]
                       + [MixerStuckBinary(coordinator, entry.entry_id)])


class VaillantBinary(VaillantEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry_id: str, d: BinaryDef) -> None:
        super().__init__(coordinator, entry_id, d.key, d.name)
        self._attr_device_class = d.device_class
        if d.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        v = self.data_value
        return None if v is None else str(v).lower() in ON_VALUES
