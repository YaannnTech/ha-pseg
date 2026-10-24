# PSE&G Energy (New Jersey) for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprax/ha-pseg)](https://github.com/sidprax/ha-pseg/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Validate with hassfest](https://github.com/sidprax/ha-pseg/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/sidprax/ha-pseg/actions/workflows/hassfest.yaml)
[![HACS Action](https://github.com/sidprax/ha-pseg/actions/workflows/hacs.yaml/badge.svg)](https://github.com/sidprax/ha-pseg/actions/workflows/hacs.yaml)

Home Assistant integration for Public Service Electric and Gas (PSE&G) customers in New Jersey. Retrieves daily electric meter readings, costs, and historical energy trends directly from the PSE&G MySmartEnergy portal (MyMeter).

Includes a built-in Lovelace card with 7-day and 14-day history views and kWh / cost switching.

![PSEG Energy Card](docs/card.png)

## Features

- **Daily Smart Meter Readings**: Captures daily electricity usage (`sensor.pseg_electricity_consumption`).
- **Estimated Cost Tracking**: Computes daily electricity cost estimates in USD (`sensor.pseg_electricity_cost`) using your configured electric rate.
- **Home Assistant Energy Dashboard**: Native Long-Term Statistics (LTS) support for electricity consumption and cost tracking.
- **Historical Backfill**: Built-in action (`pseg.backfill_history`) to backfill up to 2 years of historical daily usage and estimated cost directly into Home Assistant Energy statistics.
- **Configurable Electricity Rate**: Easily configure your effective electric rate (defaulting to standard NJ PSE&G ~$0.247/kWh) via integration options in Home Assistant.
- **Outdoor Temperature**: Records daily low, average, and high temperatures reported alongside meter readings (`sensor.pseg_outdoor_temperature`).
- **14-Day History**: Provides 14 days of interval usage and cost data in entity state attributes for local charting.
- **Manual Refresh**: Includes a refresh button (`button.pseg_refresh_data`) to trigger an immediate data fetch.
- **Auto-Registered Lovelace Card**: Bundles `pseg-energy-card` automatically registered into frontend resources and ready to add from the card picker.

## Architecture & Dependencies

This project follows a clean **two-component architecture** to keep the core Home Assistant installation lightweight while enabling automated portal sign-in:

| Component | Responsibility | Repository / Install | Dependencies |
|---|---|---|---|
| **PSE&G Integration** | Fetches hourly/daily usage & cost data from the MySmartEnergy portal; exposes sensors, buttons, and dashboard cards. | This repository (`sidprax/ha-pseg`) via HACS | `beautifulsoup4` (installed automatically by HA Core). Zero external system packages required. |
| **PSE&G Auth Companion Add-on** | *Optional companion service.* Runs an isolated headless browser to automate Okta portal authentication, handle reCAPTCHA challenges, and submit OTP codes. | [`sidprax/ha-pseg-auth-addon`](https://github.com/sidprax/ha-pseg-auth-addon) via HA Add-on Store | Packaged inside its own Docker container: Chromium, ChromeDriver, FFmpeg, Selenium, and SpeechRecognition. Does not bloat or affect HA Core. |
| **Browser Session Cookie** | Direct manual authentication without running any companion service. | Built-in | Zero external dependencies. Works on any installation type. |

## Installation

### Step 1: Install the Companion Add-on (Optional, for Automated OTP Sign-in)

If you wish to use automated username/password sign-in with SMS or Email OTP:

1. Add the companion add-on repository to Home Assistant:

   [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsidprax%2Fha-pseg-auth-addon)

   *Or manually: Go to **Settings** > **Add-ons** > **Add-on Store** > three dots (top right) > **Repositories** > add `https://github.com/sidprax/ha-pseg-auth-addon`.*
2. In the Add-on Store, find **PSE&G Auth Companion**, click **Install**, and **Start**.
3. Enable **Start on boot** and **Watchdog**.

> [!NOTE]
> If you prefer not to install the add-on, you can skip this step and connect using a **Browser Session Cookie** instead.

### Step 2: Install the Integration

#### Via HACS (Recommended)

1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right and select **Custom repositories**.
3. Add the repository:
   ```text
   https://github.com/sidprax/ha-pseg
   ```
4. Set category to **Integration** and click **Add**.
5. Find **PSE&G Energy (New Jersey)**, click **Download**, and restart Home Assistant.

#### Manual Installation

1. Copy the `custom_components/pseg` directory to your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **PSE&G Energy (New Jersey)**.
3. Choose your sign-in method:
   - **Automated Sign-In (Requires Companion Add-on)**: Enter your PSE&G portal username and password, then select your MFA delivery method (SMS or Email). If the companion add-on is not running, this option is disabled in the menu and you will be prompted to install it or use a session cookie.
   - **Browser Session Cookie (No Add-on Required)**: Provide an active session cookie copied from `mysmartenergy.nj.pseg.com`. Requires no companion add-on and works from anywhere.
4. Click **Submit**.

## Home Assistant Energy Dashboard

The integration natively publishes official Home Assistant External Statistics for both electricity consumption and cost:

1. In Home Assistant, navigate to **Settings** > **Dashboards** > **Energy**.
2. Under **Electricity Grid**, click **Add Consumption**.
3. In the statistic dropdown, select **PSE&G Electricity Consumption** (`pseg:electricity_consumption`).
4. Select **Track costs for this energy consumption** > **Use an entity with total energy costs** and select **PSE&G Electricity Cost** (`pseg:electricity_cost`).
5. Click **Save**.

The Energy Dashboard will automatically display your electric usage and actual billing costs with hourly resolution for recent days and daily trends across the full backfill range.

## Historical Backfill

To backfill historical usage data from the PSE&G portal into Home Assistant Long-Term Statistics:

1. In Home Assistant, navigate to **Developer Tools** > **Actions** (or **Services**).
2. Select the `pseg.backfill_history` action.
3. (Optional) Provide a `start_date` and `end_date` (format: `YYYY-MM-DD`). If omitted, it defaults to backfilling the last 2 years of daily data up to today.
4. Click **Perform action**.

Example action YAML:

```yaml
action: pseg.backfill_history
data:
  start_date: "2024-01-01"
  end_date: "2026-10-19"
```

## Lovelace Card

The integration registers `pseg-energy-card` automatically. Add it to any dashboard:

```yaml
type: custom:pseg-energy-card
entity: sensor.pseg_electricity_consumption
```

### Options

| Option | Type | Default | Description |
|---|---|---|---|
| `entity` | string | `sensor.pseg_electricity_consumption` | Primary consumption entity |
| `toggle_entity` | string | `input_boolean.pseg_display_dollars` | Optional helper entity to switch between kWh and dollar view |
| `range_toggle_entity` | string | `input_boolean.pseg_chart_14d` | Optional helper entity to switch between 7-day and 14-day chart view |
| `show_next_update` | boolean | `false` | Display the next scheduled fetch timestamp beside the meter label |
| `popup_hash` | string | `null` | URL hash to open a custom popup card on tap. When omitted, tapping opens the standard entity dialog. |

## Entities Provided

- `sensor.pseg_electricity_consumption`: Latest daily electric usage in kWh (contains `history_14d` and daily stats)
- `sensor.pseg_electricity_cost`: Latest daily estimated cost in USD
- `sensor.pseg_meter_id`: Meter serial number and service classification
- `sensor.pseg_latest_reading_date`: Date of the most recent recorded reading
- `sensor.pseg_outdoor_temperature`: Recorded low, average, and high temperatures
- `sensor.pseg_next_update`: Timestamp of the next scheduled polling attempt
- `button.pseg_refresh_data`: Button to trigger an immediate portal sync

## License

MIT
