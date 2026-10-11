"""Logiktest der anwesenheitsgesteuerten Warmwasser-Pause (simulierte Uhr, Fake-Anlage, Fake-Personen)."""
import asyncio, os, sys, warnings
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
warnings.simplefilter("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from homeassistant.util import dt as dt_util
from custom_components.vaillant_ebus import presence
from custom_components.vaillant_ebus.ebusd import EbusdError
from custom_components.vaillant_ebus.spec import DAYS

TZ = dt_util.get_time_zone("Europe/Berlin"); dt_util.DEFAULT_TIME_ZONE = TZ
class Sim:
    def __init__(self, h, m, day=11): self.t = datetime(2026, 10, day, h, m, tzinfo=TZ).astimezone(timezone.utc)
    def utcnow(self): return self.t
    def now(self): return dt_util.as_local(self.t)
    def adv(self, minutes): self.t += timedelta(minutes=minutes)

class FakeStore:
    def __init__(self): self.data = None
    async def async_load(self): return self.data
    async def async_save(self, d): self.data = dict(d)

class FakeClient:
    def __init__(self): self.cc = "auto"; self.fail_cc = 0; self.log = []
    async def read(self, c, m, fresh=False, max_age=0):
        assert (c, m) == ("cc", "Mode"); return ["20", self.cc, "off", "circulation", "00", "night"]
    async def write(self, c, m, v):
        if self.fail_cc > 0: self.fail_cc -= 1; raise EbusdError("simuliert")
        assert (c, m) == ("cc", "SetMode"); self.cc = v; self.log.append(v)

class FakeCoord:
    def __init__(self, program):
        self.client = FakeClient(); self.prog = {d: list(program) for d in DAYS}
        self.presence_enabled = True; self.presence_delay_min = 20.0; self.presence_suspended_day = None
        self.shower = SimpleNamespace(active=False); self.writes = []
    def async_update_listeners(self): pass
    async def _read(self, key, fresh=False, max_age=0): return True
    def build_schedules(self): return {"hwc": {d: list(v) for d, v in self.prog.items()}}
    async def async_write_schedule(self, circuit, day, slots, *, internal=False):
        if circuit == "hwc" and not internal and self.presence_suspended_day == day:
            raise EbusdError("pausiert")
        self.prog[day] = list(slots); self.writes.append((day, list(slots)))

class FakeHass:
    def __init__(self, states): self.states = SimpleNamespace(get=lambda e: SimpleNamespace(state=states[e]) if e in states else None)
    def async_create_task(self, c): return asyncio.ensure_future(c)

P = [("05:10", "11:00"), ("12:00", "21:30")]
def make(states, program=P, h=10, m=0, day=11):
    sim = Sim(h, m, day); presence.dt_util.utcnow, presence.dt_util.now = sim.utcnow, sim.now
    stores = {}; presence.Store = lambda hass, v, key, **k: stores.setdefault(key, FakeStore())
    co = FakeCoord(program); mgr = presence.PresenceManager(FakeHass(states), co, list(states))
    return sim, co, mgr, states, stores

async def main():
    away = lambda: {"person.a": "not_home", "person.b": "not_home"}
    # P1: beide weg -> nach Wartezeit pausiert, Rueckkehr stellt alles her
    sim, co, mgr, st, _ = make(away())
    await mgr.async_evaluate(); assert not mgr.suspended, "P1: sofort pausiert"
    sim.adv(10); await mgr.async_evaluate(); assert not mgr.suspended, "P1: vor Ablauf der Wartezeit pausiert"
    sim.adv(11); await mgr.async_evaluate()
    assert mgr.suspended and co.prog["Sunday"] == [] and co.client.cc == "off" and co.presence_suspended_day == "Sunday", "P1: Pause nicht gesetzt"
    assert co.prog["Monday"] == P, "P1: andere Tage duerfen nicht veraendert werden"
    st["person.a"] = "home"; await mgr.async_evaluate()
    assert not mgr.suspended and co.prog["Sunday"] == P and co.client.cc == "auto" and co.presence_suspended_day is None, "P1: Rueckkehr stellt nicht wieder her"
    print("P1 ok: Pause nach Wartezeit, Wiederherstellung bei Rueckkehr")
    # P2: kurz weg -> nichts
    sim, co, mgr, st, _ = make(away()); await mgr.async_evaluate(); sim.adv(10); await mgr.async_evaluate()
    st["person.a"] = "home"; await mgr.async_evaluate(); sim.adv(60); await mgr.async_evaluate()
    assert not mgr.suspended and co.writes == [], "P2 fehlgeschlagen"; print("P2 ok: kurze Abwesenheit loest nichts aus")
    # P3: unbekannt zaehlt als zuhause
    sim, co, mgr, st, _ = make({"person.a": "not_home", "person.b": "unknown"}); await mgr.async_evaluate(); sim.adv(60); await mgr.async_evaluate()
    assert not mgr.suspended, "P3 fehlgeschlagen"; print("P3 ok: 'unknown' wird als zuhause behandelt")
    # P4: ausgeschaltet / ausschalten waehrend Pause
    sim, co, mgr, st, _ = make(away()); co.presence_enabled = False
    await mgr.async_evaluate(); sim.adv(60); await mgr.async_evaluate(); assert not mgr.suspended and co.writes == [], "P4a"
    co.presence_enabled = True; await mgr.async_evaluate(); sim.adv(30); await mgr.async_evaluate(); assert mgr.suspended, "P4b"
    co.presence_enabled = False; await mgr.async_evaluate(); assert not mgr.suspended and co.prog["Sunday"] == P and co.client.cc == "auto", "P4c"
    print("P4 ok: Schalter aus -> keine Pause; Ausschalten waehrend Pause stellt sofort zurueck")
    # P5: Dusch-Wunsch hat Vorrang (Beginn UND Ende der Pause warten)
    sim, co, mgr, st, _ = make(away()); co.shower.active = True
    await mgr.async_evaluate(); sim.adv(30); await mgr.async_evaluate(); assert not mgr.suspended, "P5a: Pause waehrend Dusch-Wunsch begonnen"
    co.shower.active = False; await mgr.async_evaluate(); assert mgr.suspended, "P5b"
    co.shower.active = True; st["person.a"] = "home"; await mgr.async_evaluate(); assert mgr.suspended, "P5c: Wiederherstellung waehrend Dusch-Wunsch"
    co.shower.active = False; await mgr.async_evaluate(); assert not mgr.suspended and co.prog["Sunday"] == P, "P5d"
    print("P5 ok: Dusch-Wunsch hat Vorrang, Wechsel wartet auf sein Ende")
    # P6: Tageswechsel -> altes Programm zurueck, neuer Tag wird neu bewertet
    sim, co, mgr, st, _ = make(away(), h=23, m=0); await mgr.async_evaluate(); sim.adv(25); await mgr.async_evaluate(); assert mgr.suspended
    sim.adv(70)  # 00:10 Montag
    await mgr.async_evaluate(); assert not mgr.suspended and co.prog["Sunday"] == P, "P6: Sonntag nicht zurueckgestellt"
    await mgr.async_evaluate()  # niemand ist zuhause: sofort wieder pausieren, keine neue Wartezeit
    assert mgr.suspended and co.presence_suspended_day == "Monday" and co.prog["Monday"] == [], "P6: Montag nicht pausiert"
    print("P6 ok: Tageswechsel stellt den Vortag zurueck und pausiert den neuen Tag")
    # P7: Schutz gegen Aenderungen waehrend der Pause
    try: await co.async_write_schedule("hwc", "Monday", [("06:00", "07:00")]); raise SystemExit("P7: Schutz fehlt")
    except EbusdError: pass
    await co.async_write_schedule("cc", "Monday", [("06:00", "07:00")]); await co.async_write_schedule("hwc", "Tuesday", [("06:00", "07:00")])
    print("P7 ok: heutige Pufferladung waehrend Pause gesperrt, andere Programme frei")
    # P8: Wiederherstellung schlaegt fehl -> Wiederholung
    sim, co, mgr, st, _ = make(away()); await mgr.async_evaluate(); sim.adv(21); await mgr.async_evaluate(); assert mgr.suspended
    st["person.a"] = "home"; co.client.fail_cc = 1; await mgr.async_evaluate()
    assert mgr.suspended and mgr.state.get("resume_pending"), "P8a: Fehler nicht vorgemerkt"
    await mgr.async_evaluate(); assert not mgr.suspended and co.client.cc == "auto" and co.prog["Sunday"] == P, "P8b: Wiederholung greift nicht"
    print("P8 ok: Fehler beim Wiederherstellen werden wiederholt")
    # P9: Neustart waehrend Pause (Person inzwischen zuhause) -> beim Start wiederhergestellt
    sim, co, mgr, st, stores = make(away()); await mgr.async_evaluate(); sim.adv(21); await mgr.async_evaluate(); assert mgr.suspended
    st2 = {"person.a": "home", "person.b": "not_home"}
    co2 = co; co2.shower = SimpleNamespace(active=False)
    mgr2 = presence.PresenceManager(FakeHass(st2), co2, list(st2)); await mgr2.async_load()
    assert mgr2.suspended and co2.presence_suspended_day == "Sunday", "P9a: Zustand nicht geladen"
    await mgr2.async_evaluate(); assert not mgr2.suspended and co2.prog["Sunday"] == P and co2.client.cc == "auto", "P9b"
    print("P9 ok: Zustand ueberlebt Neustart und wird aufgeraeumt")
    # P10: Programm war schon leer -> kein Schreiben, cc trotzdem pausiert und zurueckgestellt
    sim, co, mgr, st, _ = make(away(), program=[]); await mgr.async_evaluate(); sim.adv(21); await mgr.async_evaluate()
    assert mgr.suspended and co.writes == [] and co.client.cc == "off", "P10a"
    st["person.a"] = "home"; await mgr.async_evaluate(); assert not mgr.suspended and co.client.cc == "auto" and co.writes == [], "P10b"
    print("P10 ok: leeres Programm wird nicht angefasst")
    print("\nALLE ANWESENHEITS-SZENARIEN BESTANDEN")
asyncio.run(main())
