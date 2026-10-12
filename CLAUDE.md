# Projekt: vaillant_ebus (HA-Integration, HACS) – Übergabe / Arbeitsanweisung

Home-Assistant-Integration für Vaillant auroMATIC VRS 620 / ecoVIT (Öl) über **ebusd per TCP** (Port 8888, Heimnetz).
Der Regler bleibt die Steuerung: HA ändert nur Sollwerte/Modi/Zeitfenster und muss immer alles wiederherstellen können.
Sprache mit dem Nutzer: Deutsch. Zugangsdaten/Token nie ins Repo (HA-MCP-Zugang wird pro Rechner eingerichtet).

## Anlage / ebusd-Kreise
`bai` Kessel, `mc` Heizkreis HK2 (Mischerkreis), `hwc` Pufferladung, `cc` Zirkulation, `hc` HK1 (deaktiviert), `ui`, `sc` (Solar am Regler aus).
Solar läuft separat über Resol DeltaSol E (eigene HA-Integration, Entitäten `sensor.temperature_sensor_*`). Puffer mit Frischwasserstation (zieht oben ab).
ebusd-Host/Port steht in der HA-Integration (Config-Entry) bzw. `tests/live_coordinator.py`.

## ebusd per Kommandozeile (zum Verifizieren)
- Befehle über TCP-Port, **eine Zeile pro Verbindung, kein `quit` mitsenden** (sonst "command not found"/Fehler). Beispiel: `printf 'read -f -c mc Mode\n' | nc -w 6 <host> 8888`. Auf Windows: Python-Socket oder `Test-NetConnection` ist ungeeignet → kleines Python-Skript.
- `read -f -c <kreis> <name>` (-f = frisch vom Bus). `write -c <kreis> <name> <wert>`. `find -c <kreis>` listet Nachrichten.
- **Zurücklesen immer mit dem passenden Register prüfen:** `mc SetMode` ändert `mc Mode` (Feld 1), NICHT `mc OperatingMode` (blieb "auto", Fehler bis 0.12.0).
- Zeiten nur in 10-Minuten-Schritten (Start abwärts, Ende aufwärts runden, `normalize_slot`). `daysel=selected` schreibt nur einen Tag.
- `hwc SetMode on` setzt auch cc und mc auf Dauerbetrieb → gesperrt. `cc SetMode on/off` wirkt isoliert.
- Schreibbefehle gehen durch eine Sicherheits-Regex in `ebusd.py`.

## Code (custom_components/vaillant_ebus)
`spec.py` (Item-Tabelle ITEMS/WRITES, Intervalle FASTEST 15 s/FAST 60 s/SLOW 600 s), `coordinator.py` (Tick 15 s, `async_write`, `async_write_schedule` mit Anwesenheits-Sperre),
`entity.py`, Plattformen `sensor/binary_sensor/number/select/switch/button/text.py`, `schedule_editor.py`, `oil.py` (Brenner-/Ölzähler, sekundengenau),
`shower.py` (Dusch-Wunsch), `presence.py` (Warmwasser-Pause bei Abwesenheit; Personen per Schalter `Anwesenheit zählt: <Person>`),
`mixer.py` (Verdacht "Mischer hängt", Rohrfühler-Spreizung; externe Fühler-Entitäten fest in der Datei), `__init__.py`, `services.yaml`.
Karte: `www/vaillant-schema-card.js` (Shadow-DOM, Inline-SVG, Desktop `_svg()` + Mobil `_svgMobile()`).

## Tests (ohne echtes HA, Python-venv mit `pip install homeassistant pyflakes`)
`tests/presence_logic.py`, `shower_logic.py`, `mixer_logic.py`, `smoke_entities.py`, `live_coordinator.py` (liest echten ebusd).
**Immer zusätzlich `python -m pyflakes custom_components/vaillant_ebus/*.py`** (0.11.0 scheiterte an fehlendem Import; Smoke-Test ruft `async_setup_entry` nicht auf).
Vor einem Release: Syntax + pyflakes + Tests; nach Schreib-Features Schreibtest mit sofortigem Zurücksetzen.

## Release-Ablauf
1. `manifest.json` Version erhöhen (VERSION in `const.py` liest sie; erscheint als `sw_version` am Gerät).
2. `git commit` + `git push`, dann `gh release create vX.Y.Z --title ... --notes ...` (HACS zieht Releases).
3. Nutzer aktualisiert in HACS und startet HA neu (Dashboard-Karte separat, siehe unten).
Test-Setup lokal: HA in venv; kopierte Integration in ein Testverzeichnis (nicht ins produktive HA schreiben).

## Dashboard-Karte hochladen
Datei ist als inline-Dashboard-Ressource in HA registriert (ha-mcp `ha_config_set_dashboard_resource`, `resource_type=module`, Ressourcen-ID in HA nachschlagen
mit `ha_config_list_dashboard_resources`). **Immer die komplette Datei als `content` senden**, danach prüfen, dass die zurückgegebene Größe = `wc -c` ist. Nutzer: hart neu laden.
Karten-Änderungen headless prüfen (Brave/Chrome `--headless --screenshot` mit Mock-`hass`).

## ha-mcp Stolperstellen
`limit` ≤ 1000 bei Suchen; in `python_transform` kein `assert`; große History-Antworten landen in einer Datei (mit python/jq auswerten);
nach HA-Neustart kurz warten (502). Best-practice-Skill beachten.

## Verhalten, das der Nutzer wünscht
- Heizung muss ohne HA funktionieren; HA ändert nur temporär/umkehrbar. Nichts automatisch schalten, wo nur ein Verdacht besteht (Mischer: nur melden).
- Vor riskanten Schreibtests: kurz begründen, danach sofort zurückstellen und zurücklesen.
- Fehler offen zugeben (z. B. defekte Releases kennzeichnen), nicht beschönigen.

## Offene Punkte
- **Zeitprogramme optimieren** (Plan): ab ca. 2026-10-25 Auswertung der Zapfzeiten (Puffer-oben-Abfall, Zirkulation), WW-Brennerstarts, Heizöl → Fenstervorschläge pro Tag; Nutzer entscheidet.
- Mischer HK2 (Oventrop-Antrieb) schwergängig nach der Sommerpause → Techniker; HA meldet Verdacht per `binary_sensor ... mischer_hangt_verdacht`.
- Techniker-Fragen: Taktung des Brenners (Brennersperrzeit/Pumpenstufe/Hysterese), Ladepumpen-Vorlauf vor Brennerstart, Mischer, Heizkurve/Absenkung.
- Optional: automatisches Vorwärmen bei Rückkehr (nicht gebaut), Heizöl-Ansicht auf Brenner-Verbrauch umbauen, Resol-Relais 3/7 ungeklärt, "Heizung pausieren" beim Dusch-Wunsch testen.
