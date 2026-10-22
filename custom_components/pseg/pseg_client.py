"""PSEG API Client for Home Assistant (New Jersey).

Uses session cookies to communicate directly with the PSE&G MySmartEnergy portal (MyMeter platform).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import re
import time
from typing import Any, Dict, Optional

import requests

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mysmartenergy.nj.pseg.com"


class PsegAuthError(Exception):
    """Exception raised for authentication or session failures."""


class PsegClient:
    """Client for PSE&G MySmartEnergy."""

    def __init__(self, cookie: str) -> None:
        self.cookie = cookie
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": f"{BASE_URL}/Dashboard",
        })
        self.update_cookie(cookie)

    def update_cookie(self, new_cookie: str) -> None:
        """Update active session cookies."""
        self.cookie = new_cookie
        self.session.headers.update({"Cookie": new_cookie})

    def test_connection(self) -> bool:
        """Validate whether current session cookie is authorized."""
        try:
            resp = self.session.get(f"{BASE_URL}/Dashboard", allow_redirects=True, timeout=20)
            if resp.status_code != 200:
                raise PsegAuthError(f"HTTP status {resp.status_code} received from portal")
            if "signin" in resp.url.lower() or "login" in resp.url.lower():
                raise PsegAuthError("Session cookie expired or rejected by portal")
            return True
        except requests.RequestException as err:
            raise PsegAuthError(f"Failed to connect to PSE&G: {err}") from err

    def _get_verification_token(self) -> str:
        """Extract __RequestVerificationToken from the /Dashboard page."""
        try:
            resp = self.session.get(f"{BASE_URL}/Dashboard", timeout=25)
            if "signin" in resp.url.lower() or "login" in resp.url.lower():
                raise PsegAuthError("Session expired: Redirected to login")
            dash_html = resp.text
        except requests.RequestException as err:
            raise PsegAuthError(f"Network error on Dashboard: {err}") from err

        token_match = re.search(
            r'name=[\"\']__RequestVerificationToken[\"\'][^>]*value=[\"\']([^\"\']+)[\"\']',
            dash_html,
        )
        if not token_match:
            raise PsegAuthError("Session invalid: __RequestVerificationToken not found on /Dashboard")
        return token_match.group(1)

    def fetch_history_range(
        self,
        start_date_str: str,
        end_date_str: str,
        chunk_days: int = 90,
    ) -> list[dict[str, Any]]:
        """Fetch historical usage and cost data across a date range in polite chunks."""
        token = self._get_verification_token()

        try:
            start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
        except ValueError as err:
            raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {err}") from err

        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt

        headers2 = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
        }

        records_map: dict[str, dict[str, Any]] = {}
        curr_start = start_dt

        while curr_start <= end_dt:
            curr_end = min(curr_start + timedelta(days=chunk_days), end_dt)
            chunk_start_str = curr_start.strftime("%Y-%m-%d")
            chunk_end_str = curr_end.strftime("%Y-%m-%d")
            _LOGGER.info("Fetching PSE&G history chunk from %s to %s...", chunk_start_str, chunk_end_str)

            chart_setup_data = {
                "__RequestVerificationToken": token,
                "UsageInterval": "6",  # 6 = Daily
                "UsageType": "1",  # 1 = Consumption
                "jsTargetName": "StorageType",
                "EnableHoverChart": "true",
                "Start": chunk_start_str,
                "End": chunk_end_str,
                "IsRangeOpen": "False",
                "MaintainMaxDate": "true",
                "SelectedViaDateRange": "False",
                "ChartComparison": "1",
                "ChartComparison2": "0",
                "ChartComparison3": "0",
                "ChartComparison4": "0",
            }

            try:
                resp2 = self.session.post(
                    f"{BASE_URL}/Dashboard/Chart",
                    data=chart_setup_data,
                    headers=headers2,
                    timeout=25,
                )
                resp2.raise_for_status()

                ts = int(time.time() * 1000)
                resp3 = self.session.get(
                    f"{BASE_URL}/Dashboard/ChartData",
                    params={"_": ts},
                    headers=headers2,
                    timeout=25,
                )
                resp3.raise_for_status()
                data = resp3.json()
            except requests.RequestException as err:
                raise PsegAuthError(f"Failed to retrieve chart chunk ({chunk_start_str} to {chunk_end_str}): {err}") from err

            chart_data = data.get("Data")
            if not chart_data or not isinstance(chart_data, dict):
                ajax_results = data.get("AjaxResults") or []
                for ar in ajax_results:
                    if isinstance(ar, dict) and ar.get("Action") == "Redirect":
                        raise PsegAuthError("Session expired during history backfill: Redirected to login")
                _LOGGER.warning("No chart data returned for range %s to %s", chunk_start_str, chunk_end_str)
            else:
                series_list = chart_data.get("series", [])
                meter_series = {}
                for s in series_list:
                    if "Meter" in str(s.get("name") or ""):
                        meter_series = s
                        break

                pts = meter_series.get("data", [])
                for pt in pts:
                    if isinstance(pt, dict):
                        kwh = round(pt.get("y", 0.0), 4)
                        hs = pt.get("hs", {})
                        p_start = hs.get("start", "")
                        try:
                            dt = datetime.strptime(p_start, "%m/%d/%Y")
                            date_iso = dt.strftime("%Y-%m-%d")
                        except Exception:
                            date_iso = p_start

                        x = pt.get("x", 0)
                        start_utc = datetime.fromtimestamp(x / 1000, tz=timezone.utc) if x else None
                        est_cost = round(kwh * 0.247, 4)
                        records_map[date_iso] = {
                            "date": date_iso,
                            "start": start_utc,
                            "kwh": kwh,
                            "cost": est_cost,
                        }

            curr_start = curr_end + timedelta(days=1)
            if curr_start <= end_dt:
                time.sleep(0.75)

        sorted_records = [records_map[d] for d in sorted(records_map.keys())]
        _LOGGER.info(
            "Fetched %d historical records across range %s to %s",
            len(sorted_records),
            start_date_str,
            end_date_str,
        )
        return sorted_records

    def fetch_energy_data(self, days_back: int = 14) -> Dict[str, Any]:
        """Fetch usage and temperature data using the 3-step MyMeter chart sequence."""
        token = self._get_verification_token()

        # Step 2: POST /Dashboard/Chart -> Set date range and hourly granularity
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days_back)
        chart_setup_data = {
            "__RequestVerificationToken": token,
            "UsageInterval": "5",  # 5 = Hourly
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

        headers2 = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE_URL,
        }

        try:
            resp2 = self.session.post(f"{BASE_URL}/Dashboard/Chart", data=chart_setup_data, headers=headers2, timeout=25)
            resp2.raise_for_status()
        except requests.RequestException as err:
            raise PsegAuthError(f"Failed to set chart context: {err}") from err

        # Step 3: GET /Dashboard/ChartData -> Parse pure JSON series
        ts = int(time.time() * 1000)
        try:
            resp3 = self.session.get(f"{BASE_URL}/Dashboard/ChartData", params={"_": ts}, headers=headers2, timeout=25)
            resp3.raise_for_status()
            data = resp3.json()
        except Exception as err:
            raise PsegAuthError(f"Failed to retrieve chart data: {err}") from err

        return self._parse_chart_data(data)

    def _parse_chart_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse series into clean sensor model."""
        chart_data = data.get("Data")
        if not chart_data or not isinstance(chart_data, dict):
            ajax_results = data.get("AjaxResults") or []
            for ar in ajax_results:
                if isinstance(ar, dict) and ar.get("Action") == "Redirect":
                    raise PsegAuthError("Session expired: Redirected to login portal")
            raise PsegAuthError("No chart data returned from MyMeter. Session may have expired.")

        series_list = chart_data.get("series", [])
        if not series_list:
            raise PsegAuthError("No series data returned from MyMeter. Session may have expired.")

        nav_series = series_list[0].get("data", [])
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

        hourly_records = []
        daily_map: dict[str, dict[str, Any]] = {}

        for pt in detailed_pts:
            if isinstance(pt, dict):
                x = pt.get("x", 0)
                start_utc = datetime.fromtimestamp(x / 1000, tz=timezone.utc)
                kwh = round(pt.get("y", 0.0), 4)
                cost = round(kwh * 0.247, 4)

                hourly_records.append({
                    "start": start_utc,
                    "date": start_utc.strftime("%Y-%m-%d"),
                    "kwh": kwh,
                    "cost": cost,
                })

                hs = pt.get("hs", {})
                start_str = hs.get("start", "")
                try:
                    date_iso = datetime.strptime(start_str, "%m/%d/%Y").strftime("%Y-%m-%d")
                except Exception:
                    date_iso = start_utc.strftime("%Y-%m-%d")

                if date_iso not in daily_map:
                    daily_map[date_iso] = {"date": date_iso, "kwh": 0.0, "cost": 0.0}
                daily_map[date_iso]["kwh"] = round(daily_map[date_iso]["kwh"] + kwh, 2)
                daily_map[date_iso]["cost"] = round(daily_map[date_iso]["cost"] + cost, 2)

        history_14d = sorted(daily_map.values(), key=lambda x: x["date"])
        latest_record = history_14d[-1] if history_14d else {"date": "None", "kwh": 0.0, "cost": 0.0}
        prev_record = history_14d[-2] if len(history_14d) > 1 else {"date": "None", "kwh": 0.0, "cost": 0.0}

        latest_temp = temp_pts[-1] if temp_pts else {}
        temp_range = latest_temp.get("tr", "")

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
            "hourly_records": hourly_records,
            "temperature_range": temp_range,
            "temperature_avg": round(latest_temp.get("y", 0.0), 1) if "y" in latest_temp else None,
            "total_records": len(nav_series),
        }
