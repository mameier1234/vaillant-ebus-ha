"""Simulation: Brennerstarts/-laufzeit im gleitenden 24-h-Fenster (ohne echtes HA)."""
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, ".")
from custom_components.vaillant_ebus import oil

t0 = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
fails = []


def check(name, got, want):
    ok = got == want
    print(("OK   " if ok else "FAIL ") + name, got, "" if ok else f"(erwartet {want})")
    if not ok:
        fails.append(name)


def feed(w, start, seconds, flame, pump, step=15):
    t = start
    for _ in range(seconds // step):
        t += timedelta(seconds=step)
        w.update({"flame": "on" if flame else "off", "charge_pump": "on" if pump else "off"}, t)
    return t


# Laufzeit = vom ersten Messwert "an" bis zum ersten Messwert "aus" (Sample-and-hold, wie FlameIntegrator)

# 1) Heizen: 3 Zyklen a 2 Min an / 3 Min aus; Brenner war beim ersten Messwert aus
hc, hwc = oil.BurnerWindow("hc"), oil.BurnerWindow("hwc")
t = feed(hc, t0, 15, False, False)  # erster Messwert: aus
for _ in range(3):
    t = feed(hc, t, 120, True, False)
    t = feed(hc, t, 180, False, False)
check("hc starts", hc.starts(t), 3)
check("hc sekunden", hc.seconds(t), 360.0)
# Warmwasser-Fenster mit denselben Daten bleibt leer
t = feed(hwc, t0, 15, False, False)
for _ in range(3):
    t = feed(hwc, t, 120, True, False)
    t = feed(hwc, t, 180, False, False)
check("hwc starts bei Heiz-Zyklen", hwc.starts(t), 0)

# 2) Warmwasser-Ladung: Brenner + Ladepumpe; Lauf noch offen (6 Messwerte "an" = 75 s)
w = oil.BurnerWindow("hwc")
t = feed(w, t0, 60, False, False)
t = feed(w, t, 90, True, True)
check("hwc starts", w.starts(t), 1)
check("hwc sekunden (offener Lauf)", w.seconds(t), 75.0)

# 3) Fenster gleitet: nach 25 h ist alles raus
t = feed(w, t, 25 * 3600, False, False, step=60)
check("nach 25 h starts", w.starts(t), 0)
check("nach 25 h minuten", w.seconds(t), 0.0)

# 4) Laeuft beim ersten Messwert schon: kein Start, aber Laufzeit
w = oil.BurnerWindow("hc")
t = feed(w, t0, 120, True, False)
check("laeuft schon: starts", w.starts(t), 0)
check("laeuft schon: sekunden", w.seconds(t), 105.0)  # 8 Messwerte, Lauf beginnt beim ersten

# 5) Luecke > 2 Min (HA/ebusd weg) beendet den Lauf beim letzten Messwert, kein Phantom-Lauf
w = oil.BurnerWindow("hc")
t = feed(w, t0, 15, False, False)
t = feed(w, t, 60, True, False)
last = t
t = last + timedelta(minutes=30)
w.update({"flame": "off", "charge_pump": "off"}, t)
check("luecke: sekunden", w.seconds(t), 45.0)  # Lauf endet beim letzten Messwert vor der Luecke
check("luecke: starts", w.starts(t), 1)

# 6) Dump/Load ueber Neustart; offener Lauf wird beim letzten Zeitpunkt beendet, erster Messwert danach ist kein Start
w = oil.BurnerWindow("hc")
t = feed(w, t0, 15, False, False)
t = feed(w, t, 90, True, False)
raw = w.dump()
w2 = oil.BurnerWindow("hc")
w2.load(raw)
t = t + timedelta(minutes=5)
w2.update({"flame": "on", "charge_pump": "off"}, t)
check("restore: starts (1 + Neustart zaehlt nicht)", w2.starts(t), 1)

print("ALLE OK" if not fails else f"FEHLER: {fails}")
sys.exit(1 if fails else 0)
