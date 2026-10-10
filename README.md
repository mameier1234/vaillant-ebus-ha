# Vaillant eBUS Control (Home Assistant, HACS)

Steuerung einer Vaillant-Heizung über **ebusd** (direkter TCP-Zugriff auf den Kommandoport, Standard 8888).
Kein MQTT nötig; bestehende MQTT-Sensoren können parallel weiterlaufen.

## Stand 0.2
- `select`: **Betriebsart** (winter = Heizen, summer = nur Warmwasser), **Warmwasser Modus**, **Zirkulation Modus**
- `vaillant_ebus.hot_water_override` – Warmwasser für X Stunden / bis Zeitpunkt auf „an“, danach automatisch zurück auf den vorherigen Modus (persistiert, überlebt HA-Neustart); `cancel_hot_water_override` bricht ab
- `vaillant_ebus.set_schedule` – bis zu 3 Zeitfenster für `hwc`/`hc`/`mc`/`cc`, Block `weekdays` oder `weekend`

## Verifiziert (ebusd 23.3, Vaillant SOLSY/VRC)
- `Mode` ist nur lesbar; geschrieben wird mit `write -c <kreis> SetMode <auto|on|off>` → Antwort `done`
- `Timer.<Tag>` hat 7 Felder: `von;bis;von;bis;von;bis;daysel`; wirkt auf den ganzen Block (Mo-Fr / Sa-So)
- Schreib-/Lesetest an echter Anlage: Zirkulation off → auto, Timer unverändert zurückgeschrieben

## Voraussetzung
ebusd muss den TCP-Port im LAN anbieten (`--address=0.0.0.0` o. ä.). Der Port ist unauthentifiziert – nur im Heimnetz.

## Geplant
Wochenraster-Dashboardkarte, `water_heater`-Entität, Temperatur-Dashboard (nicht angeschlossene Fühler ausblenden), Tests.
