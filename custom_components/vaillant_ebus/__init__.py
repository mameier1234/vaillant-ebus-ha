"""Vaillant eBUS Control (auroMATIC VRS 620 ueber ebusd)."""

from __future__ import annotations

from dataclasses import dataclass

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import CONF_HOST, CONF_PERSONS, CONF_PORT, DOMAIN, SERVICE_SET_SCHEDULE
from .coordinator import VaillantCoordinator
from .ebusd import EbusdClient, EbusdError
from .presence import PresenceManager
from .shower import ShowerManager
from .spec import DAYS, TIMER_CIRCUITS

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.TEXT,
]

TIME_RE = vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$")
SLOT = vol.Schema({vol.Required("from"): TIME_RE, vol.Required("to"): TIME_RE})

DAY_CHOICES = {
    "weekdays": DAYS[:5],
    "weekend": DAYS[5:],
    **{d.lower(): (d,) for d in DAYS},
}

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("circuit"): vol.In(list(TIMER_CIRCUITS)),
        vol.Required("days"): vol.In(list(DAY_CHOICES)),
        vol.Required("slots"): vol.All(cv.ensure_list, [SLOT], vol.Length(max=3)),
    }
)


@dataclass
class VaillantData:
    coordinator: VaillantCoordinator
    shower: ShowerManager
    presence: PresenceManager


type VaillantConfigEntry = ConfigEntry[VaillantData]


async def async_setup_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    client = EbusdClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = VaillantCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    shower = ShowerManager(hass, coordinator)
    coordinator.shower = shower
    presence = PresenceManager(hass, coordinator, entry.options.get(CONF_PERSONS, []))
    await presence.async_load()
    entry.runtime_data = VaillantData(coordinator, shower, presence)
    entry.async_on_unload(entry.add_update_listener(_options_updated))

    async def set_schedule(call: ServiceCall) -> None:
        """Schreibt jeden betroffenen Tag einzeln (daysel=selected) und liest zur Kontrolle zurueck."""
        slots = [(s["from"], s["to"]) for s in call.data["slots"]]
        try:
            for day in DAY_CHOICES[call.data["days"]]:
                await coordinator.async_write_schedule(call.data["circuit"], day, slots)
        except (ValueError, EbusdError) as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, set_schedule, SET_SCHEDULE_SCHEMA)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await shower.async_load()  # nach den Plattformen: Parameter (number-Entitaeten) sind dann gesetzt
    presence.async_start()
    return True


async def _options_updated(hass: HomeAssistant, entry: VaillantConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    entry.runtime_data.presence.async_stop()
    hass.services.async_remove(DOMAIN, SERVICE_SET_SCHEDULE)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
