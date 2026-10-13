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

### Example Card Configuration

```yaml
type: custom:pseg-energy-card
entity: sensor.pseg_electricity_consumption
cost_per_kwh: 0.22
cycle_days: 30
last_cycle_kwh: 168.0
popup_hash: "#pseg_energy_popup"
```

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| `entity` | string | `sensor.pseg_electricity_consumption` | Entity providing daily kWh and `history_14d` |
| `cost_per_kwh` | number | `0.22` | Electric rate in $/kWh |
| `cycle_days` | number | `30` | Billing cycle duration in days |
| `last_cycle_kwh` | number | `168.0` | Previous cycle total for projection comparison |
| `toggle_entity` | string | `input_boolean.pseg_display_dollars` | Toggle entity for kWh vs $ display |
| `range_toggle_entity` | string | `input_boolean.pseg_chart_14d` | Toggle entity for 7d vs 14d chart range |
| `popup_hash` | string | `#pseg_energy_popup` | Hash for popup navigation on card tap |

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
