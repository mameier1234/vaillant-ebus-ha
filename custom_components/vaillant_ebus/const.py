"""Konstanten fuer Vaillant eBUS Control."""

import json
from pathlib import Path

DOMAIN = "vaillant_ebus"

# Version aus der manifest.json, damit sie am Geraet in HA sichtbar ist (Einstellungen -> Geraete -> Firmware)
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))["version"]
REPO_URL = "https://github.com/mameier1234/vaillant-ebus-ha"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_PERSONS = "persons"
DEFAULT_PORT = 8888
TICK_SECONDS = 15  # Koordinator-Takt; einzelne Nachrichten haben eigene Intervalle (spec.py)

EMPTY_SLOT = "-:-"
MAX_SLOTS = 3

SERVICE_SET_SCHEDULE = "set_schedule"
