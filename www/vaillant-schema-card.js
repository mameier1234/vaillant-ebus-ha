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
  betrieb: "select.vaillant_heizung_betriebsart",
  dusch: "switch.heating_vaillant_heizung_dusch_wunsch",
  duschStatus: "sensor.heating_vaillant_heizung_dusch_wunsch_status",
};
const OR = "#ff9800", RD = "#ff7043", GR = "#4caf50";

class VaillantSchemaCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this.style.setProperty("--vsc-max", (this._config.max_width || 720) + "px");
    this._bp = this._config.mobile_breakpoint || 560;
    if (!this._ro && typeof ResizeObserver !== "undefined") {
      this._ro = new ResizeObserver(() => {
        const m = this._isMobile();
        if (m !== this._mobile) { this._mobile = m; this._last = null; if (this._hass) this.hass = this._hass; }
      });
      this._ro.observe(this);
    }
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML =
        "<style>:host{display:block}ha-card{padding:8px 12px}#c{max-width:var(--vsc-max,720px);margin:0 auto}svg{width:100%;height:auto;display:block}.hot{cursor:pointer}</style><ha-card><div id='c'></div></ha-card>";
      this.shadowRoot.addEventListener("click", (ev) => {
        const m = ev.target.closest && ev.target.closest("[data-set]");
        if (m) { this._setMode(m.dataset.set); return; }
        if (ev.target.closest && ev.target.closest("[data-shower]")) { this._toggleShower(); return; }
        const t = ev.target.closest && ev.target.closest("[data-entity]");
        if (!t) return;
        this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: t.dataset.entity } }));
      });
    }
  }
  set hass(hass) {
    this._hass = hass;
    if (this._mobile === undefined) this._mobile = this._isMobile();
    const svg = this._mobile ? this._svgMobile() : this._svg();
    if (svg !== this._last) {
      this._last = svg;
      this.shadowRoot.getElementById("c").innerHTML = svg;
    }
  }
  disconnectedCallback() { if (this._ro) { this._ro.disconnect(); this._ro = null; } }
  _isMobile() {
    const l = this._config && this._config.layout;
    if (l === "mobile") return true;
    if (l === "desktop") return false;
    const w = this.getBoundingClientRect().width;
    return w > 0 && w < this._bp;
  }
  _setMode(opt) {
    const st = this._hass && this._hass.states[E.betrieb];
    if (!st || st.state === opt) return;
    const msg = opt === "summer" ? "Heizung auf SOMMER stellen? (Heizung aus, nur Warmwasser)" : "Heizung auf WINTER stellen? (Heizung Automatik)";
    if (!window.confirm(msg)) return;
    this._hass.callService("select", "select_option", { entity_id: E.betrieb, option: opt });
  }
  _pill(x, y, w, h) {
    const st = this._hass.states[E.betrieb];
    const cur = st && st.state;
    const half = w / 2;
    const seg = (i, opt, label, col) => {
      const act = cur === opt;
      return `<rect x='${x + i * half + 2}' y='${y + 2}' width='${half - 4}' height='${h - 4}' rx='${(h - 4) / 2}' fill='${act ? col : "transparent"}'/>`
        + `<text x='${x + i * half + half / 2}' y='${y + h / 2}' class='${act ? "pa" : "pn"}' text-anchor='middle' dominant-baseline='central'>${label}</text>`
        + `<rect class='hot' data-set='${opt}' x='${x + i * half}' y='${y}' width='${half}' height='${h}' fill='transparent'><title>Heizung auf ${label} stellen</title></rect>`;
    };
    const bad = cur !== "winter" && cur !== "summer";
    return `<rect x='${x}' y='${y}' width='${w}' height='${h}' rx='${h / 2}' fill='var(--secondary-background-color)' stroke='var(--divider-color)'/>`
      + seg(0, "winter", "Winter", "#ff7043") + seg(1, "summer", "Sommer", "#ffc107")
      + (bad ? `<text x='${x + w + 8}' y='${y + h / 2}' class='s' dominant-baseline='central'>${cur || "?"}</text>` : "");
  }
  _toggleShower() {
    const sw = this._hass && this._hass.states[E.dusch];
    if (!sw || sw.state === "unavailable") return;
    if (sw.state === "on") {
      if (!window.confirm("Dusch-Wunsch abbrechen? (Zirkulation und Zusatzfenster werden zurückgenommen)")) return;
      this._hass.callService("switch", "turn_off", { entity_id: E.dusch });
    } else {
      this._hass.callService("switch", "turn_on", { entity_id: E.dusch });
    }
  }
  _showerBtn(x, y, w, h) {
    const sw = this._hass.states[E.dusch], ss = this._hass.states[E.duschStatus];
    const on = !!sw && sw.state === "on";
    let label = "Dusch-Wunsch";
    if (on && ss) {
      const a = ss.attributes || {};
      const mins = a.ende ? Math.max(0, Math.ceil((new Date(a.ende) - Date.now()) / 60000)) : null;
      if (ss.state === "aufheizen") label = "Aufheizen" + (a.prognose_min != null ? " ~" + Math.max(1, Math.round(a.prognose_min)) + " min" : (a.puffer_oben != null ? " · " + Number(a.puffer_oben).toFixed(1).replace(".", ",") + " °C" : ""));
      else if (ss.state === "zirkulation") label = "Zirkulation" + (mins !== null ? " · " + mins + " min" : "");
      else label = "Aufräumen …";
    }
    return `<rect x='${x}' y='${y}' width='${w}' height='${h}' rx='${h / 2}' fill='${on ? "#29b6f6" : "var(--secondary-background-color)"}' stroke='var(--divider-color)'/>`
      + `<text x='${x + w / 2}' y='${y + h / 2}' class='${on ? "pa" : "pb"}' text-anchor='middle' dominant-baseline='central'>${label}</text>`
      + `<rect class='hot' data-shower='1' x='${x}' y='${y}' width='${w}' height='${h}' fill='transparent'><title>${on ? "Dusch-Wunsch läuft – antippen zum Abbrechen" : "Dusch-Wunsch starten: Puffer aufheizen, Zirkulation an"}</title></rect>`;
  }
  getCardSize() { return 9; }
  static getStubConfig() { return {}; }

  _ctx() {
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

    return { N, F, I, ON, RUN, C, P, S, pS, pW, br, hp, lp, zp, mx, tank, hot, dot, box, tx };
  }

  _svg() {
    const { N, F, I, ON, RUN, C, P, S, pS, pW, br, hp, lp, zp, mx, tank, hot, dot, box, tx } = this._ctx();
    const zone = (y, ent, l) => { const t = N(ent); return `<rect x='290' y='${y}' width='110' height='80' fill='${C(t)}' stroke='var(--divider-color)'/>` + tx(345, y + 30, F(t) + " °C", "z") + tx(345, y + 52, l, "zs") + hot(290, y, 110, 80, ent); };

    return `<svg viewBox='0 0 680 556' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Heizungsschema'>
<style>text{font-family:var(--primary-font-family,Roboto,sans-serif)}.t{font-size:14px;font-weight:500;fill:var(--primary-text-color)}.s{font-size:12px;fill:var(--secondary-text-color)}.z{font-size:14px;font-weight:500;fill:#1b1b1b}.zs{font-size:12px;fill:#1b1b1b}.pa{font-size:13px;font-weight:500;fill:#1b1b1b}.pn{font-size:13px;fill:var(--secondary-text-color)}.pb{font-size:13px;font-weight:500;fill:var(--primary-text-color)}.flow{stroke-dasharray:6 6;animation:fl 1s linear infinite}@keyframes fl{to{stroke-dashoffset:-12}}@media (prefers-reduced-motion:reduce){.flow{animation:none}}</style>
${this._pill(50, 4, 190, 28)}<text x='252' y='18' class='s' dominant-baseline='central'>Betriebsart Heizung</text>
${this._showerBtn(450, 4, 190, 28)}
<g transform='translate(0,36)'>
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
</g>
</svg>`;
  }
  _svgMobile() {
    const { N, F, I, C, P, S, pS, pW, br, hp, lp, zp, mx, tank, hot, dot, box, tx } = this._ctx();
    const zone = (y, ent, l) => { const t = N(ent); return `<rect x='10' y='${y}' width='130' height='60' fill='${C(t)}' stroke='var(--divider-color)'/>` + tx(75, y + 22, F(t) + " °C", "z") + tx(75, y + 42, l, "zs") + hot(10, y, 130, 60, ent); };
    return `<svg viewBox='0 0 360 609' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='Heizungsschema'>
<style>text{font-family:var(--primary-font-family,Roboto,sans-serif)}.t{font-size:14px;font-weight:500;fill:var(--primary-text-color)}.s{font-size:12px;fill:var(--secondary-text-color)}.z{font-size:14px;font-weight:500;fill:#1b1b1b}.zs{font-size:12px;fill:#1b1b1b}.pa{font-size:13px;font-weight:500;fill:#1b1b1b}.pn{font-size:13px;fill:var(--secondary-text-color)}.pb{font-size:13px;font-weight:500;fill:var(--primary-text-color)}.flow{stroke-dasharray:6 6;animation:fl 1s linear infinite}@keyframes fl{to{stroke-dashoffset:-12}}@media (prefers-reduced-motion:reduce){.flow{animation:none}}</style>
${this._pill(10, 6, 170, 30)}${this._showerBtn(190, 6, 160, 30)}
<g transform='translate(0,46)'>
<g fill='none'>
<line x1='95' y1='54' x2='95' y2='74' ${P(pS, OR)}/>
<line x1='95' y1='118' x2='95' y2='150' ${P(pW, OR)}/>
<line x1='140' y1='175' x2='160' y2='175' stroke='#888' stroke-width='1.5' opacity='.55'/>
<line x1='140' y1='255' x2='160' y2='255' ${P(hp, RD)}/>
<line x1='255' y1='310' x2='255' y2='295' ${P(hp, RD)}/>
<line x1='160' y1='398' x2='140' y2='398' ${P(lp, RD)}/>
<line x1='255' y1='370' x2='255' y2='380' ${P(lp, RD)}/>
</g>
${box(10, 10, 170, 44)}${tx(95, 26, "Kollektor", "t")}${tx(95, 44, F(N(E.kollektor)) + " °C · " + I(N(E.einstrahlung)) + " W/m²", "s")}${hot(10, 10, 170, 44, E.kollektor)}
${box(190, 10, 160, 44)}${tx(270, 26, "Solarkreis", "t")}${tx(270, 44, "V " + F(N(E.vlSolar)) + " · R " + F(N(E.rlSolar)), "s")}${dot(204, 26, 5, pS)}${hot(190, 10, 160, 44, E.pumpeSolar)}
${box(10, 74, 170, 44)}${tx(95, 90, "Wärmetauscher", "t")}${tx(95, 108, "V " + F(N(E.vlWT)) + " · R " + F(N(E.rlWT)), "s")}${hot(10, 74, 170, 44, E.vlWT)}
${box(190, 74, 160, 44)}${tx(270, 90, "WT-Pumpe", "t")}${tx(270, 108, pW ? "läuft" : "aus", "s")}${dot(204, 90, 5, pW)}${hot(190, 74, 160, 44, E.pumpeWT)}
${zone(150, E.pufferOben, "Oben (Fühler 1)")}${zone(210, E.pufferMitte, "Mitte (Resol)")}${zone(270, E.puffer4, "Fühler 4")}${zone(330, E.pufferUnten, "Unten (Fühler 2)")}
<rect x='10' y='150' width='130' height='240' rx='6' fill='none' stroke='var(--primary-text-color)' stroke-width='1' opacity='.5'/>
${box(160, 150, 190, 50)}${tx(255, 166, "Frischwasser", "t")}${tx(255, 184, "Zirkulation " + (zp ? "läuft" : "aus"), "s")}${dot(176, 166, 5, zp)}${hot(160, 150, 190, 50, E.zirk)}
${box(160, 215, 190, 80)}${tx(255, 231, "Heizkreis", "t")}${tx(255, 249, "Vorlauf " + F(N(E.hkVL)) + " · Soll " + F(N(E.hkSoll), 0), "s")}${dot(176, 267, 5, hp)}<text x='188' y='271' class='s'>Pumpe ${hp ? "an" : "aus"}</text><text x='262' y='271' class='s'>Mischer ${mx}</text>${hot(160, 215, 190, 80, E.hkVL)}
${box(160, 310, 190, 60, br ? "rgba(255,112,67,.28)" : null)}${tx(255, 328, "Kessel", "t")}${tx(255, 348, F(N(E.kesselVL)) + " °C · Brenner " + (br ? "läuft" : "aus"), "s")}${br ? `<path d='M330 366 Q324 356 330 346 Q332 354 337 356 Q340 350 336 344 Q348 352 343 366 Z' fill='${OR}'/>` : ""}${hot(160, 310, 190, 60, E.brenner)}
${box(160, 380, 190, 36)}${tx(255, 398, "Ladepumpe " + (lp ? "läuft" : "aus"), "s")}${dot(176, 398, 5, lp)}${hot(160, 380, 190, 36, E.ladePumpe)}
${box(10, 436, 170, 46)}${tx(95, 452, "Wasserdruck", "s")}${tx(95, 470, F(N(E.druck), 2) + " bar", "t")}${hot(10, 436, 170, 46, E.druck)}
${box(190, 436, 160, 46)}${tx(270, 452, "Außen", "s")}${tx(270, 470, F(N(E.aussen)) + " °C", "t")}${hot(190, 436, 160, 46, E.aussen)}
${box(10, 490, 170, 46)}${tx(95, 506, "Heizöl-Tank", "s")}${tx(95, 524, I(tank) + " L · " + (tank === null ? "–" : Math.round(tank / 100)) + " %", "t")}${hot(10, 490, 170, 46, E.tank)}
${box(190, 490, 160, 46)}${tx(270, 506, "Brenner Heizen", "s")}${tx(270, 524, I(N(E.brennerH)) + " h · " + I(N(E.brennerS)) + " St.", "t")}${hot(190, 490, 160, 46, E.brennerH)}
<text x='10' y='555' class='s'>Grün: Pumpe läuft · Puffer: blau kühl bis rot warm</text>
</g>
</svg>`;
  }
}
customElements.define("vaillant-schema-card", VaillantSchemaCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "vaillant-schema-card", name: "Vaillant Heizungsschema", description: "Live-Schema von Solar, Puffer, Kessel und Heizkreis" });
