"""Schreibbare Sollwerte (Benutzerebene des Reglers)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .ebusd import EbusdError
from .entity import VaillantEntity


@dataclass(frozen=True)
class NumberDef:
    key: str
    name: str
    min: float
    max: float
    step: float
    decimals: int  # Format fuer ebusd
    unit: str | None = UnitOfTemperature.CELSIUS
    icon: str | None = None


NUMBERS = (
    NumberDef("room_target", "Raumsoll Tag", 10, 30, 1, 0),
    NumberDef("room_night", "Absenktemperatur", 10, 30, 1, 0),
    NumberDef("heating_curve", "Heizkurve", 0.2, 4.0, 0.05, 2, None, "mdi:chart-bell-curve-cumulative"),
    NumberDef("ot_limit", "AT-Abschaltgrenze", 10, 35, 1, 0),
    NumberDef("buffer_target", "Puffer Solltemperatur", 40, 65, 1, 0),
    NumberDef("holiday_temp", "Raumsoll Ferien", 5, 25, 0.5, 1),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(VaillantNumber(coordinator, entry.entry_id, d) for d in NUMBERS)


class VaillantNumber(VaillantEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry_id: str, d: NumberDef) -> None:
        super().__init__(coordinator, entry_id, d.key, d.name)
        self._d = d
        self._attr_native_min_value = d.min
        self._attr_native_max_value = d.max
        self._attr_native_step = d.step
        self._attr_native_unit_of_measurement = d.unit
        self._attr_icon = d.icon
        if d.unit == UnitOfTemperature.CELSIUS:
            self._attr_device_class = NumberDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> float | None:
        return self.value

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.async_write(self._key, f"{value:.{self._d.decimals}f}")
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err
