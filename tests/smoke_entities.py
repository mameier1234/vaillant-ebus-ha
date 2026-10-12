import sys, types, asyncio, traceback
from unittest.mock import MagicMock
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import importlib
from custom_components.vaillant_ebus import spec

DATA = {k: None for k in spec.ITEMS}
DATA.update({
 "outside_temp": 11.9, "boiler_flow_temp": 35.3, "boiler_flow_desired": 41.0, "mixer_flow_temp": 39.2, "mixer_flow_desired": 42.0,
 "system_flow_temp": 39.0, "system_flow_desired": 42.0, "room_temp": 29.1, "buffer_top": 53.0, "buffer_lower_middle": 35.3,
 "buffer_bottom": 32.8, "water_pressure": 1.36, "flame": "off", "heating_pump": "on", "mixer_state": "open", "charge_pump": "off",
 "circulation_pump": "off", "party_active": "0", "holiday_active": "0", "season": "auto", "hwc_mode": "auto", "circulation_mode": "auto",
 "room_target": 22.0, "room_night": 17.0, "heating_curve": 1.4, "ot_limit": 20.0, "pump_idle": 0.0, "flow_min": 20.0, "flow_max": 90.0,
 "preheat_max": 0.0, "buffer_target": 53.0, "charge_pump_lag": 3.0, "reload_delay": 0.0, "parallel_charging": "yes", "pre_shutdown": 15.0,
 "frost_delay": 1.0, "temp_increase": 0.0, "boiler_temp_max": 80.0, "outside_correction": 0.0, "room_correction": 0.0, "holiday_temp": 14.0,
 "burner_hours": 21374.0, "burner_hours_hwc": 13613.0, "burner_starts_hc": 90761.0, "burner_starts_hwc": 13956.0,
})
SLOTS = {d: [("05:10","11:00"),("12:00","21:30")] for d in spec.DAYS}
DATA["schedules"] = {c: dict(SLOTS) for c in spec.TIMER_CIRCUITS}
DATA["holiday_period"] = ["03.01.2011","01.01.2003","31.01.2011","01.01.2003"]

coord = MagicMock(); coord.data = DATA; coord.last_update_success = True; coord.edit_day = {}; coord.nozzle_lph = 2.5
from homeassistant.util.unit_system import METRIC_SYSTEM
hass = MagicMock(); hass.config.units = METRIC_SYSTEM

ents = []
def add(label, f):
    try: ents.extend(f())
    except Exception: print("ERZEUGEN FEHLGESCHLAGEN:", label); traceback.print_exc()

from custom_components.vaillant_ebus import sensor, binary_sensor, number, select, switch, button, schedule_editor, oil, text
E="entry"
add("sensor", lambda: [sensor.VaillantSensor(coord,E,d) for d in sensor.SENSORS] + [sensor.ScheduleSensor(coord,E,c,n) for c,n in spec.TIMER_CIRCUITS.items()] + [sensor.HolidaySensor(coord,E)])
add("oil", lambda: [oil.OilUsageSensor(coord,E,"oil_used_hc","x","hc"), oil.BurnerRuntimeSensor(coord,E,"burner_fine_hc","x","hc"), oil.NozzleFlowNumber(coord,E)])
bw = oil.BurnerWindow("hc")
add("burner24", lambda: [oil.BurnerStartsWindowSensor(coord,E,"burner_starts_24h_hc","x",bw), oil.BurnerRuntimeWindowSensor(coord,E,"burner_runtime_24h_hc","y",bw)])
add("binary", lambda: [binary_sensor.VaillantBinary(coord,E,d) for d in binary_sensor.BINARIES])
add("number", lambda: [number.VaillantNumber(coord,E,d) for d in number.NUMBERS])
add("select", lambda: [select.VaillantModeSelect(coord,E,m) for m in select.MODES] + [schedule_editor.ScheduleDaySelect(coord,E,c,n) for c,n in spec.TIMER_CIRCUITS.items()])
add("switch", lambda: [switch.PartySwitch(coord,E), switch.ParallelChargingSwitch(coord,E)])
add("button", lambda: [button.QuickLoadButton(coord,E)])
from custom_components.vaillant_ebus import shower
mgr = MagicMock(); mgr.active = False; mgr.phase = "idle"; mgr.state = {}
add("shower", lambda: [shower.ShowerSwitch(coord,E,mgr), shower.ShowerStatusSensor(coord,E,mgr)] + shower.shower_numbers(coord,E) + [shower.ShowerPauseSwitch(coord,E)])
from custom_components.vaillant_ebus import presence
pm = MagicMock(); pm.persons = ["person.a"]; pm.state = {}; pm.status = "anwesend"; pm.away_since = None
coord.presence_enabled = False; coord.presence_delay_min = 20.0
add("presence", lambda: [presence.PresenceSwitch(coord,E,pm), presence.PresenceDelayNumber(coord,E), presence.PresenceStatusSensor(coord,E,pm)])
add("text", lambda: [schedule_editor.ScheduleSlotText(coord,E,c,n,s) for c,n in spec.TIMER_CIRCUITS.items() for s in range(3)])

bad = 0; uids = set()
for e in ents:
    e.hass = hass
    name = f"{type(e).__name__}:{e.unique_id}"
    if e.unique_id in uids: print("DOPPELTE unique_id", e.unique_id); bad += 1
    uids.add(e.unique_id)
    try:
        st = e.state; av = e.available; at = e.extra_state_attributes
        if st in (None, "unknown") and av: print(f"  ?? {name}: state={st!r} available={av}"); bad += 1
    except Exception as ex:
        bad += 1; print(f"  FEHLER {name}: {type(ex).__name__}: {ex}"); traceback.print_exc(limit=2)
print(f"\n{len(ents)} Entitaeten geprueft, {bad} Probleme")
for e in ents:
    if type(e).__name__ in ("NozzleFlowNumber","VaillantNumber","ScheduleSlotText","ScheduleSensor","ParallelChargingSwitch","VaillantModeSelect","ShowerSwitch","ShowerStatusSensor","ShowerNumber","ShowerPauseSwitch","BurnerRuntimeSensor","OilUsageSensor","BurnerStartsWindowSensor","BurnerRuntimeWindowSensor","PresenceSwitch","PresenceDelayNumber","PresenceStatusSensor"):
        e.hass = hass
        try: print(f"  {type(e).__name__:22} {e.unique_id[-28:]:28} -> {e.state!r}")
        except Exception as ex: print("  ", type(e).__name__, "state fehlt:", ex)
