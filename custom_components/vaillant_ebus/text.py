"""Text-Entitaeten: Zeitprogramm-Zeiten je Kreis."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VaillantConfigEntry
from .schedule_editor import ScheduleText
from .spec import TIMER_CIRCUITS


async def async_setup_entry(
    hass: HomeAssistant, entry: VaillantConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(ScheduleText(coordinator, entry.entry_id, c, n) for c, n in TIMER_CIRCUITS.items())
