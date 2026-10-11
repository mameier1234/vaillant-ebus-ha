"""Zuordnung der Reglerwerte (auroMATIC VRS 620, Heizkreis HK2 = ebusd-Kreis ``mc``) zu ebusd-Nachrichten.

Alle Zuordnungen sind gegen die Displaywerte des Reglers verifiziert (Stand 2026-10-11).
Reine Daten, keine HA-Abhaengigkeit -> direkt gegen ebusd testbar.

Hinweise:
- ``mc Params`` liefert die *echten* Heizkreis-Parameter (== Display C2/B5); ``HeatingCurve``,
  ``TempDesiredLow`` usw. liefern abweichende Werte und werden NICHT verwendet.
- HK1 (``hc``) ist am Regler deaktiviert und wird ignoriert.
- "Warmwasser/Speicher" ist hier ein Pufferspeicher mit Frischwasserstation.
"""

from __future__ import annotations

from dataclasses import dataclass

FAST = 60  # Sekunden
SLOW = 600


@dataclass(frozen=True)
class Item:
    circuit: str
    message: str
    idx: int = 0
    interval: int = FAST
    fresh: bool = False  # immer frisch vom Bus (Betriebsarten)
    ok: bool = False  # Feld 1 muss "ok" sein (Fuehlerstatus), sonst None
    numeric: bool = True


DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
TIMER_CIRCUITS = {"mc": "Heizung", "hwc": "Pufferladung", "cc": "Zirkulation"}

# --- Lesewerte --------------------------------------------------------------------------
ITEMS: dict[str, Item] = {
    # Temperaturen
    "outside_temp": Item("broadcast", "outsidetemp"),
    "boiler_flow_temp": Item("bai", "FlowTemp", ok=True),
    "boiler_flow_desired": Item("bai", "FlowTempDesired"),
    "mixer_flow_temp": Item("mc", "FlowTemp", ok=True),
    "mixer_flow_desired": Item("mc", "Status0a", idx=4),
    "system_flow_temp": Item("ui", "FlowTemp", ok=True),
    "system_flow_desired": Item("ui", "FlowTempDesired"),
    "room_temp": Item("ui", "RoomTemp", ok=True),
    "buffer_top": Item("hwc", "Storage1Sensor2", ok=True),
    "buffer_lower_middle": Item("sc", "Storage4Sensor3", ok=True),
    "buffer_bottom": Item("sc", "Storage2Sensor3", ok=True),
    "water_pressure": Item("bai", "WaterPressure", ok=True),
    # Status
    "flame": Item("bai", "Flame", numeric=False),
    "heating_pump": Item("mc", "Status0a", idx=2, numeric=False),
    "mixer_state": Item("mc", "Status0a", idx=1, numeric=False),
    "charge_pump": Item("hwc", "Status0a", idx=2, numeric=False),
    "circulation_pump": Item("cc", "Status0a", idx=2, numeric=False),
    "party_active": Item("mc", "IsInParty", numeric=False),
    "holiday_active": Item("mc", "IsInHoliday", numeric=False),
    # Betriebsarten (immer frisch, sonst stale direkt nach dem Schreiben)
    "season": Item("mc", "OperatingMode", fresh=True, numeric=False),
    "hwc_mode": Item("hwc", "Mode", idx=1, fresh=True, numeric=False),
    "circulation_mode": Item("cc", "Mode", idx=1, fresh=True, numeric=False),
    # Heizkreis-Parameter (mc Params = Display B5/C2)
    "room_target": Item("mc", "Params", idx=0, interval=SLOW),
    "room_night": Item("mc", "Params", idx=1, interval=SLOW),
    "heating_curve": Item("mc", "Params", idx=2, interval=SLOW),
    "ot_limit": Item("mc", "Params", idx=4, interval=SLOW),
    "pump_idle": Item("mc", "Params", idx=5, interval=SLOW),
    "flow_min": Item("mc", "Params", idx=6, interval=SLOW),
    "flow_max": Item("mc", "Params", idx=7, interval=SLOW),
    "preheat_max": Item("mc", "Params", idx=8, interval=SLOW),
    # Pufferladung (C4/B5)
    "buffer_target": Item("hwc", "TempDesired2", interval=SLOW),
    "charge_pump_lag": Item("hwc", "HwcLaggingTime2", interval=SLOW),
    "reload_delay": Item("hwc", "HwcLoadingDelay2", interval=SLOW),
    "parallel_charging": Item("hwc", "HcParallelStorageFillingEnabled2", interval=SLOW, numeric=False),
    # Gesamtsystem (C7/C8/C12/B4)
    "pre_shutdown": Item("ui", "PreShutDownTime", interval=SLOW),
    "frost_delay": Item("ui", "FrostOverRideTime", interval=SLOW),
    "temp_increase": Item("ui", "TempIncrease", interval=SLOW),
    "boiler_temp_max": Item("ui", "BoilerTempMax", interval=SLOW),
    "outside_correction": Item("hc", "OutsideTempCorrection", interval=SLOW),
    "room_correction": Item("ui", "RoomTempOffset", interval=SLOW),
    "holiday_temp": Item("ui", "RoomTempHoliday", interval=SLOW),
    "burner_hours": Item("bai", "HcHours", interval=SLOW),
}

# Ferienzeitraum: Text (4 Datumsfelder), kein numerischer Wert
HOLIDAY_PERIOD = Item("ui", "HolidayPeriod", interval=SLOW, numeric=False)

# --- Schreibbare Werte: key -> (Kreis, Nachricht) -------------------------------------
WRITES: dict[str, tuple[str, str]] = {
    "season": ("mc", "SetMode"),
    "hwc_mode": ("hwc", "SetMode"),
    "circulation_mode": ("cc", "SetMode"),
    "room_target": ("mc", "SetTempDesired"),
    "room_night": ("mc", "SetTempDesiredLow"),
    "heating_curve": ("mc", "SetHeatingCurve"),
    "ot_limit": ("mc", "SetShutdownTemp"),
    "buffer_target": ("hwc", "SetTempDesired"),
    "holiday_temp": ("ui", "RoomTempHoliday"),
    "charge_pump_lag": ("hwc", "HwcLaggingTime2"),
    "reload_delay": ("hwc", "HwcLoadingDelay2"),
    "parallel_charging": ("hwc", "HcParallelStorageFillingEnabled2"),
}
QUICK_LOAD = ("mc", "load")  # Quick - WW Speicherladung (onoff)
QUICK_PARTY = ("mc", "party")  # Quick - Party (onoff)

# --- Hilfsfunktionen (rein) -------------------------------------------------------------
def message_key(item: Item) -> tuple[str, str]:
    return (item.circuit, item.message)


def all_messages() -> dict[tuple[str, str], tuple[int, bool]]:
    """(Kreis, Nachricht) -> (kleinstes Intervall, fresh?) ueber alle Items inkl. Zeitprogramme."""
    out: dict[tuple[str, str], tuple[int, bool]] = {}
    items = list(ITEMS.values()) + [HOLIDAY_PERIOD]
    for it in items:
        k = message_key(it)
        interval, fresh = out.get(k, (it.interval, it.fresh))
        out[k] = (min(interval, it.interval), fresh or it.fresh)
    for circuit in TIMER_CIRCUITS:
        for day in DAYS:
            out[(circuit, f"Timer.{day}")] = (SLOW, False)
    return out


def parse(item: Item, tokens: list[str]):
    """Token-Liste einer ebusd-Antwort -> Wert oder None (Fuehler 'cutoff', Fehler)."""
    try:
        if item.ok and (len(tokens) <= 1 or tokens[1] != "ok"):
            return None
        raw = tokens[item.idx].strip()
        if item.numeric:
            return float(raw)
        return raw
    except (IndexError, ValueError):
        return None


def timer_slots(tokens: list[str]) -> list[tuple[str, str]]:
    """'05:10;11:00;12:00;21:30;-:-;-:-;Sa-So' -> [('05:10','11:00'), ('12:00','21:30')]."""
    slots = []
    for i in range(0, 6, 2):
        if i + 1 < len(tokens) and tokens[i] != "-:-" and tokens[i + 1] != "-:-":
            slots.append((tokens[i], tokens[i + 1]))
    return slots


# --- Zeitprogramm-Editor ----------------------------------------------------------------
# Auswahl "Tag" -> betroffene Wochentage (None = heute)
DAY_OPTIONS: dict[str, tuple[str, ...] | None] = {
    "Heute": None,
    "Mo": ("Monday",), "Di": ("Tuesday",), "Mi": ("Wednesday",), "Do": ("Thursday",),
    "Fr": ("Friday",), "Sa": ("Saturday",), "So": ("Sunday",),
    "Mo–Fr": DAYS[:5],
    "Sa–So": DAYS[5:],
}


def format_slots(slots: list[tuple[str, str]]) -> str:
    return ", ".join(f"{a}-{b}" for a, b in slots) if slots else "aus"


def parse_slots(text: str) -> list[tuple[str, str]]:
    """'5:10-11:00, 12:00–21:30' -> [('05:10','11:00'), ('12:00','21:30')]; 'aus'/'' -> []."""
    import re

    text = text.strip().lower()
    if text in ("", "aus", "-", "off"):
        return []
    slots = []
    for part in text.split(","):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\s*", part)
        if not m:
            raise ValueError(f"Ungültiges Zeitfenster: {part.strip()!r} (Format HH:MM-HH:MM)")
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        if h1 > 23 or h2 > 24 or m1 > 59 or m2 > 59 or (h2 == 24 and m2):
            raise ValueError(f"Ungültige Uhrzeit in {part.strip()!r}")
        slots.append((f"{h1:02d}:{m1:02d}", f"{h2:02d}:{m2:02d}"))
    return slots
