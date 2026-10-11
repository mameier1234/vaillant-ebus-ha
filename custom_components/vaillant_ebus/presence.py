"""Anwesenheitsgesteuerte Warmwasser-Pause.

Sind alle ausgewaehlten Personen laenger als die eingestellte Zeit nicht zuhause, wird fuer *heute*
- das Pufferladungs-Zeitprogramm geleert (der Regler haelt den Puffer dann nicht mehr auf Temperatur) und
- die Zirkulation auf ``off`` gestellt (nur wenn sie auf ``auto`` stand).
Kommt jemand heim, wechselt der Tag, wird die Erkennung ausgeschaltet oder startet HA neu, wird alles aus dem
gespeicherten Original wiederhergestellt. Ein laufender Dusch-Wunsch hat Vorrang (Wechsel warten auf sein Ende).
Heizkreis und Heizung werden nicht angefasst.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import VaillantCoordinator
from .ebusd import EbusdError
from .entity import VaillantEntity
from .spec import DAYS

_LOGGER = logging.getLogger(__name__)

CHECK_SECONDS = 60
DEFAULT_DELAY_MIN = 20


class PresenceManager:
    def __init__(self, hass: HomeAssistant, coordinator: VaillantCoordinator, persons: list[str]) -> None:
        self._hass = hass
        self._c = coordinator
        self.persons = list(persons)
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.presence")
        self.state: dict[str, Any] = {}
        self.away_since: datetime | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._busy = False

    # --- Zustand ---------------------------------------------------------------------
    @property
    def suspended(self) -> bool:
        return bool(self.state)

    def _states_away(self) -> bool:
        """Alle ausgewaehlten Personen sind sicher nicht zuhause (unbekannt/nicht verfuegbar zaehlt als zuhause)."""
        if not self.persons:
            return False
        for p in self.persons:
            st = self._hass.states.get(p)
            if st is None or st.state in ("home", "unknown", "unavailable"):
                return False
        return True

    @property
    def status(self) -> str:
        if not self._c.presence_enabled or not self.persons:
            return "aus"
        if self.suspended:
            return "pausiert"
        return "abwesend" if self._states_away() else "anwesend"

    async def _save(self) -> None:
        await self._store.async_save(self.state)
        self._c.presence_suspended_day = self.state.get("day")
        self._c.async_update_listeners()

    # --- Lebenszyklus ----------------------------------------------------------------
    async def async_load(self) -> None:
        self.state = await self._store.async_load() or {}
        self._c.presence_suspended_day = self.state.get("day")

    def async_start(self) -> None:
        if self.persons:
            self._unsubs.append(async_track_state_change_event(self._hass, self.persons, self._person_changed))
        self._unsubs.append(
            async_track_time_interval(self._hass, self._tick, timedelta(seconds=CHECK_SECONDS))
        )
        self._hass.async_create_task(self.async_evaluate())

    def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs = []

    @callback
    def _person_changed(self, _event: Any) -> None:
        self._hass.async_create_task(self.async_evaluate())

    async def _tick(self, _now: Any) -> None:
        await self.async_evaluate()

    # --- Logik -----------------------------------------------------------------------
    async def async_evaluate(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            await self._evaluate()
        except EbusdError as err:
            _LOGGER.warning("Anwesenheits-Pause: %s", err)
        finally:
            self._busy = False
            self._c.async_update_listeners()

    async def _evaluate(self) -> None:
        c = self._c
        shower_active = bool(c.shower and c.shower.active)
        today = DAYS[dt_util.now().weekday()]
        if not c.presence_enabled or not self.persons:
            self.away_since = None
            if self.suspended and not shower_active:
                await self._resume()
            return
        if self.suspended:
            if shower_active:
                return
            if self.state.get("resume_pending") or self.state.get("day") != today or not self._states_away():
                await self._resume()
            return
        if self._states_away():
            now = dt_util.utcnow()
            if self.away_since is None:
                self.away_since = now
            waited = (now - self.away_since).total_seconds() / 60
            if waited >= c.presence_delay_min and not shower_active:
                await self._suspend()
        else:
            self.away_since = None

    async def _suspend(self) -> None:
        c = self._c
        client = c.client
        local = dt_util.now()
        day = DAYS[local.weekday()]
        await c._read(("hwc", f"Timer.{day}"), fresh=True, max_age=0)
        orig = list(c.build_schedules().get("hwc", {}).get(day, []))
        prev_cc = (await client.read("cc", "Mode", fresh=True))[1]
        self.state = {
            "day": day, "orig": [list(x) for x in orig], "prev_cc": prev_cc, "cc_set": False,
            "since": dt_util.utcnow().isoformat(), "resume_pending": False,
        }
        c.presence_suspended_day = day
        try:
            if orig:
                await c.async_write_schedule("hwc", day, [], internal=True)
            if prev_cc == "auto":
                await client.write("cc", "SetMode", "off")
                self.state["cc_set"] = True
        except EbusdError as err:
            _LOGGER.warning("Anwesenheits-Pause konnte nicht gesetzt werden (%s), nehme zurueck", err)
            await self._resume()
            return
        await self._save()
        _LOGGER.info("Niemand zuhause: Warmwasser-Pause fuer %s gesetzt", day)

    async def _resume(self) -> None:
        c = self._c
        s = self.state
        try:
            if s.get("orig"):
                await c.async_write_schedule("hwc", s["day"], [tuple(x) for x in s["orig"]], internal=True)
            if s.get("cc_set"):
                prev = s.get("prev_cc", "auto")
                await c.client.write("cc", "SetMode", prev if prev in ("auto", "on", "off") else "auto")
        except EbusdError as err:
            _LOGGER.warning("Anwesenheits-Pause: Wiederherstellen fehlgeschlagen (%s), neuer Versuch", err)
            self.state["resume_pending"] = True
            await self._save()
            return
        self.state = {}  # away_since bleibt: ist weiterhin niemand da (Tageswechsel), muss nicht neu gewartet werden
        await self._save()
        _LOGGER.info("Warmwasser-Pause beendet, Programm wiederhergestellt")


# --- Entitaeten ------------------------------------------------------------------------
class PresenceSwitch(VaillantEntity, SwitchEntity, RestoreEntity):
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, manager: PresenceManager) -> None:
        super().__init__(coordinator, entry_id, "presence_enabled", "Anwesenheitserkennung Warmwasser")
        self._m = manager

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.presence_enabled)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.coordinator.presence_enabled = last.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.presence_enabled = True
        self.async_write_ha_state()
        await self._m.async_evaluate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.presence_enabled = False
        self.async_write_ha_state()
        await self._m.async_evaluate()  # stellt ein bestehende Pause sofort zurueck


class PresenceDelayNumber(VaillantEntity, RestoreNumber):
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 5
    _attr_native_max_value = 240
    _attr_native_step = 5
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "presence_delay", "Abwesend ab (Wartezeit)")
        self._value = float(DEFAULT_DELAY_MIN)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._value = float(last.native_value)
        self.coordinator.presence_delay_min = self._value

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.coordinator.presence_delay_min = value
        self.async_write_ha_state()


class PresenceStatusSensor(VaillantEntity, SensorEntity):
    _attr_icon = "mdi:account-clock"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["aus", "anwesend", "abwesend", "pausiert"]

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, manager: PresenceManager) -> None:
        super().__init__(coordinator, entry_id, "presence_status", "Anwesenheit Warmwasser Status")
        self._m = manager

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return self._m.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._m.state
        return {
            "personen": self._m.persons,
            "pausiert_seit": s.get("since"),
            "pause_fuer_tag": s.get("day"),
            "abwesend_seit": self._m.away_since.isoformat() if self._m.away_since else None,
        }
