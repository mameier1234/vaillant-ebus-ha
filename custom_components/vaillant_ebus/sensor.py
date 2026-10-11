"""Sensoren: Temperaturen, Druck, Parameter (diagnostisch), Zeitprogramme, Ferien."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfPressure, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import VaillantConfigEntry
from .entity import VaillantEntity
from .oil import OilUsageSensor
from .spec import DAYS, TIMER_CIRCUITS

C = UnitOfTemperature.CELSIUS
T = SensorDeviceClass.TEMPERATURE


@dataclass(frozen=True)
class SensorDef:
    key: str
    name: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    precision: int | None = 1
    diagnostic: bool = False
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    options: list[str] | None = None


SENSORS = (
    SensorDef("outside_temp", "Außentemperatur", T, C),
    SensorDef("boiler_flow_temp", "Kessel Vorlauf", T, C),
    SensorDef("boiler_flow_desired", "Kessel Vorlauf Soll", T, C),
    SensorDef("mixer_flow_temp", "Heizkreis Vorlauf", T, C),
    SensorDef("mixer_flow_desired", "Heizkreis Vorlauf Soll", T, C, 0),
    SensorDef("system_flow_temp", "Sammler Vorlauf (VF1)", T, C),
    SensorDef("system_flow_desired", "Anlagensollwert", T, C, 0),
    SensorDef("room_temp", "Raumtemperatur Regler", T, C),
    SensorDef("buffer_top", "Puffer oben", T, C),
    SensorDef("buffer_lower_middle", "Puffer Mitte unten (Fühler 4)", T, C),
    SensorDef("buffer_bottom", "Puffer unten", T, C),
    SensorDef("water_pressure", "Wasserdruck Heizung", SensorDeviceClass.PRESSURE, UnitOfPressure.BAR, 2),
    SensorDef("mixer_state", "Mischer", SensorDeviceClass.ENUM, None, None, False, None, ["open", "close", "off"]),
    # Parameter des Reglers (nur lesen; schreibbare sind als number-Entitaeten angelegt)
    SensorDef("pump_idle", "Pumpensperrzeit", None, UnitOfTime.MINUTES, 0, True),
    SensorDef("flow_min", "Vorlauf Minimaltemperatur", T, C, 0, True),
    SensorDef("flow_max", "Vorlauf Maximaltemperatur", T, C, 0, True),
    SensorDef("preheat_max", "Max. Voraufheizung", None, UnitOfTime.HOURS, 0, True),
    SensorDef("pre_shutdown", "Max. Vorabschaltung", None, UnitOfTime.MINUTES, 0, True),
    SensorDef("frost_delay", "Frostschutzverzögerung", None, UnitOfTime.HOURS, 0, True),
    SensorDef("temp_increase", "Temperaturüberhöhung", None, "K", 1, True),
    SensorDef("boiler_temp_max", "Wärmeerzeuger Maximaltemperatur", T, C, 0, True),
    SensorDef("outside_correction", "Korrektur Außentemperatur", None, "K", 1, True),
    SensorDef("room_correction", "Korrektur Raumtemperatur", None, "K", 1, True),
    SensorDef("burner_hours", "Brennerlaufzeit Heizen", SensorDeviceClass.DURATION, UnitOfTime.HOURS, 0, False,
              SensorStateClass.TOTAL_INCREASING),
    SensorDef("burner_hours_hwc", "Brennerlaufzeit Warmwasser", SensorDeviceClass.DURATION, UnitOfTime.HOURS, 0,
              False, SensorStateClass.TOTAL_INCREASING),
    SensorDef("burner_starts_hc", "Brennerstarts Heizen", None, None, 0, False, SensorStateClass.TOTAL_INCREASING),
    SensorDef("burner_starts_hwc", "Brennerstarts Warmwasser", None, None, 0, False,
              SensorStateClass.TOTAL_INCREASING),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[SensorEntity] = [VaillantSensor(coordinator, entry.entry_id, d) for d in SENSORS]
    entities += [ScheduleSensor(coordinator, entry.entry_id, c, n) for c, n in TIMER_CIRCUITS.items()]
    entities.append(HolidaySensor(coordinator, entry.entry_id))
    entities += [
        OilUsageSensor(coordinator, entry.entry_id, "oil_used_hc", "Heizölverbrauch Heizen (Brenner)", "burner_hours"),
        OilUsageSensor(coordinator, entry.entry_id, "oil_used_hwc", "Heizölverbrauch Warmwasser (Brenner)", "burner_hours_hwc"),
    ]
    async_add_entities(entities)


class VaillantSensor(VaillantEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str, d: SensorDef) -> None:
        super().__init__(coordinator, entry_id, d.key, d.name)
        self._attr_device_class = d.device_class
        self._attr_native_unit_of_measurement = d.unit
        self._attr_state_class = d.state_class
        self._attr_suggested_display_precision = d.precision
        if d.options:
            self._attr_options = d.options
        if d.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self.data_value


def _fmt(slots: list[tuple[str, str]]) -> str:
    return ", ".join(f"{a}–{b}" for a, b in slots) if slots else "aus"


class ScheduleSensor(VaillantEntity, SensorEntity):
    """Zustand = Programm von heute; Attribute = alle 7 Tage."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, entry_id: str, circuit: str, label: str) -> None:
        super().__init__(coordinator, entry_id, f"schedule_{circuit}", f"Zeitprogramm {label}")
        self._circuit = circuit

    @property
    def _days(self) -> dict[str, list[tuple[str, str]]]:
        return self.coordinator.data.get("schedules", {}).get(self._circuit, {})

    @property
    def data_value(self):
        return self._days or None

    @property
    def native_value(self) -> str | None:
        today = DAYS[dt_util.now().weekday()]
        if today not in self._days:
            return None
        return _fmt(self._days[today])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {day.lower(): _fmt(slots) for day, slots in self._days.items()}


class HolidaySensor(VaillantEntity, SensorEntity):
    _attr_icon = "mdi:beach"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "holiday_period", "Ferienzeitraum")

    @staticmethod
    def _date(raw: str) -> str | None:
        try:
            return datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
        except ValueError:
            return None

    @property
    def native_value(self) -> str | None:
        v = self.data_value
        if not v or len(v) < 4:
            return None
        start, end = self._date(v[0]), self._date(v[2])
        return f"{v[0]} – {v[2]}" if start and end else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        v = self.data_value or []
        return {f"zeitraum_{i + 1}": f"{v[2 * i]} – {v[2 * i + 1]}" for i in range(len(v) // 2)} if len(v) >= 4 else {}
