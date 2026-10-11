"""Dusch-Wunsch: Puffer bei Bedarf aufheizen und Zirkulation zeitlich begrenzt einschalten.

Ablauf (alles zeitlich begrenzt, der Regler bleibt jederzeit der Chef):
1. Liegt "Puffer oben" unter der Schwelle und laeuft gerade kein Pufferladungs-Fenster, wird fuer heute ein
   Zusatzfenster in das Pufferladungs-Zeitprogramm geschrieben (Regler laedt dann, getestet). Das Fenster endet
   von selbst; HA entfernt es zusaetzlich, sobald der Puffer warm genug ist, und stellt das Programm wieder her.
2. Erst wenn der Puffer oben warm genug ist (oder schon war), wird die Zirkulation eingeschaltet
   (``cc SetMode on``, isoliert getestet) und nach kurzer Zeit auf den vorherigen Modus zurueckgestellt - damit
   das heisse Wasser schnell an der Dusche ankommt, ohne lauwarmes Wasser im Kreis zu pumpen.

Der Zustand wird gespeichert; nach einem HA-Neustart wird aufgeraeumt bzw. fortgesetzt.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import VaillantCoordinator
from .ebusd import EbusdError
from .entity import VaillantEntity
from .spec import DAYS, in_slots, merge_slots, normalize_slot

_LOGGER = logging.getLogger(__name__)

POLL_SECONDS = 20
HYSTERESIS = 1.0  # Puffer gilt als warm genug ab Schwelle + 1 K
LAST_END = "23:50"  # Fenster nie ueber Mitternacht schreiben
DEFAULT_RATE = 0.35  # K/min Aufheizrate "Puffer oben" (aus Verlaufsdaten; wird aus echten Durchlaeufen gelernt)
SAFETY = 1.5  # Fensterlaenge = Prognose * SAFETY + MARGIN
MARGIN_MIN = 10
MIN_WINDOW_MIN = 20
PAUSE_FACTOR = 1.25  # Startschaetzung: mit pausierter Heizung ca. 25 % schneller (wird gelernt)
PARALLEL = ("hwc", "HcParallelStorageFillingEnabled2")


class ShowerManager:
    def __init__(self, hass: HomeAssistant, coordinator: VaillantCoordinator) -> None:
        self._hass = hass
        self._c = coordinator
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.shower")
        self._learn: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.shower_learn")
        self.rate: float = DEFAULT_RATE
        self.rate_pause: float = DEFAULT_RATE * PAUSE_FACTOR
        self.state: dict[str, Any] = {}
        self._task: asyncio.Task | None = None

    # --- Zustand ---------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self.state)

    @property
    def phase(self) -> str:
        return self.state.get("phase", "idle")

    async def _save(self) -> None:
        await self._store.async_save(self.state)
        self._c.async_update_listeners()

    # --- Lebenszyklus ----------------------------------------------------------------
    def eta_minutes(self, top: float | None, threshold: float, pause: bool = False) -> float | None:
        """Prognose in Minuten bis 'Puffer oben' die Schwelle (+Hysterese) erreicht."""
        if top is None:
            return None
        return max(0.0, threshold + HYSTERESIS - top) / (self.rate_pause if pause else self.rate)

    def _window_minutes(self, eta: float | None, heat_max: float) -> float:
        if eta is None:
            return heat_max
        return min(heat_max, max(MIN_WINDOW_MIN, eta * SAFETY + MARGIN_MIN))

    async def _learn_rate(self, top: float | None, now: datetime) -> None:
        """Beobachtete Heizrate in den gelernten Wert einmitteln (nur bei plausiblen Daten)."""
        t0, top0 = self.state.get("heat_start"), self.state.get("heat_start_top")
        if top is None or t0 is None or top0 is None:
            return
        minutes = (now - dt_util.parse_datetime(t0)).total_seconds() / 60
        rise = top - top0
        if minutes >= 5 and rise >= 2:
            obs = rise / minutes
            if 0.05 <= obs <= 2.0:
                if self.state.get("pause") and self.state.get("par_restore"):
                    self.rate_pause = round(0.7 * self.rate_pause + 0.3 * obs, 3)
                else:
                    self.rate = round(0.7 * self.rate + 0.3 * obs, 3)
                await self._learn.async_save({"rate": self.rate, "rate_pause": self.rate_pause})
                _LOGGER.info("Dusch-Wunsch: Heizrate gelernt: %.2f / pausiert %.2f K/min (beobachtet %.2f)",
                             self.rate, self.rate_pause, obs)

    async def async_load(self) -> None:
        learned = await self._learn.async_load() or {}
        self.rate = float(learned.get("rate", DEFAULT_RATE))
        self.rate_pause = float(learned.get("rate_pause", self.rate * PAUSE_FACTOR))
        self.state = await self._store.async_load() or {}
        if self.state:
            self.state.setdefault("cc_set", True)  # Zustand aus v0.8.0: Zirkulation lief von Anfang an
            _LOGGER.info("Dusch-Wunsch nach Neustart fortgesetzt (Phase %s)", self.phase)
            self._task = self._hass.async_create_task(self._run())

    async def async_start(self) -> None:
        if self.active:
            return
        client = self._c.client
        pause = bool(self._c.shower_pause_heating)
        try:
            prev = (await client.read("cc", "Mode", fresh=True))[1]
            top = await self._top()
            now = dt_util.utcnow()
            thr, circ, heat = self._c.shower_threshold, self._c.shower_circ_min, self._c.shower_heat_max
            st: dict[str, Any] = {
                "prev_cc": prev, "cc_set": False, "start": now.isoformat(), "threshold": thr, "circ_min": circ,
                "heat_max": heat, "window": None, "phase": "circ", "top": top, "pause": False, "par_restore": None,
                "circ_end": (now + timedelta(minutes=circ)).isoformat(),
            }
            self.state = st  # damit _finish bei Fehlern alles Geaenderte zuruecknehmen kann
            if top is not None and top < thr:
                eta = self.eta_minutes(top, thr, pause)
                win = self._window_minutes(eta, heat)
                st.update(phase="heat", heat_end=(now + timedelta(minutes=win)).isoformat(), eta_min=eta,
                          heat_start=now.isoformat(), heat_start_top=top, pause=pause)
                st.pop("circ_end")
                st["window"] = await self._open_window(win)
                if pause:
                    par = (await client.read(*PARALLEL, fresh=True))[0]
                    if par == "yes":
                        await client.write(*PARALLEL, "no")  # Heizung waehrend der Ladung pausieren
                        st["par_restore"] = "yes"
            else:
                await client.write("cc", "SetMode", "on")  # Puffer ist schon warm: gleich zirkulieren
                st["cc_set"] = True
        except EbusdError as err:
            await self._finish()  # alles bereits Geaenderte zuruecknehmen
            raise HomeAssistantError(f"Dusch-Wunsch konnte nicht gestartet werden: {err}") from err
        await self._save()
        self._task = self._hass.async_create_task(self._run())

    async def async_cancel(self) -> None:
        if not self.active:
            return
        if self._task:
            self._task.cancel()
            self._task = None
        await self._finish()

    # --- Hilfen ----------------------------------------------------------------------
    async def _top(self) -> float | None:
        try:
            tok = await self._c.client.read("hwc", "Storage1Sensor2", fresh=True)
            if len(tok) > 1 and tok[1] != "ok":
                return None
            return float(tok[0])
        except (EbusdError, ValueError):
            return None

    async def _open_window(self, heat_min: float) -> dict[str, Any] | None:
        local = dt_util.now()
        day = DAYS[local.weekday()]
        await self._c._read(("hwc", f"Timer.{day}"), fresh=True, max_age=0)
        orig = list(self._c.build_schedules().get("hwc", {}).get(day, []))
        hhmm = local.strftime("%H:%M")
        if in_slots(orig, hhmm):
            return None  # laeuft ohnehin ein Ladefenster
        end_local = local + timedelta(minutes=heat_min)
        end = LAST_END if end_local.date() != local.date() else min(end_local.strftime("%H:%M"), LAST_END)
        start, end = normalize_slot(hhmm, end)
        end = min(end, LAST_END)
        if start >= end:
            return None
        merged = merge_slots(orig, (start, end))
        if len(merged) > 3:
            _LOGGER.warning("Dusch-Wunsch: Pufferladungs-Programm hat keinen freien Slot")
            return None
        await self._c.async_write_schedule("hwc", day, merged, internal=True)
        return {"day": day, "orig": [list(x) for x in orig], "slot": [start, end]}

    async def _restore_parallel(self) -> None:
        val = self.state.get("par_restore")
        if val:
            await self._c.client.write(*PARALLEL, val)
            self.state["par_restore"] = None

    async def _close_window(self) -> None:
        w = self.state.get("window")
        if not w:
            return
        await self._c.async_write_schedule("hwc", w["day"], [tuple(x) for x in w["orig"]], internal=True)
        self.state["window"] = None

    async def _finish(self) -> None:
        """Alles zuruecknehmen; bei Fehlern Zustand behalten, der Lauf versucht es weiter."""
        try:
            await self._restore_parallel()
            await self._close_window()
            if self.state.get("cc_set"):
                prev = self.state.get("prev_cc", "auto")
                await self._c.client.write("cc", "SetMode", prev if prev in ("auto", "on", "off") else "auto")
                self.state["cc_set"] = False
        except EbusdError as err:
            _LOGGER.warning("Dusch-Wunsch: Aufraeumen fehlgeschlagen (%s), neuer Versuch", err)
            self.state["phase"] = "finish"
            await self._save()
            if not self._task:
                self._task = self._hass.async_create_task(self._run())
            return
        self.state = {}
        await self._save()

    # --- Hauptschleife ---------------------------------------------------------------
    async def _run(self) -> None:
        try:
            while self.state:
                now = dt_util.utcnow()
                ph = self.phase
                try:
                    if ph == "finish":
                        await self._finish()
                        if not self.state:
                            return
                    elif ph == "heat":
                        top = await self._top()
                        self.state["top"] = top
                        eta = self.eta_minutes(top, self.state["threshold"], bool(self.state.get("pause")))
                        self.state["eta_min"] = None if eta is None else round(eta, 1)
                        heat_end = dt_util.parse_datetime(self.state["heat_end"])
                        reached = top is not None and top >= self.state["threshold"] + HYSTERESIS
                        if reached or now >= heat_end:
                            if reached:
                                await self._learn_rate(top, now)
                            await self._restore_parallel()
                            await self._close_window()
                            warm_enough = reached or (top is not None and top >= self.state["threshold"] - 3)
                            if warm_enough:
                                await self._c.client.write("cc", "SetMode", "on")
                                self.state["cc_set"] = True
                                self.state["phase"] = "circ"
                                self.state["circ_end"] = (now + timedelta(minutes=self.state["circ_min"])).isoformat()
                                await self._save()
                            else:  # Puffer wurde nicht warm: lauwarmes Wasser nicht im Kreis pumpen
                                await self._finish()
                                if not self.state:
                                    return
                    elif ph == "circ":
                        if now >= dt_util.parse_datetime(self.state["circ_end"]):
                            await self._finish()
                            if not self.state:
                                return
                except EbusdError as err:
                    _LOGGER.warning("Dusch-Wunsch: %s", err)
                self._c.async_update_listeners()
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise


# --- Entitaeten ------------------------------------------------------------------------
class ShowerSwitch(VaillantEntity, SwitchEntity):
    _attr_icon = "mdi:shower-head"

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, manager: ShowerManager) -> None:
        super().__init__(coordinator, entry_id, "shower_request", "Dusch-Wunsch")
        self._m = manager

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._m.active

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._m.state
        return {"phase": self._m.phase, "puffer_oben": s.get("top"), "schwelle": s.get("threshold"),
                "prognose_min": s.get("eta_min"), "heizung_pausiert": bool(s.get("par_restore"))} if s else {}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._m.async_start()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._m.async_cancel()


class ShowerPauseSwitch(VaillantEntity, SwitchEntity, RestoreEntity):
    """Option: Heizung waehrend der Dusch-Ladung pausieren (Parallele Ladung AUS), danach zurueck."""

    _attr_icon = "mdi:radiator-off"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "shower_pause_heating", "Dusch-Wunsch Heizung pausieren")

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.shower_pause_heating)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self.coordinator.shower_pause_heating = last.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.shower_pause_heating = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.shower_pause_heating = False
        self.async_write_ha_state()


class ShowerStatusSensor(VaillantEntity, SensorEntity):
    _attr_icon = "mdi:shower"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["bereit", "aufheizen", "zirkulation", "aufraeumen"]

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, manager: ShowerManager) -> None:
        super().__init__(coordinator, entry_id, "shower_status", "Dusch-Wunsch Status")
        self._m = manager

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return {"idle": "bereit", "heat": "aufheizen", "circ": "zirkulation", "finish": "aufraeumen"}[self._m.phase]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._m.state
        if not s:
            return {}
        end = s.get("heat_end") if self._m.phase == "heat" else s.get("circ_end")
        return {"ende": end, "puffer_oben": s.get("top"), "schwelle": s.get("threshold"),
                "prognose_min": s.get("eta_min"), "heizrate_k_pro_min": self._m.rate,
                "heizrate_pausiert_k_pro_min": self._m.rate_pause, "heizung_pausiert": bool(s.get("par_restore")),
                "zusatzfenster": s.get("window", {}) and s["window"].get("slot")}


class ShowerNumber(VaillantEntity, RestoreNumber):
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str, key: str, name: str, attr: str,
                 default: float, vmin: float, vmax: float, step: float, unit: str, icon: str) -> None:
        super().__init__(coordinator, entry_id, key, name)
        self._attr_name = name
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step = vmin, vmax, step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._val_attr = attr
        self._value = default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._value = float(last.native_value)
        setattr(self.coordinator, self._val_attr, self._value)

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        setattr(self.coordinator, self._val_attr, value)
        self.async_write_ha_state()


def shower_numbers(coordinator: VaillantCoordinator, entry_id: str) -> list[ShowerNumber]:
    return [
        ShowerNumber(coordinator, entry_id, "shower_threshold", "Dusch-Wunsch Puffer-Schwelle", "shower_threshold",
                     45, 30, 60, 1, UnitOfTemperature.CELSIUS, "mdi:thermometer-low"),
        ShowerNumber(coordinator, entry_id, "shower_circ_min", "Dusch-Wunsch Zirkulation Dauer", "shower_circ_min",
                     5, 2, 30, 1, UnitOfTime.MINUTES, "mdi:timer-outline"),
        ShowerNumber(coordinator, entry_id, "shower_heat_max", "Dusch-Wunsch max. Aufheizzeit", "shower_heat_max",
                     45, 10, 120, 5, UnitOfTime.MINUTES, "mdi:timer-sand"),
    ]
