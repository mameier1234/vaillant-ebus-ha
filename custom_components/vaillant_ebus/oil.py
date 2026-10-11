"""Heizoelverbrauch aus der Brennerlaufzeit: Stunden x Durchsatz (L/h).

Der Durchsatz ist ein Schaetzwert (Duesengroesse/Kesselleistung) und per number-Entitaet einstellbar.
Die Verbrauchssensoren summieren *inkrementell* (Delta Stunden x aktueller Durchsatz), damit eine spaetere
Aenderung des Durchsatzes die Vergangenheit nicht umschreibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.restore_state import ExtraStoredData

from .coordinator import VaillantCoordinator
from .entity import VaillantEntity

DEFAULT_LPH = 2.5
MAX_DELTA_HOURS = 2000  # groessere Spruenge (Zaehler-Reset o. ae.) nicht als Verbrauch werten


@dataclass
class OilExtra(ExtraStoredData):
    total: float
    last_hours: float | None

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "last_hours": self.last_hours}


class NozzleFlowNumber(VaillantEntity, RestoreNumber):
    """Brenner-Durchsatz in L/h (Schaetzwert; bitte mit Duese/Kesselleistung abgleichen)."""

    _attr_icon = "mdi:oil"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0.3
    _attr_native_max_value = 15
    _attr_native_step = 0.05
    _attr_native_unit_of_measurement = "L/h"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "nozzle_flow", "Brenner Durchsatz (Schätzwert)")
        self._value = DEFAULT_LPH

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value:
            self._value = float(last.native_value)
        self.coordinator.nozzle_lph = self._value

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.coordinator.nozzle_lph = value
        self.async_write_ha_state()


class OilUsageSensor(VaillantEntity, RestoreSensor):
    """Summierter Heizoelverbrauch (L) aus Brennerstunden x Durchsatz."""

    _attr_icon = "mdi:oil"
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, key: str, name: str, hours_key: str) -> None:
        super().__init__(coordinator, entry_id, key, name)
        self._hours_key = hours_key
        self._total = 0.0
        self._last_hours: float | None = None

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if extra := await self.async_get_last_extra_data():
            d = extra.as_dict()
            self._total = float(d.get("total") or 0.0)
            self._last_hours = d.get("last_hours")

    @property
    def extra_restore_state_data(self) -> OilExtra:
        return OilExtra(self._total, self._last_hours)

    @property
    def native_value(self) -> float:
        return round(self._total, 2)

    @callback
    def _handle_coordinator_update(self) -> None:
        hours = self.coordinator.data.get(self._hours_key)
        if hours is not None:
            if self._last_hours is not None and 0 < hours - self._last_hours < MAX_DELTA_HOURS:
                self._total += (hours - self._last_hours) * self.coordinator.nozzle_lph
            self._last_hours = hours
        self.async_write_ha_state()
