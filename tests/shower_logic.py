"""Logiktest des Dusch-Wunsches mit simulierter Uhr und Fake-Anlage (kein ebusd, keine echte Heizung)."""
import asyncio, os, sys, warnings
from datetime import datetime, timedelta, timezone
warnings.simplefilter("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from homeassistant.util import dt as dt_util
from custom_components.vaillant_ebus import shower
from custom_components.vaillant_ebus.ebusd import EbusdError

class Sim:
    def __init__(self, local_start):
        dt_util.DEFAULT_TIME_ZONE = dt_util.get_time_zone("Europe/Berlin")
        self.t = local_start.astimezone(timezone.utc)
    def utcnow(self): return self.t
    def now(self): return dt_util.as_local(self.t)

class FakeStore:
    def __init__(self): self.data = None
    async def async_load(self): return self.data
    async def async_save(self, d): self.data = dict(d)

class FakeClient:
    def __init__(self, sim, top, cc="auto", fail_writes=0):
        self.sim, self.top, self.cc, self.log, self.fail = sim, top, cc, [], fail_writes
        self.heating = False
    async def read(self, circuit, msg, fresh=False, max_age=0):
        if (circuit, msg) == ("cc", "Mode"): return ["20", self.cc, "off", "circulation", "00", "night"]
        if (circuit, msg) == ("hwc", "Storage1Sensor2"): return [f"{self.top:.2f}", "ok"]
        raise EbusdError("unbekannt")
    async def write(self, circuit, msg, value):
        if self.fail > 0 and circuit == "cc": self.fail -= 1; raise EbusdError("simulierter Fehler")
        self.log.append((self.sim.t.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%H:%M"), circuit, msg, value))
        if (circuit, msg) == ("cc", "SetMode"): self.cc = value

class FakeCoordinator:
    def __init__(self, sim, client, program):
        self.sim, self.client, self.prog = sim, client, {"Sunday": list(program)}
        self.shower_threshold, self.shower_circ_min, self.shower_heat_max = 45.0, 10.0, 45.0
        self.writes = []
    def async_update_listeners(self): pass
    async def _read(self, key, fresh=False, max_age=0): return True
    def build_schedules(self): return {"hwc": {d: list(v) for d, v in self.prog.items()}}
    async def async_write_schedule(self, circuit, day, slots):
        from custom_components.vaillant_ebus.spec import normalize_slot
        self.prog[day] = sorted(normalize_slot(a, b) for a, b in slots)
        self.writes.append((self.sim.t.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%H:%M"), list(self.prog[day])))

class FakeHass:
    def async_create_task(self, coro): return asyncio.ensure_future(coro)

async def run(label, start_local, top, program, *, warm_rate=0.5, actions=None, fail_writes=0, cc="auto"):
    sim = Sim(start_local); client = FakeClient(sim, top, cc, fail_writes)
    coord = FakeCoordinator(sim, client, program)
    shower.Store = lambda *a, **k: FakeStore()
    m = shower.ShowerManager(FakeHass(), coord)
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    real_sleep = asyncio.sleep
    async def fake_sleep(s):
        sim.t += timedelta(seconds=s)
        loaded = bool(coord.prog["Sunday"]) and any(a <= sim.now().strftime("%H:%M") < b for a, b in coord.prog["Sunday"])
        if loaded and client.top < 55: client.top += warm_rate * s / 60
        await real_sleep(0)
    shower.asyncio.sleep = fake_sleep
    await m.async_start()
    for i in range(400):
        if actions: await actions(m, sim, i)
        if not m.active: break
        await real_sleep(0)
    print(f"\n=== {label}")
    print("  Programm vorher :", program); print("  Programm nachher:", coord.prog["Sunday"])
    print("  Schreibzugriffe Fenster:", coord.writes); print("  cc-Schreibzugriffe:", [x for x in client.log])
    print("  aktiv am Ende:", m.active, "| Puffer oben Ende:", round(client.top, 1))
    return m, client, coord, sim

async def main():
    L = lambda h, m: datetime(2026, 10, 11, h, m, tzinfo=dt_util.get_time_zone("Europe/Berlin"))
    P = [("05:10", "11:00"), ("12:00", "21:30")]
    # A) kalt, ausserhalb Fenster (Luecke 11:00-12:00)
    m, c, co, s = await run("A) kalter Puffer in der Luecke", L(11, 51), 36.0, P)
    assert not m.active and co.prog["Sunday"] == P and c.cc == "auto" and any(w[2:] == ("SetMode", "on") for w in c.log), "A fehlgeschlagen"
    assert len(co.writes) == 2, "A: erwartet 2 Fensterschreibzugriffe (setzen + wiederherstellen)"
    # B) warm
    m, c, co, s = await run("B) warmer Puffer", L(11, 51), 50.0, P)
    assert not m.active and co.writes == [] and c.cc == "auto", "B fehlgeschlagen"
    # C) kalt, innerhalb Fenster
    m, c, co, s = await run("C) kalter Puffer innerhalb eines Fensters", L(14, 0), 36.0, P)
    assert co.writes == [] and not m.active and c.cc == "auto", "C fehlgeschlagen"
    # D) Abbruch in der Aufheizphase
    async def cancel_at(m, sim, i):
        if i == 5 and m.active: await m.async_cancel()
    m, c, co, s = await run("D) Abbruch waehrend Aufheizen", L(11, 51), 36.0, P, actions=cancel_at, warm_rate=0.01)
    assert not m.active and co.prog["Sunday"] == P and c.cc == "auto", "D fehlgeschlagen"
    # E) Aufheizen hoert nach max. Zeit auf, wenn der Puffer nicht warm wird
    m, c, co, s = await run("E) Puffer wird nicht warm (Zeitlimit)", L(11, 51), 36.0, P, warm_rate=0.0)
    assert not m.active and co.prog["Sunday"] == P and c.cc == "auto", "E fehlgeschlagen"
    # F) Fehler beim Zurueckstellen -> Wiederholung (echte Fehler: die naechsten 2 cc-Schreibzugriffe schlagen fehl)
    async def break_cc(m, sim, i):
        if i == 1: m._c.client.fail = 2
    m, c, co, s = await run("F) Fehler beim Zurueckstellen, Wiederholung", L(11, 51), 50.0, P, actions=break_cc)
    assert c.fail == 0, f"F: simulierte Fehler wurden nicht ausgeloest (Rest {c.fail})"
    assert not m.active and c.cc == "auto", "F fehlgeschlagen (Wiederholung greift nicht)"
    # H) Neustart mitten im Lauf: neuer Manager setzt anhand des gespeicherten Zustands fort bzw. raeumt auf
    sim = Sim(L(11, 51)); client = FakeClient(sim, 36.0); coord = FakeCoordinator(sim, client, P)
    store = FakeStore(); shower.Store = lambda *a, **k: store
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    real_sleep = asyncio.sleep
    async def hs(sec):
        sim.t += timedelta(seconds=sec); await real_sleep(0)
    shower.asyncio.sleep = hs
    m1 = shower.ShowerManager(FakeHass(), coord); await m1.async_start()
    for _ in range(3): await real_sleep(0)
    m1._task.cancel()                      # simulierter HA-Absturz
    sim.t += timedelta(hours=3)            # HA ist 3 Stunden aus
    coord.prog["Sunday"] = [("05:10", "11:00"), ("11:50", "21:30")]   # Zusatzfenster steht noch im Regler
    m2 = shower.ShowerManager(FakeHass(), coord); await m2.async_load()
    for _ in range(50):
        if not m2.active: break
        await real_sleep(0)
    print("\n=== H) Neustart mitten im Lauf (HA 3 h aus)")
    print("  Programm nachher:", coord.prog["Sunday"], "| cc:", client.cc, "| aktiv:", m2.active)
    assert not m2.active and coord.prog["Sunday"] == P and client.cc == "auto", "H fehlgeschlagen"
    # G) vorheriger Modus 'off' wird wiederhergestellt
    m, c, co, s = await run("G) vorher Zirkulation 'off'", L(11, 51), 50.0, P, cc="off")
    assert c.cc == "off", "G fehlgeschlagen"
    print("\nALLE SZENARIEN BESTANDEN")
asyncio.run(main())
