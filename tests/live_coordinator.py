import sys, asyncio, warnings
warnings.simplefilter("ignore")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
from unittest.mock import MagicMock
from homeassistant.core import HomeAssistant
from custom_components.vaillant_ebus.coordinator import VaillantCoordinator
from custom_components.vaillant_ebus.ebusd import EbusdClient
from custom_components.vaillant_ebus import spec

async def main():
    hass = HomeAssistant("/tmp/hacfg_vaillant_ebus_test")
    coord = VaillantCoordinator(hass, None, EbusdClient("192.168.160.136", 8888))
    data = await coord._async_update_data()
    missing = [k for k in spec.ITEMS if data.get(k) is None]
    print("Items gesamt:", len(spec.ITEMS), "| ohne Wert:", missing)
    for k in ["outside_temp","buffer_top","buffer_bottom","season","hwc_mode","circulation_mode","room_target","heating_curve","burner_hours","burner_starts_hc","burner_starts_hwc","parallel_charging","water_pressure"]:
        print(f"  {k:20} {data.get(k)!r}")
    print("Zeitprogramme:", {c: len(v) for c, v in data["schedules"].items()}, "| mc Samstag:", data["schedules"]["mc"].get("Saturday"))
    print("Ferien:", data["holiday_period"])
    # OilUsage-Logik mit echtem Koordinator-Datensatz
    from custom_components.vaillant_ebus.oil import OilUsageSensor
    coord.data = data; coord.nozzle_lph = 2.5
    s = OilUsageSensor(coord, "e", "oil", "x", "burner_hours"); s.hass = hass; s.async_write_ha_state = lambda: None
    s._handle_coordinator_update(); first = s.native_value
    data2 = dict(data); data2["burner_hours"] = data["burner_hours"] + 2; coord.data = data2
    s._handle_coordinator_update(); print("Oel: erst", first, "L -> nach +2 h:", s.native_value, "L (erwartet 5.0)")
asyncio.run(main())
