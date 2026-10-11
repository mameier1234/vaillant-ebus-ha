"""Gemeinsame Basis fuer alle Entitaeten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VaillantCoordinator


class VaillantEntity(CoordinatorEntity[VaillantCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)}, name="Vaillant Heizung", manufacturer="Vaillant",
            model="auroMATIC VRS 620",
        )

    @property
    def data_value(self):
        return self.coordinator.data.get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self.data_value is not None
