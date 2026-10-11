"""Brennerlaufzeit (sekundengenau gezaehlt) und Heizoelverbrauch = Laufzeit x Durchsatz (L/h).

Die Brennerlaufzeit wird aus dem Flammenzustand (alle 15 s gelesen) aufsummiert und nach Heizen und
Warmwasser-Ladung getrennt: Brenner an + Ladepumpe an = Warmwasser/Puffer, Brenner an + Ladepumpe aus = Heizen.
Der Stundenzaehler des Kessels hat nur ganze Stunden (zu grob fuer Tageswerte) und bleibt als eigener Sensor erhalten.

Der Durchsatz ist ein Schaetzwert (Duesengroesse/Kesselleistung) und per number-Entitaet einstellbar.
Die Verbrauchssensoren summieren *inkrementell* (Delta Zeit x aktueller Durchsatz), damit eine spaetere
Aenderung des Durchsatzes die Vergangenheit nicht umschreibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberMode, RestoreNumber
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.restore_state import ExtraStoredData

from .coordinator import VaillantCoordinator
from .entity import VaillantEntity

DEFAULT_LPH = 2.5
MAX_GAP_SECONDS = 120  # laengere Luecken (HA aus, ebusd nicht erreichbar) nicht als Brennerlauf werten


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


class FlameIntegrator:
    """Zaehlt Sekunden mit laufendem Brenner (Sample-and-hold) fuer eine Kategorie: 'hc' (Heizen) oder 'hwc' (Ladung)."""

    def __init__(self, category: str) -> None:
        self._cat = category
        self._last: datetime | None = None
        self._prev_on = False

    def delta_seconds(self, data: dict[str, Any], now: datetime) -> float:
        d = 0.0
        if self._last is not None and self._prev_on:
            dt = (now - self._last).total_seconds()
            if 0 < dt <= MAX_GAP_SECONDS:
                d = dt
        flame = str(data.get("flame")).lower() == "on"
        pump = str(data.get("charge_pump")).lower() == "on"
        self._prev_on = flame and (pump if self._cat == "hwc" else not pump)
        self._last = now
        return d


class BurnerRuntimeSensor(VaillantEntity, RestoreSensor):
    """Brennerlaufzeit in Stunden (3 Nachkommastellen), getrennt nach Heizen / Warmwasser-Ladung."""

    _attr_icon = "mdi:fire-circle"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "h"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, key: str, name: str, category: str) -> None:
        super().__init__(coordinator, entry_id, key, name)
        self._integ = FlameIntegrator(category)
        self._seconds = 0.0

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if extra := await self.async_get_last_extra_data():
            self._seconds = float(extra.as_dict().get("seconds") or 0.0)

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return SecondsExtra(self._seconds)

    @property
    def native_value(self) -> float:
        return round(self._seconds / 3600, 4)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._seconds += self._integ.delta_seconds(self.coordinator.data, dt_util.utcnow())
        self.async_write_ha_state()


@dataclass
class SecondsExtra(ExtraStoredData):
    seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {"seconds": self.seconds}


class OilUsageSensor(VaillantEntity, RestoreSensor):
    """Summierter Heizoelverbrauch (L) aus sekundengenauer Brennerlaufzeit x Durchsatz."""

    _attr_icon = "mdi:oil"
    _attr_device_class = SensorDeviceClass.VOLUME
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, key: str, name: str, category: str) -> None:
        super().__init__(coordinator, entry_id, key, name)
        self._integ = FlameIntegrator(category)
        self._total = 0.0

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if extra := await self.async_get_last_extra_data():
            self._total = float(extra.as_dict().get("total") or 0.0)

    @property
    def extra_restore_state_data(self) -> OilExtra:
        return OilExtra(self._total, None)

    @property
    def native_value(self) -> float:
        return round(self._total, 3)

    @callback
    def _handle_coordinator_update(self) -> None:
        secs = self._integ.delta_seconds(self.coordinator.data, dt_util.utcnow())
        self._total += secs / 3600 * self.coordinator.nozzle_lph
        self.async_write_ha_state()
