"""Betriebsarten als select-Entitaeten."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .ebusd import EbusdError
from .entity import VaillantEntity
from .schedule_editor import ScheduleDaySelect
from .spec import TIMER_CIRCUITS


@dataclass(frozen=True)
class ModeDef:
    key: str
    name: str
    options: dict[str, str]  # Anzeige -> ebusd-Wert
    icon: str


# 'on' wird fuer hwc/mc bewusst nicht angeboten: hwc SetMode=on setzte auch andere Kreise auf Dauerbetrieb.
# cc SetMode=on wurde isoliert getestet (nur Zirkulation) und ist freigegeben.
MODES = (
    ModeDef("season", "Betriebsart Heizung", {"winter": "auto", "summer": "off"}, "mdi:sun-snowflake-variant"),
    ModeDef("hwc_mode", "Pufferladung Modus", {"auto": "auto", "off": "off"}, "mdi:water-boiler"),
    ModeDef("circulation_mode", "Zirkulation Modus", {"auto": "auto", "on": "on", "off": "off"}, "mdi:pump"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(VaillantModeSelect(coordinator, entry.entry_id, m) for m in MODES)
    async_add_entities(
        ScheduleDaySelect(coordinator, entry.entry_id, c, n) for c, n in TIMER_CIRCUITS.items()
    )


class VaillantModeSelect(VaillantEntity, SelectEntity):
    def __init__(self, coordinator, entry_id: str, mode: ModeDef) -> None:
        super().__init__(coordinator, entry_id, mode.key, mode.name)
        self._mode = mode
        self._from_value = {v: k for k, v in mode.options.items()}
        self._attr_icon = mode.icon
        self._attr_options = list(mode.options)

    @property
    def current_option(self) -> str | None:
        return self._from_value.get(self.value or "")

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_write(self._key, self._mode.options[option])
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err
