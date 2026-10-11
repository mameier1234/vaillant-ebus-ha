/* Vaillant Heizungsschema – Live-Karte (Home Assistant Custom Card, ohne Abhaengigkeiten) */
const V = "sensor.heating_vaillant_heizung_";
const B = "binary_sensor.heating_vaillant_heizung_";
const E = {
  kollektor: "sensor.temperature_sensor_1", einstrahlung: "sensor.irradiation_cs",
  vlSolar: "sensor.temperature_sensor_3", rlSolar: "sensor.temperature_sensor_4",
  vlWT: "sensor.temperature_sensor_9", rlWT: "sensor.temperature_sensor_10",
  pumpeSolar: "sensor.pump_speed_relay_1", pumpeWT: "sensor.pump_speed_relay_2",
  pufferOben: V + "puffer_oben", pufferMitte: "sensor.temperature_sensor_2",
  puffer4: V + "puffer_mitte_unten_fuhler_4", pufferUnten: V + "puffer_unten",
  aussen: V + "aussentemperatur", kesselVL: V + "kessel_vorlauf",
  hkVL: V + "mischerkreis_vorlauf", hkSoll: V + "heizkreis_vorlauf_soll",
  druck: V + "wasserdruck_heizung", mischer: V + "mischer",
  brennerH: V + "brennerlaufzeit", brennerS: V + "brennerstarts_heizen",
  brenner: B + "brenner", hkPumpe: B + "heizkreispumpe", ladePumpe: B + "ladepumpe_puffer",
  zirk: B + "zirkulationspumpe", tank: "sensor.heizoel_tanklevel",
};
const OR = "#ff9800", RD = "#ff7043", GR = "#4caf50";

class VaillantSchemaCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this.style.setProperty("--vsc-max", (this._config.max_width || 720) + "px");
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML =
        "<style>:host{display:block}ha-card{padding:8px 12px}#c{max-width:var(--vsc-max,720px);margin:0 auto}svg{width:100%;height:auto;display:block}.hot{cursor:pointer}</style><ha-card><div id='c'></div></ha-card>";
      this.shadowRoot.addEventListener("click", (ev) => {
        const t = ev.target.closest && ev.target.closest("[data-entity]");
        if (!t) return;
        this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: t.dataset.entity } }));
      });
    }
  }
  set hass(hass) {
    this._hass = hass;
    const svg = this._svg();
    if (svg !== this._last) {
      this._last = svg;
      this.shadowRoot.getElementById("c").innerHTML = svg;
    }
  }
  getCardSize() { return 9; }
  static getStubConfig() { return {}; }

  _svg() {
    const st = this._hass.states;
    const S = (i) => st[i] && st[i].state;
    const N = (i) => { const v = parseFloat(S(i)); return isNaN(v) ? null : v; };
    const F = (v, d = 1) => (v === null ? "–" : v.toFixed(d).replace(".", ","));
    const I = (v) => (v === null ? "–" : Math.round(v).toLocaleString("de-DE"));
    const ON = (i) => S(i) === "on";
    const RUN = (i) => { const v = parseFloat(S(i)); return !isNaN(v) && v > 0; };
    const C = (t) => { if (t === null) return "#9e9e9e"; const k = Math.max(0, Math.min(1, (t - 20) / 45)); return `hsl(${215 - k * 205} 65% 62%)`; };
    const P = (a, c) => (a ? `stroke='${c}' stroke-width='3' class='flow'` : "stroke='#888' stroke-width='1.5' opacity='.55'");

    const pS = RUN(E.pumpeSolar), pW = RUN(E.pumpeWT);
    const br = ON(E.brenner), hp = ON(E.hkPumpe), lp = ON(E.ladePumpe), zp = ON(E.zirk);
    const mx = { open: "öffnet", close: "schließt", off: "ruht" }[S(E.mischer)] || "–";
    const tank = N(E.tank);

    const hot = (x, y, w, h, ent) => `<rect class='hot' data-entity='${ent}' x='${x}' y='${y}' width='${w}' height='${h}' fill='transparent'/>`;
    const dot = (x, y, r, on) => `<circle cx='${x}' cy='${y}' r='${r}' fill='${on ? GR : "var(--secondary-background-color)"}' stroke='var(--secondary-text-color)' stroke-width='.6'/>`;
    const box = (x, y, w, h, fill) => `<rect x='${x}' y='${y}' width='${w}' height='${h}' rx='8' fill='${fill || "var(--secondary-background-color)"}' stroke='var(--divider-color)' stroke-width='1'/>`;
    const tx = (x, y, s, c, a) => `<text x='${x}' y='${y}' class='${c}' text-anchor='${a || "middle"}' dominant-baseline='central'>${s}</text>`;
    const zone = (y, ent, l) => { const t = N(ent); return `<rect x='290' y='${y}' width='110' height='80' fill='${C(t)}' stroke='var(--divider-color)'/>` + tx(345, y + 30, F(t) + " °C", "z") + tx(345, y + 52, l, "zs") + hot(290, y, 110, 80, ent); };

    return `<svg viewBox='0 0 680 520' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Heizungsschema'>
<style>text{font-family:var(--primary-font-family,Roboto,sans-serif)}.t{font-size:14px;font-weight:500;fill:var(--primary-text-color)}.s{font-size:12px;fill:var(--secondary-text-color)}.z{font-size:14px;font-weight:500;fill:#1b1b1b}.zs{font-size:12px;fill:#1b1b1b}.flow{stroke-dasharray:6 6;animation:fl 1s linear infinite}@keyframes fl{to{stroke-dashoffset:-12}}@media (prefers-reduced-motion:reduce){.flow{animation:none}}</style>
<g fill='none'>
<line x1='95' y1='150' x2='95' y2='133' ${P(pS, OR)}/><line x1='95' y1='115' x2='95' y2='82' ${P(pS, OR)}/><line x1='155' y1='82' x2='155' y2='150' ${P(pS, OR)}/>
<line x1='200' y1='165' x2='236' y2='165' ${P(pW, OR)}/><line x1='254' y1='165' x2='290' y2='165' ${P(pW, OR)}/><line x1='290' y1='185' x2='200' y2='185' ${P(pW, OR)}/>
<line x1='400' y1='98' x2='448' y2='98' stroke='#888' stroke-width='1.5' opacity='.55'/>
<line x1='400' y1='260' x2='553' y2='260' ${P(hp, RD)}/><line x1='565' y1='249' x2='565' y2='228' ${P(hp, RD)}/><line x1='565' y1='330' x2='565' y2='273' ${P(hp, RD)}/>
<path d='M450 358 L434 358' ${P(lp, RD)}/><path d='M416 358 L402 358' ${P(lp, RD)}/>
</g>
${box(50, 30, 150, 50)}${tx(125, 46, "Kollektor", "t")}${tx(125, 65, F(N(E.kollektor)) + " °C · " + I(N(E.einstrahlung)) + " W/m²", "s")}${hot(50, 30, 150, 50, E.kollektor)}
<text x='80' y='100' class='s' text-anchor='end'>Vorlauf</text><text x='80' y='116' class='s' text-anchor='end'>${F(N(E.vlSolar))} °C</text>
${dot(95, 124, 9, pS)}${tx(130, 128, "Pumpe", "s")}${hot(84, 113, 22, 22, E.pumpeSolar)}
<text x='163' y='100' class='s'>Rücklauf</text><text x='163' y='116' class='s'>${F(N(E.rlSolar))} °C</text>
${box(50, 150, 150, 50)}${tx(125, 175, "Wärmetauscher", "t")}${hot(50, 150, 150, 50, E.vlWT)}
${tx(245, 146, "Vorlauf " + F(N(E.vlWT)), "s")}${dot(245, 165, 9, pW)}${hot(234, 154, 22, 22, E.pumpeWT)}${tx(245, 206, "Rücklauf " + F(N(E.rlWT)), "s")}${tx(245, 224, "WT-Pumpe", "s")}
${tx(345, 46, "Pufferspeicher", "t")}${zone(60, E.pufferOben, "Oben (Fühler 1)")}${zone(140, E.pufferMitte, "Mitte (Resol)")}${zone(220, E.puffer4, "Fühler 4")}${zone(300, E.pufferUnten, "Unten (Fühler 2)")}
<rect x='290' y='60' width='110' height='320' rx='6' fill='none' stroke='var(--primary-text-color)' stroke-width='1' opacity='.5'/>
${box(450, 14, 190, 34)}${tx(545, 31, "Außen " + F(N(E.aussen)) + " °C", "t")}${hot(450, 14, 190, 34, E.aussen)}
${box(450, 70, 190, 56)}${tx(545, 88, "Frischwasser", "t")}${tx(545, 108, "Zirkulation " + (zp ? "läuft" : "aus"), "s")}${dot(470, 108, 5, zp)}${hot(450, 70, 190, 56, E.zirk)}
${box(450, 160, 190, 68)}${tx(545, 177, "Heizkreis", "t")}${tx(545, 195, "Vorlauf " + F(N(E.hkVL)) + " · Soll " + F(N(E.hkSoll), 0), "s")}${dot(500, 213, 5, hp)}<text x='512' y='217' class='s'>Pumpe ${hp ? "an" : "aus"}</text>${hot(450, 160, 190, 68, E.hkVL)}
${dot(565, 261, 12, false)}<text x='585' y='265' class='s'>Mischer ${mx}</text>${hot(553, 249, 24, 24, E.mischer)}
${box(450, 330, 190, 56, br ? "rgba(255,112,67,.28)" : null)}${tx(545, 348, "Kessel", "t")}${tx(545, 368, F(N(E.kesselVL)) + " °C · Brenner " + (br ? "läuft" : "aus"), "s")}${br ? `<path d='M618 380 Q610 368 618 356 Q620 366 626 368 Q630 362 624 354 Q640 364 634 380 Z' fill='${OR}'/>` : ""}${hot(450, 330, 190, 56, E.brenner)}
${dot(425, 358, 9, lp)}${tx(425, 404, "Ladepumpe", "s")}${hot(414, 347, 22, 22, E.ladePumpe)}
${box(40, 430, 190, 48)}${tx(135, 447, "Wasserdruck", "s")}${tx(135, 466, F(N(E.druck), 2) + " bar", "t")}${hot(40, 430, 190, 48, E.druck)}
${box(245, 430, 190, 48)}${tx(340, 447, "Heizöl-Tank", "s")}${tx(340, 466, I(tank) + " L · " + (tank === null ? "–" : Math.round(tank / 100)) + " %", "t")}${hot(245, 430, 190, 48, E.tank)}
${box(450, 430, 190, 48)}${tx(545, 447, "Brenner Heizen", "s")}${tx(545, 466, I(N(E.brennerH)) + " h · " + I(N(E.brennerS)) + " Starts", "t")}${hot(450, 430, 190, 48, E.brennerH)}
<text x='40' y='505' class='s'>Grün: Pumpe läuft · Leitungen animiert bei laufender Pumpe · Puffer: blau kühl bis rot warm · Antippen für den Verlauf</text>
</svg>`;
  }
}
customElements.define("vaillant-schema-card", VaillantSchemaCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "vaillant-schema-card", name: "Vaillant Heizungsschema", description: "Live-Schema von Solar, Puffer, Kessel und Heizkreis" });
