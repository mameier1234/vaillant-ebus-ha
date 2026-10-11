"""Konstanten fuer Vaillant eBUS Control.

Nachrichten und Felder sind gegen ebusd 23.3 (Vaillant SOLSY/VRC-Regler) verifiziert:
- ``Mode`` (hwc, cc) ist NUR lesbar; geschrieben wird ueber ``SetMode``.
- Zeitfenster: ``Timer.<Wochentag>`` hat 7 Felder (3x von;bis + daysel) und gilt fuer den
  ganzen Block (Mo-Fr / Sa-So / Mo-So), den ``daysel`` benennt.
"""

DOMAIN = "vaillant_ebus"

CONF_HOST = "host"
CONF_PORT = "port"
DEFAULT_PORT = 8888
SCAN_INTERVAL_SECONDS = 60

# ebusd-Zahlcodes <-> Namen
MODE_NAMES = {"disabled", "on", "off", "auto", "eco", "low"}

# Betriebsart (Heizen) bleibt wie in den bisherigen Automationen: mc SetMode auto|off
SEASON_CIRCUIT = "mc"

CIRCUITS_WITH_TIMER = ("hwc", "hc", "mc", "cc")

# Wochentag, ueber den ein Block geschrieben wird
BLOCK_DAY = {"weekdays": "Monday", "weekend": "Saturday"}
BLOCK_DAYSEL = {"weekdays": "Mo-Fr", "weekend": "Sa-So"}

EMPTY_SLOT = "-:-"
MAX_SLOTS = 3

STORAGE_KEY = f"{DOMAIN}.overrides"
STORAGE_VERSION = 1

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_HOT_WATER_OVERRIDE = "hot_water_override"
SERVICE_CANCEL_OVERRIDE = "cancel_hot_water_override"

# Lesezugriffe: Schluessel -> (Kreis, Nachricht, Feldindex)
MODE_READS = {
    "hwc_mode": ("hwc", "Mode", 1),
    "circulation_mode": ("cc", "Mode", 1),
    "season": (SEASON_CIRCUIT, "OperatingMode", 0),
}
# Temperaturen: Schluessel -> (Kreis, Nachricht, Anzeigename). Feld 0 = Wert, Feld 1 = Status
# ("ok"; "cutoff" = Fuehler nicht angeschlossen -> Sensor nicht verfuegbar).
TEMP_READS = {
    "outside_temp": ("hc", "OutsideTemp", "Außentemperatur"),
    "boiler_flow_temp": ("bai", "FlowTemp", "Kessel Vorlauf"),
    "heating_flow_temp": ("hc", "SumFlowSensor", "Heizkreis Vorlauf"),
    "mixer_flow_temp": ("mc", "FlowTemp", "Mischerkreis Vorlauf"),
    "storage_temp": ("hwc", "Storage1Sensor2", "Warmwasserspeicher"),
    "storage_target": ("hwc", "TempDesired2", "Warmwasserspeicher Soll"),
}
