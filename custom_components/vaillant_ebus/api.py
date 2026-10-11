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
    MODE_READS,
    SCAN_INTERVAL_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    TEMP_READS,
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


class VaillantCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Liest Betriebsarten und Temperaturen frisch vom Bus (kein ebusd-Cache, sonst stale nach Schreibzugriffen).

    Einzelne Fehler (z. B. Fuehler ``cutoff``) machen nur den jeweiligen Wert ``None``;
    nur wenn *alle* Lesezugriffe scheitern, gilt die Aktualisierung als fehlgeschlagen.
    """

    def __init__(self, hass: HomeAssistant, client: EbusdClient) -> None:
        super().__init__(
            hass, _LOGGER, name="vaillant_ebus", update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS)
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        errors: list[str] = []

        for key, (circuit, message, idx) in MODE_READS.items():
            try:
                data[key] = (await self.client.read(circuit, message, fresh=True))[idx]
            except (EbusdError, IndexError) as err:
                errors.append(str(err))
                data[key] = None

        for key, (circuit, message, _name) in TEMP_READS.items():
            try:
                parts = await self.client.read(circuit, message, fresh=True)
                if len(parts) > 1 and parts[1] != "ok":
                    data[key] = None  # z. B. cutoff
                else:
                    data[key] = float(parts[0])
            except (EbusdError, ValueError) as err:
                errors.append(str(err))
                data[key] = None

        if len(errors) == len(MODE_READS) + len(TEMP_READS):
            raise UpdateFailed(errors[0])
        return data


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
