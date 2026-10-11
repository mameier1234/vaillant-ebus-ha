"""Koordinator: liest ebusd-Nachrichten gestaffelt (schnell/langsam) und parst sie."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import EMPTY_SLOT, MAX_SLOTS, TICK_SECONDS
from .ebusd import EbusdClient, EbusdError
from .spec import (
    DAYS,
    HOLIDAY_PERIOD,
    ITEMS,
    TIMER_CIRCUITS,
    WRITES,
    all_messages,
    parse,
    timer_slots,
)

_LOGGER = logging.getLogger(__name__)


def format_schedule(slots: list[tuple[str, str]], daysel: str = "selected") -> str:
    """[("05:10","11:00"), ...] -> "05:10;11:00;-:-;-:-;-:-;-:-;selected"."""
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
    return ";".join(parts + [daysel])


class VaillantCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Haelt Rohdaten je (Kreis, Nachricht) und leitet daraus Werte, Zeitprogramme und Ferien ab."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EbusdClient) -> None:
        super().__init__(
            hass, _LOGGER, name="vaillant_ebus", config_entry=entry,
            update_interval=timedelta(seconds=TICK_SECONDS),
        )
        self.client = client
        self._messages = all_messages()
        self._raw: dict[tuple[str, str], list[str]] = {}
        self._last: dict[tuple[str, str], float] = {}
        self.edit_day: dict[str, str] = {}  # Kreis -> Auswahl aus DAY_OPTIONS
        self.nozzle_lph: float = 2.5  # Brenner-Durchsatz in L/h (Schaetzwert, per number-Entitaet einstellbar)
        self._starts_max: dict[str, float] = {}

    async def _read(self, key: tuple[str, str], *, fresh: bool, max_age: int) -> bool:
        try:
            self._raw[key] = await self.client.read(key[0], key[1], fresh=fresh, max_age=max_age)
            self._last[key] = time.monotonic()
            return True
        except EbusdError as err:
            _LOGGER.debug("Lesefehler %s/%s: %s", key[0], key[1], err)
            return False

    async def _async_update_data(self) -> dict[str, Any]:
        now = time.monotonic()
        tried = failed = 0
        for key, (interval, fresh) in self._messages.items():
            if now - self._last.get(key, float("-inf")) < interval - 5:
                continue
            tried += 1
            if not await self._read(key, fresh=fresh, max_age=interval):
                failed += 1
        if tried and failed == tried and not self.data:
            raise UpdateFailed("ebusd antwortet auf keine Anfrage")
        return self._build()

    async def async_refresh_after_write(self, key: str) -> None:
        """Nach einem Schreibzugriff die betroffene Nachricht frisch lesen."""
        item = ITEMS[key]
        await self._read((item.circuit, item.message), fresh=True, max_age=0)
        self.async_set_updated_data(self._build())

    async def async_write(self, key: str, value: str) -> None:
        circuit, message = WRITES[key]
        await self.client.write(circuit, message, value)
        await self.async_refresh_after_write(key)

    async def async_write_schedule(self, circuit: str, day: str, slots: list[tuple[str, str]]) -> None:
        payload = format_schedule(slots)
        await self.client.write(circuit, f"Timer.{day}", payload)
        await self._read((circuit, f"Timer.{day}"), fresh=True, max_age=0)
        got = timer_slots(self._raw.get((circuit, f"Timer.{day}"), []))
        if got != sorted(slots):
            raise EbusdError(f"Zeitprogramm {circuit}/{day}: gelesen {got}, erwartet {sorted(slots)}")
        self.async_set_updated_data(self._build())

    def _build(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, item in ITEMS.items():
            tokens = self._raw.get((item.circuit, item.message))
            data[key] = parse(item, tokens) if tokens else None
        for prefix in ("hc", "hwc"):
            hi, lo = data.get(f"{prefix}_starts_hundreds"), data.get(f"{prefix}_starts_low")
            total = hi + lo if hi is not None and lo is not None else None
            if total is not None:  # nie rueckwaerts: Hunderter-Uebertrag zwischen den zwei Lesungen
                total = max(total, self._starts_max.get(prefix, total))
                self._starts_max[prefix] = total
            data[f"burner_starts_{prefix}"] = total
        holiday = self._raw.get((HOLIDAY_PERIOD.circuit, HOLIDAY_PERIOD.message))
        data["holiday_period"] = holiday
        data["schedules"] = {
            circuit: {
                day: timer_slots(self._raw.get((circuit, f"Timer.{day}"), []))
                for day in DAYS
                if (circuit, f"Timer.{day}") in self._raw
            }
            for circuit in TIMER_CIRCUITS
        }
        return data
