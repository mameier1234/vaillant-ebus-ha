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
