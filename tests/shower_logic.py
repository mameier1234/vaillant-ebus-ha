"""Logiktest des Dusch-Wunsches mit simulierter Uhr und Fake-Anlage (kein ebusd, keine echte Heizung)."""
import asyncio, os, sys, warnings
from datetime import datetime, timedelta, timezone
warnings.simplefilter("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from homeassistant.util import dt as dt_util
from custom_components.vaillant_ebus import shower
from custom_components.vaillant_ebus.ebusd import EbusdError
REAL_SLEEP = asyncio.sleep  # Original festhalten (die Tests ueberschreiben asyncio.sleep)

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
        self.par, self.fail_par = 'yes', False
    async def read(self, circuit, msg, fresh=False, max_age=0):
        if (circuit, msg) == ("cc", "Mode"): return ["20", self.cc, "off", "circulation", "00", "night"]
        if (circuit, msg) == ("hwc", "Storage1Sensor2"): return [f"{self.top:.2f}", "ok"]
        if (circuit, msg) == ("hwc", "HcParallelStorageFillingEnabled2"): return [self.par]
        raise EbusdError("unbekannt")
    async def write(self, circuit, msg, value):
        if (circuit, msg) == ("hwc", "HcParallelStorageFillingEnabled2"):
            if self.fail_par and value == "no": raise EbusdError("simulierter Fehler (Parallele Ladung)")
            self.par = value; self.log.append((self.sim.t.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%H:%M"), circuit, msg, value)); return
        if self.fail > 0 and circuit == "cc": self.fail -= 1; raise EbusdError("simulierter Fehler")
        self.log.append((self.sim.t.astimezone(dt_util.DEFAULT_TIME_ZONE).strftime("%H:%M"), circuit, msg, value))
        if (circuit, msg) == ("cc", "SetMode"): self.cc = value

class FakeCoordinator:
    def __init__(self, sim, client, program):
        self.sim, self.client, self.prog = sim, client, {"Sunday": list(program)}
        self.shower_threshold, self.shower_circ_min, self.shower_heat_max = 45.0, 10.0, 45.0
        self.shower_pause_heating = False
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

async def run(label, start_local, top, program, *, warm_rate=0.5, actions=None, fail_writes=0, cc="auto", pause=False, fail_par=False, expect_error=False):
    stores = {}
    sim = Sim(start_local); client = FakeClient(sim, top, cc, fail_writes)
    coord = FakeCoordinator(sim, client, program)
    coord.shower_pause_heating = pause; client.fail_par = fail_par
    shower.Store = lambda hass, ver, key, **k: stores.setdefault(key, FakeStore())
    m = shower.ShowerManager(FakeHass(), coord)
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    real_sleep = REAL_SLEEP
    async def fake_sleep(s):
        sim.t += timedelta(seconds=s)
        loaded = bool(coord.prog["Sunday"]) and any(a <= sim.now().strftime("%H:%M") < b for a, b in coord.prog["Sunday"])
        if loaded and client.top < 55: client.top += warm_rate * s / 60
        await real_sleep(0)
    shower.asyncio.sleep = fake_sleep
    err = None
    try:
        await m.async_start()
    except Exception as e:
        err = e
    if expect_error:
        print(f"\n=== {label}\n  Fehler wie erwartet: {err}\n  Programm nachher: {coord.prog['Sunday']} | par: {client.par} | cc: {client.cc} | aktiv: {m.active}")
        return m, client, coord, sim
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
    t_on = [w[0] for w in c.log if w[2:] == ("SetMode", "on")][0]
    assert t_on > co.writes[0][0], f"A: Zirkulation muss NACH dem Aufheizen starten (an um {t_on}, Fenster um {co.writes[0][0]})"
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
    assert c.log == [], "D: beim Abbruch in der Aufheizphase darf cc nie angefasst werden"
    # E) Aufheizen hoert nach max. Zeit auf, wenn der Puffer nicht warm wird
    m, c, co, s = await run("E) Puffer wird nicht warm (Zeitlimit)", L(11, 51), 36.0, P, warm_rate=0.0)
    assert not m.active and co.prog["Sunday"] == P and c.cc == "auto", "E fehlgeschlagen"
    assert c.log == [], "E: wird der Puffer nicht warm, darf die Zirkulation nie starten"
    # I) Fensterlaenge richtet sich nach der Prognose
    P2 = [("05:10", "11:00")]
    m, c, co, s = await run("I1) leicht kalter Puffer (42 C): kurzes Fenster", L(11, 51), 42.0, P2, warm_rate=0.4)
    end1 = co.writes[0][1][-1][1]
    m, c, co, s = await run("I2) sehr kalter Puffer (36 C): volles Fenster", L(11, 51), 36.0, P2, warm_rate=0.4)
    end2 = co.writes[0][1][-1][1]
    print("  Fensterende 42 C:", end1, "| 36 C:", end2)
    assert end1 <= "12:20" and end2 >= "12:30" and end1 < end2, "I: Fensterlaenge passt nicht zur Prognose"
    # J) Heizrate wird aus echten Durchlaeufen gelernt (Simulation heizt mit 0.5 K/min)
    m, c, co, s = await run("J) Heizrate lernen", L(11, 51), 36.0, P2, warm_rate=0.5)
    print("  gelernte Rate:", m.rate, "(Start 0.35, beobachtet ca. 0.5)")
    assert 0.38 < m.rate < 0.48, "J: Rate wurde nicht plausibel gelernt"
    # K) Heizung pausieren: Parallele Ladung AUS waehrend des Aufheizens, danach zurueck auf AN
    m, c, co, s = await run("K) Heizung pausieren", L(11, 51), 36.0, P, pause=True)
    par = [w for w in c.log if w[2] == "HcParallelStorageFillingEnabled2"]
    print("  Parallele-Ladung-Zugriffe:", par)
    assert [w[3] for w in par] == ["no", "yes"] and c.par == "yes", "K: Parallele Ladung nicht korrekt aus/an"
    t_yes = par[1][0]; t_cc = [w[0] for w in c.log if w[2:] == ("SetMode", "on")][0]
    assert t_yes <= t_cc, "K: Heizung muss vor der Zirkulation wieder laufen"
    # K1) ohne Option bleibt die Parallele Ladung unberuehrt
    m, c, co, s = await run("K1) ohne Pause-Option", L(11, 51), 36.0, P, pause=False)
    assert not [w for w in c.log if w[2] == "HcParallelStorageFillingEnabled2"], "K1: Parallele Ladung darf nicht angefasst werden"
    # K2) Abbruch in der Aufheizphase stellt Parallele Ladung zurueck
    async def cancel_k(m, sim, i):
        if i == 5 and m.active: await m.async_cancel()
    m, c, co, s = await run("K2) Abbruch bei pausierter Heizung", L(11, 51), 36.0, P, pause=True, actions=cancel_k, warm_rate=0.01)
    assert not m.active and c.par == "yes" and co.prog["Sunday"] == P, "K2 fehlgeschlagen"
    # K3) Fehler beim Pausieren: alles bereits Geaenderte wird zurueckgenommen
    m, c, co, s = await run("K3) Fehler beim Pausieren (Start)", L(11, 51), 36.0, P, pause=True, fail_par=True, expect_error=True)
    assert not m.active and c.par == "yes" and co.prog["Sunday"] == P and c.cc == "auto", "K3: Aufraeumen nach Startfehler fehlgeschlagen"
    # F) Fehler beim Zurueckstellen -> Wiederholung (echte Fehler: die naechsten 2 cc-Schreibzugriffe schlagen fehl)
    async def break_cc(m, sim, i):
        if i == 1: m._c.client.fail = 2
    m, c, co, s = await run("F) Fehler beim Zurueckstellen, Wiederholung", L(11, 51), 50.0, P, actions=break_cc)
    assert c.fail == 0, f"F: simulierte Fehler wurden nicht ausgeloest (Rest {c.fail})"
    assert not m.active and c.cc == "auto", "F fehlgeschlagen (Wiederholung greift nicht)"
    # H) Neustart mitten im Lauf: neuer Manager setzt anhand des gespeicherten Zustands fort bzw. raeumt auf
    sim = Sim(L(11, 51)); client = FakeClient(sim, 36.0); coord = FakeCoordinator(sim, client, P)
    stores = {}; shower.Store = lambda hass, ver, key, **k: stores.setdefault(key, FakeStore())
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    real_sleep = REAL_SLEEP
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
    # H2) Zustand aus v0.8.0 (ohne cc_set-Feld): cc war schon an und muss am Ende zurueckgestellt werden
    sim = Sim(L(12, 6)); client = FakeClient(sim, 40.3, cc="on"); coord = FakeCoordinator(sim, client, [("05:10", "11:00"), ("12:00", "21:30")])
    stores = {}; shower.Store = lambda hass, ver, key, **k: stores.setdefault(key, FakeStore())
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    old = {"prev_cc": "auto", "start": sim.t.isoformat(), "threshold": 45.0, "circ_min": 10.0, "heat_max": 45.0,
           "window": {"day": "Sunday", "orig": [["05:10", "11:00"], ["13:00", "21:30"]], "slot": ["12:00", "13:00"]},
           "phase": "heat", "top": 40.3, "heat_end": (sim.t + timedelta(minutes=45)).isoformat()}
    stores["vaillant_ebus.shower"] = FakeStore(); stores["vaillant_ebus.shower"].data = old
    real_sleep = REAL_SLEEP
    async def hs2(sec):
        sim.t += timedelta(seconds=sec); client.top += 0.5 * sec / 60; await real_sleep(0)
    shower.asyncio.sleep = hs2
    m3 = shower.ShowerManager(FakeHass(), coord); await m3.async_load()
    for _ in range(400):
        if not m3.active: break
        await real_sleep(0)
    print("\n=== H2) Zustand aus v0.8.0 wird fortgesetzt")
    print("  Programm nachher:", coord.prog["Sunday"], "| cc:", client.cc, "| cc-Zugriffe:", client.log)
    assert not m3.active and client.cc == "auto" and coord.prog["Sunday"] == [("05:10", "11:00"), ("13:00", "21:30")], "H2 fehlgeschlagen"
    # K4) Neustart mitten in der pausierten Heizphase: Parallele Ladung wird zurueckgestellt
    sim = Sim(L(12, 10)); client = FakeClient(sim, 41.0); client.par = "no"
    coord = FakeCoordinator(sim, client, [("05:10", "11:00"), ("12:00", "21:30")])
    stores = {}; shower.Store = lambda hass, ver, key, **k: stores.setdefault(key, FakeStore())
    shower.dt_util.utcnow, shower.dt_util.now = sim.utcnow, sim.now
    stores["vaillant_ebus.shower"] = FakeStore()
    stores["vaillant_ebus.shower"].data = {"prev_cc": "auto", "cc_set": False, "start": sim.t.isoformat(), "threshold": 45.0, "circ_min": 5.0,
        "heat_max": 45.0, "window": {"day": "Sunday", "orig": [["05:10", "11:00"], ["13:00", "21:30"]], "slot": ["12:00", "13:00"]},
        "phase": "heat", "top": 41.0, "pause": True, "par_restore": "yes", "heat_end": (sim.t - timedelta(minutes=1)).isoformat()}
    real_sleep = REAL_SLEEP
    async def hs3(sec):
        sim.t += timedelta(seconds=sec); await real_sleep(0)
    shower.asyncio.sleep = hs3
    m4 = shower.ShowerManager(FakeHass(), coord); await m4.async_load()
    for _ in range(100):
        if not m4.active: break
        await real_sleep(0)
    print("\n=== K4) Neustart in pausierter Heizphase")
    print("  par:", client.par, "| Programm:", coord.prog["Sunday"], "| aktiv:", m4.active)
    assert not m4.active and client.par == "yes" and coord.prog["Sunday"] == [("05:10", "11:00"), ("13:00", "21:30")], "K4 fehlgeschlagen"
    # L) Brenner-Integrator: Sample-and-hold, Kategorien, Luecken
    from custom_components.vaillant_ebus.oil import FlameIntegrator
    t0 = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc); hc, hw = FlameIntegrator("hc"), FlameIntegrator("hwc")
    seq = [(0, "off", "off"), (15, "on", "on"), (30, "on", "on"), (45, "on", "off"), (60, "off", "off"), (75, "off", "off")]
    tot_hc = tot_hw = 0.0
    for sec, fl, pu in seq:
        d = {"flame": fl, "charge_pump": pu}; n = t0 + timedelta(seconds=sec)
        tot_hc += hc.delta_seconds(d, n); tot_hw += hw.delta_seconds(d, n)
    print("\n=== L) Brenner-Integrator: Heizen", tot_hc, "s | Warmwasser", tot_hw, "s (erwartet 15 / 30)")
    assert (tot_hc, tot_hw) == (15.0, 30.0), "L: Brennerzaehlung falsch"
    gap = FlameIntegrator("hc"); gap.delta_seconds({"flame": "on", "charge_pump": "off"}, t0)
    assert gap.delta_seconds({"flame": "on", "charge_pump": "off"}, t0 + timedelta(hours=1)) == 0.0, "L: lange Luecke darf nicht als Brennerlauf zaehlen"
    print("\nALLE SZENARIEN BESTANDEN")
asyncio.run(main())
