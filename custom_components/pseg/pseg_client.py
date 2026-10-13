"""PSEG Client for Home Assistant.

Handles automated headless authentication through Okta (with reCAPTCHA audio fallback
and SMS/Email OTP handshake) and fetches usage data via the MyMeter platform.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mysmartenergy.nj.pseg.com"
SIGNIN_URL = f"{BASE_URL}/Saml/okta-prod/SignIn"


class PsegAuthError(Exception):
    """Exception raised for authentication failures."""


class PsegMfaRequired(Exception):
    """Exception raised when MFA code is required."""


class PsegClient:
    """Client for PSE&G MySmartEnergy."""

    def __init__(
        self,
        username: str,
        password: str,
        browser_dir: str,
        mfa_method: str = "sms",
    ) -> None:
        self.username = username
        self.password = password
        self.browser_dir = browser_dir
        self.mfa_method = mfa_method
        self.cookies: Dict[str, str] = {}
        self._driver = None

    def _solve_recaptcha_if_present(self, driver) -> None:
        """Automatically solve visual reCAPTCHA challenge via audio transcription."""
        time.sleep(2)
        from selenium.webdriver.common.by import By
        import speech_recognition as sr

        bframes = [
            f
            for f in driver.find_elements(By.TAG_NAME, "iframe")
            if "bframe" in (f.get_attribute("src") or "")
        ]
        if not bframes:
            return

        _LOGGER.info("reCAPTCHA challenge detected. Solving via audio challenge...")
        driver.switch_to.frame(bframes[0])
        try:
            audio_btn = driver.find_element(By.ID, "recaptcha-audio-button")
            audio_btn.click()
            time.sleep(3)

            src = driver.find_element(By.ID, "audio-source").get_attribute("src")
            tmp_mp3 = "/tmp/pseg_recaptcha.mp3"
            tmp_wav = "/tmp/pseg_recaptcha.wav"
            urllib.request.urlretrieve(src, tmp_mp3)
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_mp3, tmp_wav],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            recognizer = sr.Recognizer()
            with sr.AudioFile(tmp_wav) as audio_file:
                audio_data = recognizer.record(audio_file)
            transcription = recognizer.recognize_google(audio_data)
            _LOGGER.debug("reCAPTCHA audio transcription: %s", transcription)

            inp = driver.find_element(By.ID, "audio-response")
            inp.send_keys(transcription)
            time.sleep(1)
            driver.find_element(By.ID, "recaptcha-verify-button").click()
            time.sleep(3)
        except Exception as err:
            _LOGGER.warning("Could not auto-solve reCAPTCHA: %s", err)
        finally:
            driver.switch_to.default_content()

    def _init_browser(self):
        """Initialize headless Chrome/Chromium with stealth flags."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        os.makedirs(self.browser_dir, exist_ok=True)
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument(f"--user-data-dir={self.browser_dir}")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        for bin_path in ["/usr/bin/chromium-browser", "/usr/bin/chromium", "/usr/bin/google-chrome"]:
            if os.path.exists(bin_path):
                opts.binary_location = bin_path
                break

        driver_path = "/usr/bin/chromedriver"
        service = Service(driver_path) if os.path.exists(driver_path) else Service()

        driver = webdriver.Chrome(service=service, options=opts)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"},
        )
        return driver

    def start_login(self) -> bool:
        """Start login flow. Returns True if logged in directly, or raises PsegMfaRequired."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        self._driver = self._init_browser()
        driver = self._driver

        try:
            _LOGGER.info("Navigating to PSE&G login...")
            driver.get(SIGNIN_URL)
            time.sleep(4)

            # Check if existing session in browser profile is still active
            if "mysmartenergy.nj.pseg.com" in driver.current_url and "SignIn" not in driver.current_url:
                _LOGGER.info("Existing browser session is still valid.")
                self._extract_cookies_from_driver()
                self._close_browser()
                return True

            # Enter identifier
            user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='identifier']")
            if user_inputs:
                user_inputs[0].clear()
                user_inputs[0].send_keys(self.username)
                time.sleep(1)
                user_inputs[0].send_keys(Keys.ENTER)
                time.sleep(4)
                self._solve_recaptcha_if_present(driver)

            # Enter password
            pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='credentials.passcode']")
            if not pass_inputs:
                for _ in range(15):
                    time.sleep(1)
                    pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='credentials.passcode']")
                    if pass_inputs:
                        break

            if not pass_inputs:
                raise PsegAuthError("Password field was not found on the login screen")

            pass_inputs[0].send_keys(self.password)
            time.sleep(1)
            pass_inputs[0].send_keys(Keys.ENTER)
            time.sleep(6)

            # Check if redirected directly
            if "mysmartenergy.nj.pseg.com" in driver.current_url and "SignIn" not in driver.current_url:
                self._extract_cookies_from_driver()
                self._close_browser()
                return True

            # MFA screen reached
            phone_btns = driver.find_elements(
                By.CSS_SELECTOR, "a[aria-label*='Select Phone'], button[aria-label*='Select Phone']"
            )
            email_btns = driver.find_elements(
                By.CSS_SELECTOR, "a[aria-label*='Select Email'], button[aria-label*='Select Email']"
            )

            if self.mfa_method == "email" and email_btns:
                _LOGGER.info("Selecting Email MFA...")
                email_btns[0].click()
                time.sleep(4)
            elif phone_btns:
                _LOGGER.info("Selecting Phone MFA...")
                phone_btns[0].click()
                time.sleep(4)
                sms_btns = driver.find_elements(
                    By.CSS_SELECTOR, "a[aria-label*='SMS'], button[aria-label*='SMS'], input[value*='SMS']"
                )
                if sms_btns:
                    sms_btns[0].click()
                    time.sleep(4)

            # Now on OTP entry screen
            _LOGGER.info("MFA code dispatched. Holding browser session open.")
            raise PsegMfaRequired("MFA verification code required")

        except PsegMfaRequired:
            raise
        except Exception as err:
            self._close_browser()
            raise PsegAuthError(f"Login failed: {err}") from err

    def complete_mfa(self, code: str) -> bool:
        """Submit MFA passcode and capture cookies."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        if not self._driver:
            raise PsegAuthError("No active browser session to complete MFA")

        driver = self._driver
        try:
            passcode_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='credentials.passcode']")
            if not passcode_inputs:
                passcode_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='tel'], input[name='passcode']")
            if not passcode_inputs:
                raise PsegAuthError("Could not locate MFA passcode input field")

            _LOGGER.info("Entering MFA code...")
            passcode_inputs[0].clear()
            passcode_inputs[0].send_keys(code)
            time.sleep(1)
            passcode_inputs[0].send_keys(Keys.ENTER)

            for _ in range(25):
                time.sleep(1)
                if "mysmartenergy.nj.pseg.com" in driver.current_url and "SignIn" not in driver.current_url:
                    _LOGGER.info("SAML redirect complete.")
                    break
            else:
                raise PsegAuthError("Timed out waiting for portal redirect after MFA")

            self._extract_cookies_from_driver()
            return True
        finally:
            self._close_browser()

    def _extract_cookies_from_driver(self) -> None:
        if self._driver:
            cookie_list = self._driver.get_cookies()
            self.cookies = {c["name"]: c["value"] for c in cookie_list}
            _LOGGER.info("Captured %d cookies from session", len(self.cookies))

    def _close_browser(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def _get_cookie_header(self) -> str:
        return "; ".join([f"{k}={v}" for k, v in self.cookies.items()])

    def fetch_energy_data(self, days_back: int = 14) -> Dict[str, Any]:
        """Fetch usage and temperature data using the 3-step MyMeter chart sequence."""
        if not self.cookies:
            raise PsegAuthError("No cookies available. Must authenticate first.")

        cookie_str = self._get_cookie_header()
        headers = {
            "cookie": cookie_str,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "referer": f"{BASE_URL}/Dashboard",
        }

        # Step 1: GET /Dashboard -> Extract __RequestVerificationToken
        req1 = urllib.request.Request(f"{BASE_URL}/Dashboard", headers=headers)
        with urllib.request.urlopen(req1, timeout=30) as resp:
            dash_html = resp.read().decode("utf-8")

        token_match = re.search(
            r'name=[\"\']__RequestVerificationToken[\"\'][^>]*value=[\"\']([^\"\']+)[\"\']',
            dash_html,
        )
        if not token_match:
            raise PsegAuthError("Session expired or invalid: __RequestVerificationToken not found")
        token = token_match.group(1)

        # Step 2: POST /Dashboard/Chart -> Set date range and interval
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days_back)
        chart_setup_data = {
            "__RequestVerificationToken": token,
            "UsageInterval": "6",  # 6 = Daily
            "UsageType": "1",  # 1 = Consumption
            "jsTargetName": "StorageType",
            "EnableHoverChart": "true",
            "Start": start_dt.strftime("%Y-%m-%d"),
            "End": end_dt.strftime("%Y-%m-%d"),
            "IsRangeOpen": "False",
            "MaintainMaxDate": "true",
            "SelectedViaDateRange": "False",
            "ChartComparison": "1",
            "ChartComparison2": "0",
            "ChartComparison3": "0",
            "ChartComparison4": "0",
        }

        headers2 = headers.copy()
        headers2["content-type"] = "application/x-www-form-urlencoded"
        headers2["x-requested-with"] = "XMLHttpRequest"

        encoded = urllib.parse.urlencode(chart_setup_data).encode("utf-8")
        req2 = urllib.request.Request(f"{BASE_URL}/Dashboard/Chart", data=encoded, headers=headers2)
        with urllib.request.urlopen(req2, timeout=30) as resp:
            resp.read()

        # Step 3: GET /Dashboard/ChartData -> Parse pure JSON series
        ts = int(time.time() * 1000)
        req3 = urllib.request.Request(f"{BASE_URL}/Dashboard/ChartData?_={ts}", headers=headers2)
        with urllib.request.urlopen(req3, timeout=30) as resp:
            raw_json = resp.read().decode("utf-8")
            data = json.loads(raw_json)

        return self._parse_chart_data(data)

    def _parse_chart_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse series into clean sensor model."""
        series_list = data.get("Data", {}).get("series", [])
        if not series_list:
            raise PsegAuthError("No series data returned from MyMeter")

        nav_series = series_list[0].get("data", [])  # [[timestamp, kwh], ...]
        meter_series = {}
        temp_series = {}

        for s in series_list:
            name = str(s.get("name") or "")
            if "Meter" in name:
                meter_series = s
            elif "Temperature" in name:
                temp_series = s

        meter_name = meter_series.get("name") or "PSE&G Electric Meter"
        detailed_pts = meter_series.get("data", [])
        temp_pts = temp_series.get("data", [])

        # Build daily history list
        history_14d = []
        for i, pt in enumerate(detailed_pts):
            if isinstance(pt, dict):
                kwh = round(pt.get("y", 0.0), 2)
                hs = pt.get("hs", {})
                # '10/11/2026' -> '2026-10-11'
                start_str = hs.get("start", "")
                try:
                    dt = datetime.strptime(start_str, "%m/%d/%Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_iso = start_str

                # Approximate cost (around $0.25/kWh standard NJ tariff)
                est_cost = round(kwh * 0.247, 2)
                history_14d.append({
                    "date": date_iso,
                    "kwh": kwh,
                    "cost": est_cost,
                })

        latest_record = history_14d[-1] if history_14d else {"date": "None", "kwh": 0.0, "cost": 0.0}
        prev_record = history_14d[-2] if len(history_14d) > 1 else {"date": "None", "kwh": 0.0, "cost": 0.0}

        latest_temp = temp_pts[-1] if temp_pts else {}
        temp_range = latest_temp.get("tr", "")  # e.g. '55° | 60° | 63°F'

        return {
            "meter": meter_name,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "latest_date": latest_record["date"],
            "latest_kwh": latest_record["kwh"],
            "latest_cost": latest_record["cost"],
            "previous_date": prev_record["date"],
            "previous_kwh": prev_record["kwh"],
            "previous_cost": prev_record["cost"],
            "history_14d": history_14d,
            "temperature_range": temp_range,
            "temperature_avg": round(latest_temp.get("y", 0.0), 1) if "y" in latest_temp else None,
            "total_records": len(nav_series),
        }
