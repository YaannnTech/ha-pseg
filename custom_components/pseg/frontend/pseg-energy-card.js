/**
 * PSEG Energy Card - Ultra-Minimal Galleria Edition
 *
 * Requirements & Features:
 * - 2 Rows total (tight gap, perfectly aligned header):
 *   - Row 1: Left meta (As of MM/DD, Meter ...XXXX) + Right horizontal mini stat items (Latest with ↑/↓ % pill, Avg, Proj with vs last cycle %, Rate)
 *   - Row 2: Compact bar chart (7d or 14d governed by separator toggle `input_boolean.pseg_chart_14d` or config `days`)
 * - Color-coded bars relative to average:
 *   - Green to Amber scheme (no harsh red):
 *     - Below avg (< -5%): Soft emerald green
 *     - At/near avg (within ±5%): Amber-yellow
 *     - Above avg (> +5%): Warm amber/orange
 * - Continuous daily timeline: detects and fills missing calendar dates (e.g. 10/10) with 0 / N/A dotted slot so all dates are represented.
 * - Bar spacing reduced: bars take wider width (up to 28px max-width) with small 3px gaps.
 * - Values inside (<10: 1 decimal, >=10: rounded); when in dollar mode, bars display numbers without '$' sign.
 * - Projection shows vs last cycle diff badge (e.g. +5% or -5%).
 * - Perfectly aligned mini stat items: fixed height labels, baseline-aligned values.
 * - Tapping anywhere opens detailed popup (`#pseg_energy_popup`).
 */

class PsegEnergyCard extends HTMLElement {
  static getStubConfig() {
    return {
      entity: "sensor.pseg_electricity_yesterday",
      cost_per_kwh: 0.22,
      cycle_days: 30,
      days: 14,
      last_cycle_kwh: 168.0,
      toggle_entity: "input_boolean.pseg_display_dollars",
      range_toggle_entity: "input_boolean.pseg_chart_14d",
      popup_hash: "#pseg_energy_popup"
    };
  }

  constructor() {
    super();
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("PSEG Energy Card: Please specify an entity");
    }
    this.config = {
      cost_per_kwh: 0.22,
      cycle_days: 30,
      days: 14,
      last_cycle_kwh: 168.0,
      toggle_entity: "input_boolean.pseg_display_dollars",
      range_toggle_entity: "input_boolean.pseg_chart_14d",
      popup_hash: "#pseg_energy_popup",
      ...config
    };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    if (this._hass) {
      this.render();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this.config) {
      this.render();
    }
  }

  getCardSize() {
    return 2;
  }

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      max_columns: 12,
    };
  }

  openPopup() {
    if (this.config.popup_hash) {
      window.location.hash = this.config.popup_hash;
    } else {
      const event = new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId: this.config.entity }
      });
      this.dispatchEvent(event);
    }
  }

  // Format value for bar labels (never show $ sign in bars)
  formatBarVal(kwh, isDollars, rate) {
    if (isDollars) {
      const d = kwh * rate;
      return d < 10 ? d.toFixed(1) : `${Math.round(d)}`;
    }
    return kwh < 10 ? kwh.toFixed(1) : `${Math.round(kwh)}`;
  }

  // Format value for header stats (clean numbers only, unit is indicated in the column label)
  formatPrecision(kwh, isDollars, rate) {
    if (isDollars) {
      const d = kwh * rate;
      return d.toFixed(2);
    }
    return kwh.toFixed(2);
  }

  // Green to Amber gradient (smooth transition without aggressive red)
  getBarColor(kwh, avgKwh) {
    if (!avgKwh || avgKwh <= 0) {
      return "linear-gradient(180deg, rgba(16, 185, 129, 0.95) 0%, rgba(16, 185, 129, 0.50) 100%)";
    }
    const ratio = kwh / avgKwh;
    if (ratio < 0.95) {
      // Below avg -> Emerald Green
      return "linear-gradient(180deg, rgba(16, 185, 129, 0.95) 0%, rgba(16, 185, 129, 0.45) 100%)";
    } else if (ratio <= 1.12) {
      // Near avg -> Warm Yellow / Amber
      return "linear-gradient(180deg, rgba(234, 179, 8, 0.95) 0%, rgba(234, 179, 8, 0.50) 100%)";
    } else {
      // Higher than avg -> Warm Amber / Orange (soft amber, not red)
      return "linear-gradient(180deg, rgba(245, 158, 11, 0.95) 0%, rgba(217, 119, 6, 0.55) 100%)";
    }
  }

  render() {
    if (!this.shadowRoot || !this._hass || !this.config) return;

    let entity = this._hass.states[this.config.entity];
    if (!entity) {
      entity = this._hass.states["sensor.pseg_electricity_yesterday"] || 
               this._hass.states["sensor.pseg_smart_energy_meter_electricity_yesterday"];
    }
    if (!entity) {
      this.shadowRoot.innerHTML = `
        <ha-card style="background: rgba(25, 25, 25, 0.4); backdrop-filter: blur(10px); padding: 12px; border-radius: 18px; color: #ff6b6b; border: 1px solid rgba(255,255,255,0.08);">
          Entity not found: ${this.config.entity}
        </ha-card>
      `;
      return;
    }

    const toggleEnt = this.config.toggle_entity || "input_boolean.pseg_display_dollars";
    const isDollars = this._hass.states[toggleEnt]?.state === "on";

    const rangeToggleEnt = this.config.range_toggle_entity || "input_boolean.pseg_chart_14d";
    let daysToShow = parseInt(this.config.days) || 14;
    if (this._hass.states[rangeToggleEnt]) {
      daysToShow = this._hass.states[rangeToggleEnt].state === "on" ? 14 : 7;
    }

    const rate = parseFloat(this.config.cost_per_kwh) || 0.22;
    const cycleDays = parseInt(this.config.cycle_days) || 30;
    const lastCycleKwh = parseFloat(this.config.last_cycle_kwh) || 168.0;

    const rawHistory = entity.attributes.history_14d || [];
    const latestRawDate = entity.attributes.latest_date || "";
    const meterRaw = entity.attributes.meter || "";

    // Extract Meter last 4 digits
    const meterNumMatch = meterRaw.match(/\d+/);
    const fullMeterNum = meterNumMatch ? meterNumMatch[0] : "";
    const meterLast4 = fullMeterNum.length >= 4 ? fullMeterNum.slice(-4) : fullMeterNum;
    const meterText = meterLast4 ? `Meter ...${meterLast4}` : "Electric";

    // Reconstruct calendar sequence to avoid missing dates (e.g. 10/10)
    const historyMap = new Map();
    rawHistory.forEach(item => {
      if (item && item.date) {
        historyMap.set(item.date, parseFloat(item.kwh) || 0);
      }
    });

    // Reference end date
    let endDate = latestRawDate;
    if (!endDate && rawHistory.length > 0) {
      endDate = rawHistory[rawHistory.length - 1].date;
    }
    if (!endDate) {
      endDate = new Date().toISOString().slice(0, 10);
    }

    const endDt = new Date(endDate + "T12:00:00Z");
    const activeData = [];
    for (let i = daysToShow - 1; i >= 0; i--) {
      const cur = new Date(endDt.getTime() - i * 86400000);
      const iso = cur.toISOString().slice(0, 10);
      const val = historyMap.has(iso) ? historyMap.get(iso) : null;
      activeData.push({
        date: iso,
        kwh: val,
        isMissing: val === null
      });
    }

    // Format As of MM/DD header date
    let asOfDateStr = latestRawDate;
    const lParts = latestRawDate.split("-");
    if (lParts.length === 3) {
      asOfDateStr = `${lParts[1]}/${lParts[2]}`;
    }

    // Calculate Average over valid points
    const validPoints = activeData.filter(d => !d.isMissing);
    const count = validPoints.length || 1;
    const avgKwh = validPoints.reduce((acc, c) => acc + (c.kwh || 0), 0) / count;

    // Latest day data
    const lastValidPoint = validPoints[validPoints.length - 1] || { kwh: parseFloat(entity.state) || 0 };
    const latestKwh = parseFloat(lastValidPoint.kwh) || 0;

    // Latest vs Average Diff %
    const diffPct = avgKwh > 0 ? ((latestKwh - avgKwh) / avgKwh) * 100 : 0;
    const isHigher = diffPct > 0;
    const absDiff = Math.abs(diffPct).toFixed(0);
    const arrowSymbol = isHigher ? "↑" : "↓";
    const pillClass = isHigher ? "pill-amber" : "pill-green";

    // Cycle Projection & comparison vs last cycle
    const projKwh = avgKwh * cycleDays;
    const projDiffPct = lastCycleKwh > 0 ? ((projKwh - lastCycleKwh) / lastCycleKwh) * 100 : 0;
    const isProjHigher = projDiffPct > 0;
    const absProjDiff = Math.abs(projDiffPct).toFixed(0);
    const projArrowSymbol = isProjHigher ? "↑" : "↓";
    const projPillClass = isProjHigher ? "pill-amber" : "pill-green";

    // Single-unit string representations for header mini stats
    const latestDisplay = this.formatPrecision(latestKwh, isDollars, rate);
    const avgDisplay = this.formatPrecision(avgKwh, isDollars, rate);
    const projDisplay = isDollars
      ? `${Math.round(projKwh * rate)}`
      : `${Math.round(projKwh)}`;
    const unitLabel = isDollars ? "$" : "kWh";
    const rateDisplay = rate.toFixed(2);

    // Build bars with reduced gap and wider fill
    const maxKwh = Math.max(...validPoints.map(d => d.kwh || 0), 6);
    const barsHtml = activeData.map((item, idx) => {
      const kwh = item.kwh !== null ? item.kwh : 0;
      const heightPct = item.isMissing ? 4 : Math.min(Math.max((kwh / maxKwh) * 100, 16), 100);
      const isLatest = idx === activeData.length - 1 && !item.isMissing;
      const barValText = item.isMissing ? "-" : this.formatBarVal(kwh, isDollars, rate);
      const barBg = item.isMissing ? "rgba(255, 255, 255, 0.12)" : this.getBarColor(kwh, avgKwh);

      // Compact date (M/D)
      const dParts = item.date.split("-");
      const dateText = dParts.length === 3 ? `${parseInt(dParts[1])}/${parseInt(dParts[2])}` : item.date;
      const fitsInside = heightPct >= 32;

      return `
        <div class="bar-col ${isLatest ? 'is-latest' : ''} ${item.isMissing ? 'is-missing' : ''}" title="${item.date}: ${item.isMissing ? 'No Data' : kwh + ' kWh'}">
          <div class="bar-track">
            <div class="bar-fill" style="height: ${heightPct}%; background: ${barBg};">
              ${!item.isMissing && fitsInside ? `<span class="val-inside">${barValText}</span>` : ""}
            </div>
            ${!item.isMissing && !fitsInside ? `<span class="val-above" style="bottom: ${heightPct + 2}%;">${barValText}</span>` : ""}
          </div>
          <span class="bar-date">${dateText}</span>
        </div>
      `;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          font-family: var(--primary-font-family, 'Montserrat', sans-serif);
        }
        ha-card {
          position: relative;
          background: rgba(25, 25, 25, 0.40) !important;
          backdrop-filter: blur(10px) !important;
          -webkit-backdrop-filter: blur(10px) !important;
          border-radius: 18px !important;
          border: 1px solid rgba(255, 255, 255, 0.08) !important;
          box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.25) !important;
          padding: 10px 14px 8px;
          color: #ffffff;
          overflow: hidden;
          box-sizing: border-box;
          cursor: pointer;
          transition: transform 0.15s ease, border-color 0.15s ease;
        }
        ha-card:hover {
          border-color: rgba(255, 255, 255, 0.16) !important;
        }
        ha-card:active {
          transform: scale(0.995);
        }

        /* ROW 1: TOP ROW (Left Meta + Right Single-Line Mini Stats) */
        .top-row {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          gap: 10px;
          margin-bottom: 2px;
          padding-bottom: 0px;
        }

        /* Left Meta */
        .meta-col {
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          flex-shrink: 0;
          padding-bottom: 1px;
        }
        .meta-date {
          font-size: 13.5px;
          font-weight: 700;
          color: #ffffff;
          letter-spacing: -0.2px;
          line-height: 1.15;
          white-space: nowrap;
        }
        .meta-meter {
          font-size: 11px;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.50);
          letter-spacing: 0.1px;
          margin-top: 2px;
          line-height: 1.1;
          white-space: nowrap;
        }

        /* Right Metrics Strip */
        .metrics-inline {
          display: flex;
          align-items: flex-end;
          gap: 12px;
          overflow-x: auto;
          scrollbar-width: none;
        }
        .metrics-inline::-webkit-scrollbar {
          display: none;
        }

        .stat-item {
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          justify-content: flex-end;
        }
        .stat-label {
          font-size: 9px;
          font-weight: 600;
          text-transform: uppercase;
          color: rgba(255, 255, 255, 0.45);
          letter-spacing: 0.35px;
          line-height: 1;
          margin-bottom: 4px;
          white-space: nowrap;
          height: 9px;
        }
        .stat-val-row {
          display: flex;
          align-items: center;
          gap: 3px;
          height: 18px;
        }
        .stat-val {
          font-size: 13px;
          font-weight: 700;
          color: #ffffff;
          letter-spacing: -0.2px;
          line-height: 1;
        }

        /* Pill Badges for Higher/Lower */
        .diff-pill {
          display: inline-flex;
          align-items: center;
          gap: 1px;
          padding: 1px 4px;
          border-radius: 9px;
          font-size: 9.5px;
          font-weight: 700;
          line-height: 1.15;
        }
        .pill-green {
          background: rgba(16, 185, 129, 0.18);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.35);
        }
        .pill-amber {
          background: rgba(245, 158, 11, 0.18);
          color: #fbbf24;
          border: 1px solid rgba(245, 158, 11, 0.35);
        }

        /* ROW 2: COMPACT BAR CHART */
        .chart-row {
          display: flex;
          align-items: flex-end;
          gap: 3px;
          height: 62px;
          padding-top: 10px;
          box-sizing: border-box;
        }
        .bar-col {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          height: 100%;
          min-width: 0;
          position: relative;
        }
        .bar-track {
          flex: 1;
          width: 100%;
          position: relative;
          display: flex;
          align-items: flex-end;
          justify-content: center;
        }
        .bar-fill {
          width: 100%;
          max-width: 28px;
          border-radius: 4px 4px 2px 2px;
          position: relative;
          display: flex;
          justify-content: center;
          align-items: flex-start;
          padding-top: 2px;
          box-sizing: border-box;
          transition: height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .bar-col.is-latest .bar-fill {
          outline: 1.5px solid rgba(255, 255, 255, 0.45);
          outline-offset: 1px;
        }
        .bar-col.is-missing .bar-fill {
          border: 1px dashed rgba(255, 255, 255, 0.20);
        }

        .val-inside {
          font-size: 8.5px;
          font-weight: 700;
          color: #ffffff;
          line-height: 1;
          text-shadow: 0 1px 2px rgba(0, 0, 0, 0.8);
          pointer-events: none;
        }
        .val-above {
          position: absolute;
          font-size: 8px;
          font-weight: 700;
          color: rgba(255, 255, 255, 0.75);
          line-height: 1;
          pointer-events: none;
          text-align: center;
          white-space: nowrap;
        }
        .bar-date {
          font-size: 8.5px;
          font-weight: 500;
          color: rgba(255, 255, 255, 0.45);
          margin-top: 3px;
          line-height: 1;
          white-space: nowrap;
        }
        .bar-col.is-latest .bar-date {
          color: #ffffff;
          font-weight: 700;
        }
      </style>

      <ha-card id="cardWrapper" title="Click for details & meter history">
        <!-- Row 1: Left Meta + Right Single-Line Mini Stats -->
        <div class="top-row">
          <div class="meta-col">
            <span class="meta-date">As of ${asOfDateStr}</span>
            <span class="meta-meter">${meterText}</span>
          </div>

          <div class="metrics-inline">
            <!-- Latest + Higher/Lower Arrow Pill -->
            <div class="stat-item">
              <span class="stat-label">Usage (${unitLabel})</span>
              <div class="stat-val-row">
                <span class="stat-val">${latestDisplay}</span>
                <span class="diff-pill ${pillClass}">
                  ${arrowSymbol}${absDiff}%
                </span>
              </div>
            </div>

            <!-- Avg -->
            <div class="stat-item">
              <span class="stat-label">Avg (${daysToShow}d)</span>
              <div class="stat-val-row">
                <span class="stat-val">${avgDisplay}</span>
              </div>
            </div>

            <!-- Projection with vs last cycle diff badge -->
            <div class="stat-item">
              <span class="stat-label">Proj (Cycle)</span>
              <div class="stat-val-row">
                <span class="stat-val">${projDisplay}</span>
                <span class="diff-pill ${projPillClass}" title="${projDiffPct >= 0 ? '+' : ''}${projDiffPct.toFixed(0)}% vs last cycle">
                  ${projArrowSymbol}${absProjDiff}%
                </span>
              </div>
            </div>

            <!-- Rate -->
            <div class="stat-item">
              <span class="stat-label">Rate</span>
              <div class="stat-val-row">
                <span class="stat-val">${rateDisplay}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Row 2: Compact Bar Chart Colored Against Avg -->
        <div class="chart-row">
          ${barsHtml}
        </div>
      </ha-card>
    `;

    // Click handler for popup
    this.shadowRoot.getElementById("cardWrapper")?.addEventListener("click", () => {
      this.openPopup();
    });
  }
}

customElements.define("pseg-energy-card", PsegEnergyCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "pseg-energy-card",
  name: "PSEG Energy Card (Ultra-Minimal)",
  preview: true,
  description: "Ultra-compact minimal Galleria energy card with smooth green-amber bars and single-line metrics."
});
