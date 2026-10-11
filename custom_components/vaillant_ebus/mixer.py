"""Mischer-Diagnose: Verdacht 'Mischer haengt' und Spreizung aus den aufgeklebten Rohrfuehlern.

Verdacht (nur Meldung, es wird nichts geschaltet): ueber ein Fenster von WINDOW_MIN Minuten gilt durchgehend
- Ist-Vorlauf liegt mindestens GAP_K unter Soll,
- Puffer oben liegt mindestens GAP_K ueber Soll (Waerme waere da),
- der Vorlauf steigt in dieser Zeit um weniger als RISE_K,
- der Regler hat den Mischer ueberwiegend auf 'oeffnen' gestellt (>= 40 % der Messungen).
Die aufgeklebten Rohrfuehler (ausserhalb montiert) zeigen absolut etwas zu wenig; interessant ist die Spreizung
Vorlauf - Ruecklauf: ~0 K bei laufender Pumpe heisst, es fliesst keine Waerme in den Kreis.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .coordinator import VaillantCoordinator
from .entity import VaillantEntity

EXT_FLOW = "sensor.temperatur_speicheroben_tempspeicherobensolar_temperatur"  # Rohr Vorlauf (aufgeklebt)
EXT_RETURN = "sensor.temperatur_speicheroben_tempspeicheroben_temperatur"  # Rohr Ruecklauf (aufgeklebt)

WINDOW_MIN = 15
GAP_K = 3.0
RISE_K = 1.0
OPEN_SHARE = 0.4
MIN_SAMPLES = 20  # bei 15-s-Takt ca. 5 Minuten Daten


class MixerStuckBinary(VaillantEntity, BinarySensorEntity):
    _attr_icon = "mdi:valve-closed"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "mixer_stuck", "Mischer hängt (Verdacht)")
        self._samples: deque[tuple[datetime, float, float, float, bool]] = deque()
        self._on = False

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self._on

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"fenster_min": WINDOW_MIN, "messungen": len(self._samples)}

    @callback
    def _handle_coordinator_update(self) -> None:
        d = self.coordinator.data or {}
        try:
            flow, want, buf = float(d["mixer_flow_temp"]), float(d["mixer_flow_desired"]), float(d["buffer_top"])
        except (KeyError, TypeError, ValueError):
            super()._handle_coordinator_update()
            return
        now = dt_util.utcnow()
        self._samples.append((now, flow, want, buf, str(d.get("mixer_state")) == "open"))
        while self._samples and now - self._samples[0][0] > timedelta(minutes=WINDOW_MIN):
            self._samples.popleft()
        was = self._on
        self._on = self._evaluate(now)
        if self._on and not was:
            persistent_notification.async_create(
                self.hass,
                "Der Vorlauf folgt dem Soll trotz öffnendem Mischer seit mehr als "
                f"{WINDOW_MIN} Minuten nicht, obwohl der Puffer warm genug ist. Mischer/Stellantrieb "
                "(Handhebel) prüfen.",
                title="Heizung: Mischer hängt (Verdacht)", notification_id="vaillant_ebus_mixer_stuck",
            )
        elif was and not self._on:
            persistent_notification.async_dismiss(self.hass, "vaillant_ebus_mixer_stuck")
        super()._handle_coordinator_update()

    def _evaluate(self, now: datetime) -> bool:
        s = self._samples
        if len(s) < MIN_SAMPLES or now - s[0][0] < timedelta(minutes=WINDOW_MIN - 1):
            return False
        if not all(want - flow >= GAP_K and buf - want >= GAP_K for _, flow, want, buf, _ in s):
            return False
        if max(x[1] for x in s) - s[0][1] >= RISE_K:
            return False
        return sum(1 for x in s if x[4]) / len(s) >= OPEN_SHARE


class PipeSpreadSensor(VaillantEntity, SensorEntity):
    """Spreizung Vorlauf - Ruecklauf des Heizkreises aus den aufgeklebten Rohrfuehlern."""

    _attr_icon = "mdi:thermometer-lines"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: VaillantCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "pipe_spread", "Heizkreis Spreizung (Rohrfühler)")

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(self.hass, [EXT_FLOW, EXT_RETURN], self._ext_changed)
        )

    @callback
    def _ext_changed(self, _event: Any) -> None:
        self.async_write_ha_state()

    def _val(self, entity_id: str) -> float | None:
        st = self.hass.states.get(entity_id)
        try:
            return float(st.state) if st else None
        except ValueError:
            return None

    @property
    def native_value(self) -> float | None:
        a, b = self._val(EXT_FLOW), self._val(EXT_RETURN)
        return None if a is None or b is None else round(a - b, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"vorlauf_rohr": self._val(EXT_FLOW), "ruecklauf_rohr": self._val(EXT_RETURN)}
