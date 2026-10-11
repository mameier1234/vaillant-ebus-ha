"""Betriebsarten als select-Entitaeten."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VaillantConfigEntry
from .api import VaillantCoordinator
from .const import DOMAIN, SEASON_CIRCUIT
from .ebusd import EbusdError


@dataclass(frozen=True)
class ModeDef:
    key: str  # Schluessel in coordinator.data
    name: str
    circuit: str
    message: str  # schreibbare ebusd-Nachricht
    options: dict[str, str]  # Anzeige-Option -> ebusd-Wert
    icon: str


MODES = (
    # 'on' bewusst nicht angeboten: hwc/cc SetMode=on hat auch andere Kreise auf Dauerbetrieb gesetzt
    # winter = Heizen (mc auto), summer = nur Warmwasser (mc off); Warmwasser bleibt unberuehrt
    ModeDef("season", "Betriebsart", SEASON_CIRCUIT, "SetMode",
            {"winter": "auto", "summer": "off"}, "mdi:sun-snowflake-variant"),
    ModeDef("hwc_mode", "Warmwasser Modus", "hwc", "SetMode",
            {"auto": "auto", "off": "off"}, "mdi:water-boiler"),
    ModeDef("circulation_mode", "Zirkulation Modus", "cc", "SetMode",
            {"auto": "auto", "off": "off"}, "mdi:pump"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(VaillantModeSelect(entry, coordinator, m) for m in MODES)


class VaillantModeSelect(CoordinatorEntity[VaillantCoordinator], SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: VaillantConfigEntry, coordinator: VaillantCoordinator, mode: ModeDef) -> None:
        super().__init__(coordinator)
        self._mode = mode
        self._from_value = {v: k for k, v in mode.options.items()}
        self._attr_name = mode.name
        self._attr_icon = mode.icon
        self._attr_unique_id = f"{entry.entry_id}_{mode.key}"
        self._attr_options = list(mode.options)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Vaillant Heizung", manufacturer="Vaillant"
        )

    @property
    def current_option(self) -> str | None:
        return self._from_value.get(self.coordinator.data.get(self._mode.key) or "")

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.client.write(
                self._mode.circuit, self._mode.message, self._mode.options[option]
            )
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
