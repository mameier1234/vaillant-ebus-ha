# Vaillant eBUS Control (Home Assistant, HACS)

Bildet die Bedienung eines **Vaillant auroMATIC (VRS 620)** über **ebusd** (direkter TCP-Zugriff, Standardport 8888) in
Home Assistant ab. Kein MQTT nötig. Der Regler im Keller bleibt die Steuerung – ohne HA läuft die Heizung unverändert weiter.

Entwickelt für: Heizkreis HK2 (Mischerkreis, ebusd-Kreis `mc`), HK1 deaktiviert, Pufferspeicher mit Frischwasserstation.
Solar (Resol) ist bewusst nicht enthalten.

## Stand 0.7 (alles aus der Reglerbedienung lesbar, wichtigste Sollwerte und Zeitprogramme schreibbar)
- **Sensoren:** Außentemperatur, Kessel-/Heizkreis-Vorlauf (Ist/Soll), Sammler Vorlauf (VF1), Anlagensollwert, Raumtemperatur (Regler),
  Puffer oben / Mitte unten / unten, Wasserdruck, Mischerstatus
- **Binär:** Brenner, Heizkreispumpe, Ladepumpe, Zirkulationspumpe, Ferienprogramm
- **Zahlen (schreibbar):** Raumsoll Tag, Absenktemperatur, Heizkurve, AT-Abschaltgrenze, Puffer-Soll, Raumsoll Ferien
- **Auswahl:** Betriebsart Heizung (winter/summer), Pufferladung Modus (auto/off), Zirkulation Modus (auto/on/off)
- **Zeitprogramme:** je Kreis (Heizung, Pufferladung, Zirkulation) ein Sensor (Zustand = heute, Attribute = alle Tage), eine Auswahl *Tag* (Heute, Mo–So, Mo–Fr, Sa–So) und drei Felder *Slot 1–3*, die den hinterlegten Wert zeigen (`07:30-22:00` oder `aus`) und editierbar sind. Eingabe wird geprüft, geschrieben und zurückgelesen. Dazu der Dienst `set_schedule`
- **Brenner & Heizöl:** Laufzeit und Starts getrennt für Heizen und Warmwasser (Starts exakt = Hunderter-Zähler + Rest), daraus Heizölverbrauch
  (Δ Stunden × *Brenner Durchsatz*, L/h, Schätzwert – mit Düse/Kesselleistung abgleichen). Die Summen laufen inkrementell, eine spätere
  Änderung des Durchsatzes schreibt die Vergangenheit nicht um.
- **Konfiguration (schreibbar):** Parallele Ladung (Schalter; AUS = Pufferladung hat Vorrang vor der Heizung), Ladepumpen-Nachlauf, Nachladeverzögerung
- **Diagnose (nur lesen):** Pumpensperrzeit, Vorlauf min/max, Vorabschaltung, Frostschutzverzögerung, Temperaturüberhöhung,
  Korrekturwerte, Brennerlaufzeit
- **Ungetestet, standardmäßig deaktiviert:** Switch *Party* (`mc party`), Button *Puffer einmalig laden* (`mc load`)

## Wichtige Erkenntnisse (gegen Display verifiziert)
- Die echten Heizkreis-Parameter liefert `mc Params` (= Display B5/C2); `HeatingCurve`, `TempDesiredLow` u. a. zeigen abweichende Werte.
  Geschrieben wird über `SetTempDesired`, `SetTempDesiredLow`, `SetHeatingCurve`, `SetShutdownTemp` (mc), `SetTempDesired` (hwc).
- `Mode` ist nur lesbar; schreiben über `SetMode`. **`hwc SetMode on` setzt auch Zirkulation und Heizkreis auf Dauerbetrieb** – deshalb
  nicht angeboten. `cc SetMode on` wirkt isoliert.
- Zeitprogramm-Schreiben mit `daysel=selected` ändert nur den einen Tag (Mo–Fr/Sa–So-Blöcke bleiben sonst unberührt).
- Der Regler hat eigene Schnellfunktionen: `mc load` (Quick – WW Speicherladung), `mc party`, `mc save` (Sparen bis).

## Voraussetzung
ebusd muss den TCP-Port im LAN anbieten (`--address=0.0.0.0` o. ä.). Der Port ist unauthentifiziert – nur im Heimnetz.

## Geplant (Stufe 2, Logik)
Dusch-Wunsch (Zirkulation + Pufferladung auf Anforderung), Zeitprogramm-Optimierung nach Anwesenheit, Wochenraster-Karte.

## Tests (lokal, ohne laufendes HA)
```bash
python3 -m venv .venv && .venv/bin/pip install homeassistant
.venv/bin/python tests/smoke_entities.py     # alle Entitäten mit Testdaten instanziieren, Zustände prüfen
.venv/bin/python tests/live_coordinator.py   # Koordinator gegen echten ebusd (nur lesend, IP/Port im Skript)
```

## Dashboard-Karte (optional)
`www/vaillant-schema-card.js` ist eine eigenständige Custom Card (`type: custom:vaillant-schema-card`) mit dem Live-Schema
(Solar/Resol, Puffer, Kessel, Heizkreis, Pumpen). Als Dashboard-Ressource vom Typ *module* registrieren. Die Entitäten-IDs stehen
oben in der Datei (`E = {...}`) und sind auf die Anlage des Entwicklers zugeschnitten. Klick auf einen Teil öffnet den Verlauf.
