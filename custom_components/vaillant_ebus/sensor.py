"""Temperatursensoren (aus ebusd gelesen)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VaillantConfigEntry
from .api import VaillantCoordinator
from .const import DOMAIN, TEMP_READS


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        VaillantTemperatureSensor(entry, coordinator, key, name) for key, (_, _, name) in TEMP_READS.items()
    )


class VaillantTemperatureSensor(CoordinatorEntity[VaillantCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, entry: VaillantConfigEntry, coordinator: VaillantCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Vaillant Heizung", manufacturer="Vaillant"
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get(self._key) is not None
