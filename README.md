# PSE&G Energy (New Jersey) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprax/ha-pseg)](https://github.com/sidprax/ha-pseg/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for **Public Service Electric and Gas (PSE&G)** customers in New Jersey. Automatically retrieves your daily electric meter readings, costs, and historical energy trends directly from the PSE&G MySmartEnergy portal (MyMeter platform).

Includes an ultra-compact, custom **PSEG Energy Card** with interactive 7-day vs 14-day toggles, energy/cost switching, and seamless Home Assistant Energy Dashboard compatibility.

---

## ✨ Features

- 🔐 **Multi-Step Guided Setup**:
  - **Automated Sign-In (Recommended)**: Enter your PSE&G online credentials; if challenged by Okta, enter your 6-digit SMS or Email verification code in the modal.
  - **Browser Session Cookie**: Direct cookie authentication for users who prefer manual token provisioning.
- ⚡ **Accurate Daily Readings**: Fetches official smart meter readings (`sensor.pseg_electricity_consumption`) matching the portal down to the decimal point.
- 💵 **Cost Tracking**: Captures daily electric costs (`sensor.pseg_electricity_cost`) in USD.
- 🌡️ **Weather Integration**: Automatically extracts outdoor temperature ranges (`sensor.pseg_outdoor_temperature`) recorded alongside meter readings.
- 📊 **14-Day History Attributes**: Provides 14-day energy & cost history within entity state attributes for high-speed local charting.
- 🎨 **Built-In Ultra-Minimal Card**: Includes the `pseg-energy-card` which automatically registers in the Lovelace card picker (`Add Card` -> `PSEG Energy Card`).

---

## 📦 Installation via HACS

1. Open **Home Assistant** and navigate to **HACS** > **Integrations**.
2. Click the three dots (top right) and select **Custom repositories**.
3. Paste the repository URL:
   ```text
   https://github.com/sidprax/ha-pseg
   ```
4. Set the Category to **Integration** and click **Add**.
5. Find **PSE&G Energy (New Jersey)**, click **Download**, and restart Home Assistant.

---

## ⚙️ Configuration (Guided UI)

1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **PSE&G Energy (New Jersey)**.
3. Select your preferred setup method:
   - **Automated Sign-In**: Enter Username, Password, and MFA delivery method (SMS or Email). If Okta requests 2FA, enter the 6-digit code when prompted.
   - **Browser Session Cookie**: Paste your active session cookie from `mysmartenergy.nj.pseg.com`.
4. Click **Submit**. Your smart meter sensors and 14-day history are ready!

---

## 📊 Custom Lovelace Card

The integration bundles `pseg-energy-card.js`. It automatically registers in your Lovelace card picker.

### Basic Card Configuration (Zero-Config)

For most users, simply specify the entity. The card automatically derives your electric rate from actual meter readings and opens the standard Home Assistant entity dialog on tap:

```yaml
type: custom:pseg-energy-card
entity: sensor.pseg_electricity_consumption
```

### Advanced Card Configuration (Custom Popups & Baselines)

```yaml
type: custom:pseg-energy-card
entity: sensor.pseg_electricity_consumption
cost_per_kwh: 0.22                 # Optional: Override auto-calculated rate ($/kWh)
cycle_days: 30                     # Optional: Billing cycle length in days (default: 30)
last_cycle_kwh: 168.0              # Optional: Compare projection against prior bill total
show_next_update: true             # Optional: Render next scheduled pull time beside meter label
popup_hash: "#pseg_energy_popup"   # Optional: Navigate to custom Bubble Card / browser popup (defaults to native HA more-info)
```

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| `entity` | string | `sensor.pseg_electricity_consumption` | Primary entity providing daily kWh and `history_14d` |
| `cost_per_kwh` | number | *Auto-calculated* | Optional manual rate override ($/kWh). If omitted, automatically derived from actual meter readings. |
| `cycle_days` | number | `30` | Billing cycle duration in days for monthly usage projections |
| `last_cycle_kwh` | number | *None* | Optional previous cycle total (kWh) to display a ±% comparison badge |
| `toggle_entity` | string | `input_boolean.pseg_display_dollars` | Optional toggle helper for kWh vs $ switching |
| `range_toggle_entity` | string | `input_boolean.pseg_chart_14d` | Optional toggle helper for 7d vs 14d chart switching |
| `next_update_entity` | string | `sensor.pseg_next_update` | Entity providing next scheduled data pull timestamp |
| `show_next_update` | boolean | `false` | When true, renders next pull time beside meter label |
| `popup_hash` | string | *None* | Optional popup hash (e.g. `#pseg_energy_popup`). If omitted, opens native Home Assistant more-info modal. |

---

## 🛠️ Requirements & Host Dependencies

To support automated session refreshes through PSE&G's Okta identity engine without storing browser binaries in the integration package, ensure the host system has standard Chromium installed:

- **Alpine Linux / Home Assistant Terminal**:
  ```bash
  apk add chromium chromium-chromedriver ffmpeg
  ```
- **Debian / Ubuntu**:
  ```bash
  apt-get install chromium-browser chromium-chromedriver ffmpeg
  ```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
