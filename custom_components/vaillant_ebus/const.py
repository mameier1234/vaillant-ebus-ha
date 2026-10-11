"""Konstanten fuer Vaillant eBUS Control."""

DOMAIN = "vaillant_ebus"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_PERSONS = "persons"
DEFAULT_PORT = 8888
TICK_SECONDS = 15  # Koordinator-Takt; einzelne Nachrichten haben eigene Intervalle (spec.py)

EMPTY_SLOT = "-:-"
MAX_SLOTS = 3

SERVICE_SET_SCHEDULE = "set_schedule"
