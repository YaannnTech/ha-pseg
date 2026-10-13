# PSE&G Energy (New Jersey) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprak/ha-pseg)](https://github.com/sidprak/ha-pseg/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for **Public Service Electric and Gas (PSE&G)** customers in New Jersey. Automatically retrieves your daily electric meter readings, costs, and historical energy trends directly from the PSE&G MySmartEnergy portal (MyMeter platform).

Includes an ultra-compact, custom **PSEG Energy Card** with interactive 7-day vs 14-day toggles, energy/cost switching, and seamless Home Assistant Energy Dashboard compatibility.

---

## ✨ Features

- 🔐 **Guided Setup with 2FA / MFA Support**: Enter your standard PSE&G credentials via the Home Assistant UI; receive your 6-digit SMS or Email code and verify directly in the setup modal without manual cookie extraction.
- ⚡ **Accurate Daily Readings**: Fetches official smart meter readings (`sensor.pseg_electricity_yesterday`) matching the portal down to the decimal point.
- 💵 **Cost Tracking**: Captures daily electric costs (`sensor.pseg_electricity_cost_yesterday`) in USD.
- 🌡️ **Weather Integration**: Automatically extracts outdoor temperature ranges (daily min, max, avg) recorded alongside meter readings.
- 📊 **14-Day History Attributes**: Provides 14-day energy & cost history within entity state attributes for high-speed local charting.
- 🎨 **Built-In Ultra-Minimal Card**: Includes the `pseg-energy-card` which automatically registers in the Lovelace card picker (`Add Card` -> `PSEG Energy Card`).

---

## 📦 Installation via HACS

1. Open **Home Assistant** and navigate to **HACS** > **Integrations**.
2. Click the three dots (top right) and select **Custom repositories**.
3. Paste the repository URL:
   ```text
   https://github.com/sidprak/ha-pseg
   ```
4. Set the Category to **Integration** and click **Add**.
5. Find **PSE&G Energy (New Jersey)**, click **Download**, and restart Home Assistant.

---

## ⚙️ Configuration (Guided UI)

1. Go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **PSE&G Energy (New Jersey)**.
3. Enter your PSE&G **Username** and **Password**, and select your preferred verification method (**SMS** or **Email**).
4. When prompted, enter the **6-digit verification code** sent to your phone or email.
5. Click **Submit**. Your smart meter sensor and history are now configured!

---

## 📊 Custom Lovelace Card

The integration bundles `pseg-energy-card.js`. It automatically registers in your Lovelace card picker.

### Example Card Configuration

```yaml
type: custom:pseg-energy-card
entity: sensor.pseg_electricity_yesterday
cost_entity: sensor.pseg_electricity_cost_yesterday
```

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| `entity` | string | `sensor.pseg_electricity_yesterday` | Entity providing daily kWh and `history_14d` |
| `cost_entity` | string | `sensor.pseg_electricity_cost_yesterday` | Optional entity providing yesterday's cost in USD |
| `display_dollars` | boolean | `false` | When true, renders bars in dollars ($) instead of kWh |
| `chart_14d` | boolean | `true` | When true, displays 14 days of history; false displays 7 days |

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
