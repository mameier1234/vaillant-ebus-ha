"""Zeitprogramm-Editor: Tagesauswahl (select) + Zeiten (text) je Kreis."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .coordinator import VaillantCoordinator
from .ebusd import EbusdError
from .entity import VaillantEntity
from .spec import DAY_OPTIONS, DAYS, TIMER_CIRCUITS, format_slots, parse_slots

DEFAULT_DAY = "Heute"


def resolve_days(selection: str) -> tuple[str, ...]:
    days = DAY_OPTIONS.get(selection, DAY_OPTIONS[DEFAULT_DAY])
    return days if days else (DAYS[dt_util.now().weekday()],)


class ScheduleDaySelect(VaillantEntity, SelectEntity, RestoreEntity):
    _attr_icon = "mdi:calendar-today"
    _attr_options = list(DAY_OPTIONS)

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, circuit: str, label: str) -> None:
        super().__init__(coordinator, entry_id, f"schedule_day_{circuit}", f"Zeitprogramm {label} Tag")
        self._circuit = circuit

    @property
    def available(self) -> bool:
        return True

    @property
    def current_option(self) -> str:
        return self.coordinator.edit_day.get(self._circuit, DEFAULT_DAY)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in DAY_OPTIONS:
            self.coordinator.edit_day[self._circuit] = last.state

    async def async_select_option(self, option: str) -> None:
        self.coordinator.edit_day[self._circuit] = option
        self.coordinator.async_update_listeners()  # Textfeld neu darstellen


class ScheduleText(VaillantEntity, TextEntity):
    """Zeiten des gewaehlten Tags; Eingabe schreibt (alle Tage der Auswahl) und liest zur Kontrolle zurueck."""

    _attr_icon = "mdi:calendar-edit"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 60

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, circuit: str, label: str) -> None:
        super().__init__(coordinator, entry_id, f"schedule_text_{circuit}", f"Zeitprogramm {label} Zeiten")
        self._circuit = circuit

    def _days(self) -> tuple[str, ...]:
        return resolve_days(self.coordinator.edit_day.get(self._circuit, DEFAULT_DAY))

    @property
    def _schedule(self) -> dict[str, list[tuple[str, str]]]:
        return self.coordinator.data.get("schedules", {}).get(self._circuit, {})

    @property
    def available(self) -> bool:
        return super(VaillantEntity, self).available and bool(self._schedule)

    @property
    def native_value(self) -> str | None:
        days = [d for d in self._days() if d in self._schedule]
        return format_slots(self._schedule[days[0]]) if days else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        days = self._days()
        texts = {d: format_slots(self._schedule.get(d, [])) for d in days}
        attrs: dict[str, Any] = {"tage": [d.lower() for d in days]}
        if len(set(texts.values())) > 1:  # Block mit unterschiedlichen Tagen
            attrs["abweichend"] = {d.lower(): t for d, t in texts.items()}
        return attrs

    async def async_set_value(self, value: str) -> None:
        try:
            slots = parse_slots(value)
            for day in self._days():
                await self.coordinator.async_write_schedule(self._circuit, day, slots)
        except (ValueError, EbusdError) as err:
            raise HomeAssistantError(str(err)) from err

