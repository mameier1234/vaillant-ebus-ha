"""Zeitfenster-Formatierung, Koordinator und Warmwasser-Override."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BLOCK_DAYSEL,
    EMPTY_SLOT,
    MAX_SLOTS,
    SCAN_INTERVAL_SECONDS,
    SEASON_CIRCUIT,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .ebusd import EbusdClient, EbusdError

_LOGGER = logging.getLogger(__name__)


def format_schedule(slots: list[tuple[str, str]], block: str) -> str:
    """[("05:10","11:00"), ...] -> "05:10;11:00;-:-;-:-;-:-;-:-;Sa-So"."""
    if len(slots) > MAX_SLOTS:
        raise ValueError(f"max. {MAX_SLOTS} Zeitfenster")
    ordered = sorted(slots)
    for (_, end), (start, _) in zip(ordered, ordered[1:]):
        if start < end:
            raise ValueError("Zeitfenster ueberlappen sich")
    parts: list[str] = []
    for start, end in ordered:
        if start >= end:
            raise ValueError(f"Fenster {start}-{end}: Ende muss nach Start liegen")
        parts += [start, end]
    parts += [EMPTY_SLOT] * (2 * MAX_SLOTS - len(parts))
    return ";".join(parts + [BLOCK_DAYSEL[block]])


class VaillantCoordinator(DataUpdateCoordinator[dict[str, str]]):
    """Liest die Betriebsarten frisch vom Bus (kein ebusd-Cache, sonst stale nach Schreibzugriffen)."""

    def __init__(self, hass: HomeAssistant, client: EbusdClient) -> None:
        super().__init__(
            hass, _LOGGER, name="vaillant_ebus", update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS)
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, str]:
        try:
            hwc = await self.client.read("hwc", "Mode", fresh=True)  # temp0;hwcmode;...
            cc = await self.client.read("cc", "Mode", fresh=True)
            mc = await self.client.read(SEASON_CIRCUIT, "OperatingMode", fresh=True)  # mcmode
        except EbusdError as err:
            raise UpdateFailed(str(err)) from err
        return {"hwc_mode": hwc[1], "circulation_mode": cc[1], "season": mc[0]}


class OverrideManager:
    """Warmwasser zeitweise auf 'on' zwingen und danach den alten Modus zurueckgeben.

    Zustand wird persistiert, damit ein HA-Neustart den Rueckschreib-Termin nicht verliert.
    """

    def __init__(self, hass: HomeAssistant, coordinator: VaillantCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._state: dict[str, Any] = {}
        self._unsub: CALLBACK_TYPE | None = None

    @property
    def active_until(self) -> datetime | None:
        raw = self._state.get("until")
        return dt_util.parse_datetime(raw) if raw else None

    async def async_load(self) -> None:
        self._state = await self._store.async_load() or {}
        until = self.active_until
        if until:
            if until <= dt_util.utcnow():
                await self.async_cancel()
            else:
                self._schedule(until)

    async def async_start(self, until: datetime) -> None:
        client = self._coordinator.client
        if not self._state:  # nur den *urspruenglichen* Modus merken
            current = await client.read("hwc", "Mode", fresh=True)
            self._state["previous"] = current[1]
        self._state["until"] = dt_util.as_utc(until).isoformat()
        await self._store.async_save(self._state)
        await client.write("hwc", "SetMode", "on")
        self._schedule(until)
        await self._coordinator.async_request_refresh()

    async def async_cancel(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        previous = self._state.get("previous")
        if previous:
            # erst zurueckschreiben, dann Zustand loeschen -> bei Fehler bleibt der Termin erhalten
            await self._coordinator.client.write("hwc", "SetMode", previous)
        self._state = {}
        await self._store.async_save(self._state)
        await self._coordinator.async_request_refresh()

    def _schedule(self, until: datetime) -> None:
        if self._unsub:
            self._unsub()
        self._unsub = async_track_point_in_utc_time(
            self._hass, lambda now: self._hass.async_create_task(self.async_cancel()), until
        )
