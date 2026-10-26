# PSE&G Energy (New Jersey) for Home Assistant

[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/sidprax/ha-pseg)](https://github.com/sidprax/ha-pseg/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Validate with hassfest](https://github.com/sidprax/ha-pseg/actions/workflows/hassfest.yaml/badge.svg)](https://github.com/sidprax/ha-pseg/actions/workflows/hassfest.yaml)
[![HACS Action](https://github.com/sidprax/ha-pseg/actions/workflows/hacs.yaml/badge.svg)](https://github.com/sidprax/ha-pseg/actions/workflows/hacs.yaml)

Home Assistant integration for Public Service Electric and Gas (PSE&G) customers in New Jersey. Retrieves daily electric meter readings, costs, and historical energy trends directly from the PSE&G MySmartEnergy portal (MyMeter).

Includes a built-in Lovelace card with 7-day and 14-day history views and kWh / cost switching.

![PSEG Energy Card](docs/card.png)

## Features

- **Daily Smart Meter Readings**: Captures daily electricity usage (`sensor.pseg_electricity_consumption`).
- **Actual & Estimated Cost Tracking**: Queries actual dollar billing from the portal alongside kWh consumption (`sensor.pseg_electricity_cost`), exposing both exact portal billing and derived estimates.
- **Dynamic 7-Day Average Rate Derivation**: Automatically calculates your effective electric rate (`$/kWh`) from the weighted average of the latest 7 days where both actual cost and kWh are reported by the portal. You can also supply a custom fixed rate in integration options as an override, or fall back to the default rate (`$0.247/kWh`).
- **Home Assistant Energy Dashboard**: Native Long-Term Statistics (LTS) support for electricity consumption and cost tracking.
- **Historical Backfill**: Built-in action (`pseg.backfill_history`) to backfill up to 2 years of historical daily usage and billing cost directly into Home Assistant Energy statistics.
- **Outdoor Temperature**: Records daily low, average, and high temperatures reported alongside meter readings (`sensor.pseg_outdoor_temperature`).
- **14-Day History**: Provides 14 days of interval usage and cost data in entity state attributes for local charting.
- **Manual Refresh**: Includes a refresh button (`button.pseg_refresh_data`) to trigger an immediate data fetch.
- **Auto-Registered Lovelace Card**: Bundles `pseg-energy-card` automatically registered into frontend resources and ready to add from the card picker.

## Authentication Methods

PSE&G provides electric smart meter interval data and billing cost details through its MySmartEnergy portal ([mysmartenergy.nj.pseg.com](https://mysmartenergy.nj.pseg.com/)), powered by the MyMeter platform.

Depending on your Home Assistant installation type and whether you prefer running background services or keeping your setup lightweight, the integration supports four authentication methods:

### Comparison

| Method | Recommended For | Add-on Needed? | 2FA / OTP Prompts | Cookie Lifespan | Automated Renewal | Initial Setup Effort |
|---|---|---|---|---|---|---|
| **Option 1: Direct MyMeter Persistent Cookie** | Most Users. Most convenient overall with minimal initial manual effort. No containers needed. | No | None | Long-lived (Persistent `MM_SID` with "Remember Me") | Manual re-paste on expiration | Low (one-time email invite) |
| **Option 2: Direct MyMeter Automated Sign-In** | Hands-off users running HA OS or Supervised who want fully automated background renewal. | Yes ([Auth Add-on](https://github.com/sidprax/ha-pseg-auth-addon)) | None | Auto-renewed | Fully automated and silent | Low (one-time email invite) |
| **Option 3: Primary PSE&G Account Automated Sign-In** | Users who prefer using their existing `pseg.com` login and don't mind entering SMS/Email OTP codes. | Yes ([Auth Add-on](https://github.com/sidprax/ha-pseg-auth-addon)) | SMS or Email OTP on setup and renewal | Auto-renewed | Requires OTP entry when prompted | Very Low (uses existing login) |
| **Option 4: Primary PSE&G Account Session Cookie** | Quick testing or users who only want to use their primary account without installing the companion add-on. | No | None (handled during browser login) | Short-lived (expires with browser session) | Manual re-paste on expiration | Very Low (copy from browser DevTools) |

---

### Step-by-Step Guides and Tradeoffs

#### Option 1: Direct MyMeter Persistent Cookie (Recommended, No Add-on)

Option 1 is the most convenient everyday option. While it requires some initial manual effort to invite the secondary email and copy the cookie once, it runs completely free of background containers, requires zero SMS or Email OTP prompts, and generates a long-lived persistent cookie (`MM_SID`) via "Remember Me" that survives browser and machine restarts.

##### Step-by-Step Setup:
1. **Invite a secondary email on MyMeter**:
   - Log into your primary PSE&G account at [pseg.com](https://www.pseg.com) and navigate to **MySmartEnergy (MyMeter)**.
   - In the top navigation menu, click **Connect User / Share Access**.
   - Enter an email address (a secondary email or an alias like `yourname+pseg@gmail.com`).
   - Select your electric meter, select access through **No end date**, and send the invitation.
2. **Activate the invited user**:
   - Open the invitation email, click the link, and choose a password and security question.
3. **Capture the persistent cookie**:
   - In your desktop browser, go directly to [mysmartenergy.nj.pseg.com](https://mysmartenergy.nj.pseg.com).
   - Sign in using your **invited email address** and password, and **check "Remember Me"**. Click **Login**.
   - After the dashboard loads, press **F12** (Developer Tools).
   - Switch to the **Network** tab and refresh the page (**F5**).
   - Click any request to `mysmartenergy.nj.pseg.com` (such as `Dashboard` or `GetIntervalData`).
   - In the **Headers** tab, locate **Request Headers**, find `Cookie:`, and copy the full cookie string (it includes `MM_SID`, `ASP.NET_SessionId`, etc.).
4. **Configure Home Assistant**:
   - In Home Assistant, navigate to **Settings** > **Devices & Services** > **Add Integration** > **PSE&G Energy**.
   - Select **Persistent Browser Cookie: Direct MyMeter (Recommended, No Add-on)**.
   - Paste the cookie string and submit.

##### Pros and Cons:
- **Pros**:
  - No companion add-on or Docker required: Works on Home Assistant Core, Container, Supervised, and OS.
  - Zero 2FA prompts: Does not rely on Okta MFA, SMS codes, or phone numbers.
  - Long session lifespan: "Remember Me" creates a persistent cookie (`MM_SID`) that remains active long-term.
- **Cons**:
  - Manual re-entry on expiration: If PSE&G ever resets sessions, you need to copy and paste a new cookie via integration Reconfigure.

---

#### Option 2: Direct MyMeter Automated Sign-In (Recommended, With Add-on)

Best for hands-off installations. Headless Chromium signs into `mysmartenergy.nj.pseg.com` directly, handles the invisible background reCAPTCHA, checks "Remember Me", and captures session cookies. Because direct MyMeter logins do not go through Okta SSO, no SMS or Email OTP code is ever requested.

##### Step-by-Step Setup:
1. **Invite a secondary email on MyMeter**: Follow Steps 1 and 2 from Option 1 above.
2. **Install the Companion Add-on**:
   - Add the add-on repository: `https://github.com/sidprax/ha-pseg-auth-addon`.
   - Install **PSE&G Auth Companion**, start it, and enable **Start on boot** and **Watchdog**.
3. **Configure Home Assistant**:
   - In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration** > **PSE&G Energy**.
   - Select **Automated Sign-In: Direct MyMeter (Recommended, Zero 2FA)**.
   - Enter your invited email address and password, then submit.

##### Pros and Cons:
- **Pros**:
  - Fully automated renewal: The coordinator renews cookies in the background without interruptions.
  - Zero 2FA prompts: No verification codes needed on initial setup or renewal.
  - No DevTools needed: No manual cookie copying.
- **Cons**:
  - Requires running the companion container (Chromium and Selenium).

---

#### Option 3: Primary PSE&G Account Automated Sign-In (With Add-on, Okta 2FA)

Uses your primary `nj.pseg.com` account. Headless Chromium automates Okta SSO navigation and reCAPTCHA challenges, then prompts you in Home Assistant for your SMS or Email verification passcode.

##### Step-by-Step Setup:
1. **Install the Companion Add-on**: Add repository `https://github.com/sidprax/ha-pseg-auth-addon` and start **PSE&G Auth Companion**.
2. **Configure Home Assistant**:
   - In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration** > **PSE&G Energy**.
   - Select **Automated Sign-In: Primary PSE&G Account (Okta 2FA)**.
   - Enter your primary PSE&G credentials, choose your 2FA method (**SMS** or **Email**), and submit.
   - Enter the 6-digit verification code received on your phone or email.

##### Pros and Cons:
- **Pros**:
  - Uses existing primary credentials without inviting an extra account.
  - Automates browser navigation and reCAPTCHA.
- **Cons**:
  - Requires OTP entry on initial setup and when sessions expire.
  - Requires running the companion container.

---

#### Option 4: Primary PSE&G Account Session Cookie (Manual, No Add-on)

Uses a temporary session cookie copied from an active primary account browser session.

##### Step-by-Step Setup:
1. Log into [pseg.com](https://www.pseg.com) with your primary account credentials and complete 2FA.
2. Navigate to **MySmartEnergy (MyMeter)**.
3. Press **F12** to open Developer Tools, select the **Network** tab, and refresh (**F5**).
4. Click any request to `mysmartenergy.nj.pseg.com` (e.g. `Dashboard`).
5. Under **Request Headers**, copy the full value of the `Cookie:` header.
6. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration** > **PSE&G Energy**, select **Session Browser Cookie: Primary PSE&G Account**, paste the cookie, and submit.

##### Pros and Cons:
- **Pros**:
  - Zero add-on dependencies.
  - Uses existing primary login.
- **Cons**:
  - Short session lifespan: Session cookies expire when the browser session ends.
  - Requires frequent manual re-entry.

---

## Architecture & Dependencies

This project follows a clean **two-component architecture** to keep the core Home Assistant installation lightweight while enabling automated portal sign-in:

| Component | Responsibility | Repository / Install | Dependencies |
|---|---|---|---|
| **PSE&G Integration** | Fetches hourly/daily usage & cost data from the MySmartEnergy portal; exposes sensors, buttons, and dashboard cards. | This repository (`sidprax/ha-pseg`) via HACS | `beautifulsoup4` (installed automatically by HA Core). Zero external system packages required. |
| **PSE&G Auth Companion Add-on** | *Optional companion service.* Runs an isolated headless browser to automate MyMeter or Okta portal authentication, handle reCAPTCHA challenges, and coordinate sign-in. | [`sidprax/ha-pseg-auth-addon`](https://github.com/sidprax/ha-pseg-auth-addon) via HA Add-on Store | Packaged inside its own Docker container: Chromium, ChromeDriver, FFmpeg, Selenium, and SpeechRecognition. Does not bloat or affect HA Core. |
| **Browser Cookie** | Direct manual authentication without running any companion service. | Built-in | Zero external dependencies. Works on any installation type. |

## Installation

### Step 1: Install the Companion Add-on (Optional, for Automated Sign-In)

If you choose **Option 2** (Direct MyMeter Automated Sign-In) or **Option 3** (Primary Account Automated Sign-In):

1. Add the companion add-on repository to Home Assistant:

   [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsidprax%2Fha-pseg-auth-addon)

   *Or manually: Go to **Settings** > **Add-ons** > **Add-on Store** > three dots (top right) > **Repositories** > add `https://github.com/sidprax/ha-pseg-auth-addon`.*
2. In the Add-on Store, find **PSE&G Auth Companion**, click **Install**, and **Start**.
3. Enable **Start on boot** and **Watchdog**.

> [!NOTE]
> If you choose **Option 1** (Persistent Browser Cookie) or **Option 4** (Session Browser Cookie), you can skip this step entirely.

### Step 2: Install the Integration

#### Via HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=sidprax&repository=ha-pseg&category=integration)

1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the **+ Explore & Download Repositories** button (or search bar).
3. Search for **PSE&G Energy (New Jersey)**.
4. Click **Download**, then restart Home Assistant.

<details>
<summary><b>Custom Repository Fallback (If not yet visible in search index)</b></summary>

*(It can take up to 8 hours for newly merged default repositories to sync across all HACS instances. If you do not see it in search yet, you can add it directly:)*

1. In Home Assistant, open **HACS** > **Integrations**.
2. Click the three dots in the top right and select **Custom repositories**.
3. Add the repository:
   ```text
   https://github.com/sidprax/ha-pseg
   ```
4. Set category to **Integration** and click **Add**.
5. Find **PSE&G Energy (New Jersey)**, click **Download**, and restart Home Assistant.
</details>

#### Manual Installation

1. Copy the `custom_components/pseg` directory to your Home Assistant `config/custom_components/` folder.
2. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration**.
2. Search for **PSE&G Energy (New Jersey)**.
3. Select your preferred authentication method from the menu:
   - **Persistent Browser Cookie: Direct MyMeter (Recommended, No Add-on)**
   - **Automated Sign-In: Direct MyMeter (Recommended, Zero 2FA)**
   - **Automated Sign-In: Primary PSE&G Account (Okta 2FA)**
   - **Session Browser Cookie: Primary PSE&G Account**
4. Follow the on-screen prompts for your selected method and click **Submit**.

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
- `sensor.pseg_electricity_cost`: Latest daily electricity cost in USD (with `rate_applied`, `rate_source`, `rate_7d_avg`, and `is_exact_portal_cost` attributes)
- `sensor.pseg_meter_id`: Meter serial number and service classification
- `sensor.pseg_latest_reading_date`: Date of the most recent recorded reading
- `sensor.pseg_outdoor_temperature`: Recorded low, average, and high temperatures
- `sensor.pseg_next_update`: Timestamp of the next scheduled polling attempt
- `button.pseg_refresh_data`: Button to trigger an immediate portal sync

## License

MIT
