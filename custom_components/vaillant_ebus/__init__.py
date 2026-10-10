"""Vaillant eBUS Control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .api import OverrideManager, VaillantCoordinator, format_schedule
from .const import (
    BLOCK_DAY,
    CIRCUITS_WITH_TIMER,
    CONF_HOST,
    CONF_PORT,
    DOMAIN,
    SERVICE_CANCEL_OVERRIDE,
    SERVICE_HOT_WATER_OVERRIDE,
    SERVICE_SET_SCHEDULE,
)
from .ebusd import EbusdClient, EbusdError

PLATFORMS = [Platform.SELECT]

TIME_RE = vol.Match(r"^([01]\d|2[0-3]):[0-5]\d$")
SLOT = vol.Schema({vol.Required("from"): TIME_RE, vol.Required("to"): TIME_RE})

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("circuit"): vol.In(CIRCUITS_WITH_TIMER),
        vol.Required("days"): vol.In(list(BLOCK_DAY)),
        vol.Required("slots"): vol.All(cv.ensure_list, [SLOT], vol.Length(max=3)),
    }
)
OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional("hours"): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=168)),
        vol.Optional("until"): cv.datetime,
    }
)


@dataclass
class VaillantData:
    coordinator: VaillantCoordinator
    override: OverrideManager


type VaillantConfigEntry = ConfigEntry[VaillantData]


async def async_setup_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    client = EbusdClient(entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = VaillantCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    override = OverrideManager(hass, coordinator)
    await override.async_load()
    entry.runtime_data = VaillantData(coordinator, override)

    async def set_schedule(call: ServiceCall) -> None:
        block = call.data["days"]
        try:
            payload = format_schedule([(s["from"], s["to"]) for s in call.data["slots"]], block)
            await client.write(call.data["circuit"], f"Timer.{BLOCK_DAY[block]}", payload)
        except (ValueError, EbusdError) as err:
            raise HomeAssistantError(str(err)) from err

    async def hot_water_override(call: ServiceCall) -> None:
        if "until" in call.data:
            until = dt_util.as_utc(call.data["until"])
        else:
            until = dt_util.utcnow() + timedelta(hours=call.data.get("hours", 24))
        try:
            await override.async_start(until)
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err

    async def cancel_override(call: ServiceCall) -> None:
        try:
            await override.async_cancel()
        except EbusdError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(DOMAIN, SERVICE_SET_SCHEDULE, set_schedule, SET_SCHEDULE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_HOT_WATER_OVERRIDE, hot_water_override, OVERRIDE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_OVERRIDE, cancel_override)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VaillantConfigEntry) -> bool:
    for svc in (SERVICE_SET_SCHEDULE, SERVICE_HOT_WATER_OVERRIDE, SERVICE_CANCEL_OVERRIDE):
        hass.services.async_remove(DOMAIN, svc)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
