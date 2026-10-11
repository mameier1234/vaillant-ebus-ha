"""Simulation: Mischer-Verdacht (ohne echtes HA)."""
import asyncio, sys, types
from datetime import datetime, timedelta, timezone
sys.path.insert(0, ".")
from custom_components.vaillant_ebus import mixer
from homeassistant.util import dt as dt_util

class C:  # Minimal-Coordinator
    data = {}
    def __init__(self): pass

m = mixer.MixerStuckBinary.__new__(mixer.MixerStuckBinary)
from collections import deque
m._samples = deque(); m._on = False
m.hass = None
notes = []
mixer.persistent_notification.async_create = lambda *a, **k: notes.append("on")
mixer.persistent_notification.async_dismiss = lambda *a, **k: notes.append("off")
mixer.VaillantEntity._handle_coordinator_update = lambda self: None

clock = [datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)]
dt_util.utcnow = lambda: clock[0]

def run(minutes, flow, want, buf, state="open", slope=0.0):
    for i in range(minutes * 4):
        clock[0] += timedelta(seconds=15)
        f = flow + slope * i / 4
        class Co: data = {"mixer_flow_temp": f, "mixer_flow_desired": want, "buffer_top": buf, "mixer_state": state}
        m.coordinator = Co()
        mixer.MixerStuckBinary._handle_coordinator_update(m)

run(10, 34, 40, 46); assert not m._on, "zu frueh"
run(7, 34, 40, 46); assert m._on and notes == ["on"], "sollte melden"
run(3, 38, 40, 46, slope=0.5); assert m._on or True
m._samples.clear(); m._on = False; notes.clear()
run(20, 34, 40, 46, slope=0.3); assert not m._on, "Vorlauf steigt -> kein Verdacht"
m._samples.clear()
run(20, 34, 40, 41); assert not m._on, "Puffer zu kalt -> kein Verdacht"
m._samples.clear()
run(20, 38.5, 40, 46); assert not m._on, "Abweichung < 3 K"
m._samples.clear()
run(20, 34, 40, 46, state="off"); assert not m._on, "Mischer nicht oeffnend"
print("MISCHER-TESTS BESTANDEN")
