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

from .const import DEFAULT_ELECTRIC_RATE

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mysmartenergy.nj.pseg.com"


class PsegAuthError(Exception):
    """Exception raised for authentication or session failures."""


class PsegConnectionError(Exception):
    """Exception raised for network or communication failures with PSE&G."""


class PsegClient:
    """Client for PSE&G MySmartEnergy."""

    def __init__(self, cookie: str, user_configured_rate: Optional[float] = None) -> None:
        self.cookie = cookie
        try:
            self.user_configured_rate = float(user_configured_rate) if user_configured_rate and float(user_configured_rate) > 0 else None
        except (ValueError, TypeError):
            self.user_configured_rate = None

        self.effective_rate = self.user_configured_rate or DEFAULT_ELECTRIC_RATE
        self.rate_source = "user_configured" if self.user_configured_rate else "default"
        self.rate_7d_avg: Optional[float] = None
        self.days_used_for_rate: int = 0

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
            if resp.status_code in (401, 403):
                raise PsegAuthError(f"HTTP status {resp.status_code} received from portal")
            if resp.status_code != 200:
                raise PsegConnectionError(f"HTTP status {resp.status_code} received from portal")
            if "signin" in resp.url.lower() or "login" in resp.url.lower():
                raise PsegAuthError("Session cookie expired or rejected by portal")
            return True
        except requests.RequestException as err:
            raise PsegConnectionError(f"Failed to connect to PSE&G: {err}") from err

    def _get_verification_token(self) -> str:
        """Extract __RequestVerificationToken from the /Dashboard page."""
        try:
            resp = self.session.get(f"{BASE_URL}/Dashboard", timeout=25)
            if resp.status_code in (401, 403):
                raise PsegAuthError(f"HTTP status {resp.status_code} received from portal")
            if resp.status_code != 200:
                raise PsegConnectionError(f"HTTP status {resp.status_code} received from portal")
            if "signin" in resp.url.lower() or "login" in resp.url.lower():
                raise PsegAuthError("Session expired: Redirected to login")
            dash_html = resp.text
        except requests.RequestException as err:
            raise PsegConnectionError(f"Network error on Dashboard: {err}") from err

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

            chart_setup_data_kwh = {
                "__RequestVerificationToken": token,
                "UsageInterval": "6",  # 6 = Daily
                "UsageType": "1",  # 1 = Consumption (kWh)
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
                    data=chart_setup_data_kwh,
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
                raise PsegConnectionError(f"Failed to retrieve chart chunk ({chunk_start_str} to {chunk_end_str}): {err}") from err
            except json.JSONDecodeError as err:
                raise PsegConnectionError(f"Invalid JSON returned from chart chunk ({chunk_start_str} to {chunk_end_str}): {err}") from err

            # Optional fetch of actual cost series (UsageType: 2)
            cost_by_date = {}
            chart_setup_data_cost = dict(chart_setup_data_kwh)
            chart_setup_data_cost["UsageType"] = "2"
            try:
                r_c1 = self.session.post(f"{BASE_URL}/Dashboard/Chart", data=chart_setup_data_cost, headers=headers2, timeout=25)
                r_c1.raise_for_status()
                ts_c = int(time.time() * 1000)
                r_c2 = self.session.get(f"{BASE_URL}/Dashboard/ChartData", params={"_": ts_c}, headers=headers2, timeout=25)
                r_c2.raise_for_status()
                c_json = r_c2.json()
                c_series = c_json.get("Data", {}).get("series", [])
                c_meter = next((s for s in c_series if "Meter" in str(s.get("name") or "")), None)
                if not c_meter and c_series:
                    c_meter = c_series[0]
                if c_meter:
                    for cpt in c_meter.get("data", []):
                        if isinstance(cpt, dict):
                            c_val = round(float(cpt.get("y", 0.0) or 0.0), 4)
                            c_hs = cpt.get("hs", {})
                            c_start = c_hs.get("start", "")
                            try:
                                c_date = datetime.strptime(c_start, "%m/%d/%Y").strftime("%Y-%m-%d")
                            except Exception:
                                c_date = c_start
                            if c_date and c_val > 0:
                                cost_by_date[c_date] = c_val
            except Exception as cost_chunk_err:
                _LOGGER.debug("Could not fetch cost chunk (%s to %s): %s", chunk_start_str, chunk_end_str, cost_chunk_err)

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
                        kwh = round(float(pt.get("y", 0.0) or 0.0), 4)
                        hs = pt.get("hs", {})
                        p_start = hs.get("start", "")
                        try:
                            dt = datetime.strptime(p_start, "%m/%d/%Y")
                            date_iso = dt.strftime("%Y-%m-%d")
                        except Exception:
                            date_iso = p_start

                        x = pt.get("x", 0)
                        start_utc = datetime.fromtimestamp(x / 1000, tz=timezone.utc) if x else None

                        # Use exact portal cost if present, otherwise calculate with effective rate
                        actual_cost = cost_by_date.get(date_iso)
                        if actual_cost is not None and actual_cost > 0:
                            cost_val = actual_cost
                        else:
                            cost_val = round(kwh * self.effective_rate, 4)

                        records_map[date_iso] = {
                            "date": date_iso,
                            "start": start_utc,
                            "kwh": kwh,
                            "cost": cost_val,
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

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days_back)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        chart_setup_data_kwh = {
            "__RequestVerificationToken": token,
            "UsageInterval": "5",  # 5 = Hourly
            "UsageType": "1",  # 1 = Consumption (kWh)
            "jsTargetName": "StorageType",
            "EnableHoverChart": "true",
            "Start": start_str,
            "End": end_str,
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

        # Step 2a: Query kWh consumption data
        try:
            resp2 = self.session.post(f"{BASE_URL}/Dashboard/Chart", data=chart_setup_data_kwh, headers=headers2, timeout=25)
            resp2.raise_for_status()
        except requests.RequestException as err:
            raise PsegConnectionError(f"Failed to set chart context: {err}") from err

        ts = int(time.time() * 1000)
        try:
            resp3 = self.session.get(f"{BASE_URL}/Dashboard/ChartData", params={"_": ts}, headers=headers2, timeout=25)
            resp3.raise_for_status()
            kwh_data = resp3.json()
        except requests.RequestException as err:
            raise PsegConnectionError(f"Failed to retrieve chart data: {err}") from err
        except json.JSONDecodeError as err:
            raise PsegConnectionError(f"Invalid JSON returned from chart data: {err}") from err

        # Step 2b: Query dollar cost data (UsageType: 2)
        cost_data = None
        chart_setup_data_cost = dict(chart_setup_data_kwh)
        chart_setup_data_cost["UsageType"] = "2"
        try:
            resp4 = self.session.post(f"{BASE_URL}/Dashboard/Chart", data=chart_setup_data_cost, headers=headers2, timeout=25)
            resp4.raise_for_status()
            ts2 = int(time.time() * 1000)
            resp5 = self.session.get(f"{BASE_URL}/Dashboard/ChartData", params={"_": ts2}, headers=headers2, timeout=25)
            resp5.raise_for_status()
            cost_data = resp5.json()
        except Exception as cost_err:
            _LOGGER.debug("Could not fetch cost chart data (UsageType: 2): %s", cost_err)

        return self._parse_chart_data(kwh_data, cost_data)

    def _parse_chart_data(self, data: Dict[str, Any], cost_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Parse series into clean sensor model and compute 7-day effective rate."""
        chart_data = data.get("Data")
        if not chart_data or not isinstance(chart_data, dict):
            ajax_results = data.get("AjaxResults") or []
            for ar in ajax_results:
                if isinstance(ar, dict) and ar.get("Action") == "Redirect":
                    raise PsegAuthError("Session expired: Redirected to login portal")
            raise PsegConnectionError("No chart data returned from MyMeter. Unexpected portal response.")

        series_list = chart_data.get("series", [])
        if not series_list:
            raise PsegConnectionError("No series data returned from MyMeter. Unexpected portal response.")

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

        # Extract actual costs from cost_data if available
        hourly_cost_map: dict[int, float] = {}
        daily_cost_map: dict[str, float] = {}
        if cost_data and isinstance(cost_data.get("Data"), dict):
            c_series_list = cost_data["Data"].get("series", [])
            c_meter = next((s for s in c_series_list if "Meter" in str(s.get("name") or "")), None)
            if not c_meter and c_series_list:
                c_meter = c_series_list[0]
            if c_meter:
                for cpt in c_meter.get("data", []):
                    if isinstance(cpt, dict):
                        cx = cpt.get("x", 0)
                        c_val = round(float(cpt.get("y", 0.0) or 0.0), 4)
                        hourly_cost_map[cx] = c_val

                        chs = cpt.get("hs", {})
                        c_start = chs.get("start", "")
                        try:
                            c_iso = datetime.strptime(c_start, "%m/%d/%Y").strftime("%Y-%m-%d")
                        except Exception:
                            c_iso = datetime.fromtimestamp(cx / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                        daily_cost_map[c_iso] = round(daily_cost_map.get(c_iso, 0.0) + c_val, 4)

        # Parse kWh data points and aggregate daily totals
        daily_kwh_map: dict[str, float] = {}
        parsed_pts = []
        for pt in detailed_pts:
            if isinstance(pt, dict):
                x = pt.get("x", 0)
                start_utc = datetime.fromtimestamp(x / 1000, tz=timezone.utc)
                kwh = round(float(pt.get("y", 0.0) or 0.0), 4)

                hs = pt.get("hs", {})
                start_str = hs.get("start", "")
                try:
                    date_iso = datetime.strptime(start_str, "%m/%d/%Y").strftime("%Y-%m-%d")
                except Exception:
                    date_iso = start_utc.strftime("%Y-%m-%d")

                daily_kwh_map[date_iso] = round(daily_kwh_map.get(date_iso, 0.0) + kwh, 4)
                parsed_pts.append({
                    "start": start_utc,
                    "date": date_iso,
                    "kwh": kwh,
                    "x": x,
                })

        # Calculate effective rate from the average of the last 7 days where BOTH cost and kWh are available
        sorted_dates = sorted(daily_kwh_map.keys())
        qualifying_days = [
            d for d in reversed(sorted_dates)
            if daily_kwh_map.get(d, 0.0) > 0.0 and daily_cost_map.get(d, 0.0) > 0.0
        ][:7]

        if qualifying_days:
            total_cost_7d = sum(daily_cost_map[d] for d in qualifying_days)
            total_kwh_7d = sum(daily_kwh_map[d] for d in qualifying_days)
            derived_7d_rate = round(total_cost_7d / total_kwh_7d, 4)
            days_used_for_rate = len(qualifying_days)
        else:
            derived_7d_rate = None
            days_used_for_rate = 0

        # Hierarchy: 1) User configured override, 2) 7-day average of available data, 3) Default rate
        if self.user_configured_rate is not None and self.user_configured_rate > 0:
            effective_rate = self.user_configured_rate
            rate_source = "user_configured"
        elif derived_7d_rate is not None:
            effective_rate = derived_7d_rate
            rate_source = "derived_7d_average"
        else:
            effective_rate = DEFAULT_ELECTRIC_RATE
            rate_source = "default"

        self.effective_rate = effective_rate
        self.rate_source = rate_source
        self.rate_7d_avg = derived_7d_rate
        self.days_used_for_rate = days_used_for_rate

        _LOGGER.debug(
            "PSE&G Rate Resolved: %s $/kWh (source=%s, 7d_avg=%s, days_used=%d)",
            effective_rate,
            rate_source,
            derived_7d_rate,
            days_used_for_rate,
        )

        # Build final hourly records with actual or derived cost
        hourly_records = []
        for p in parsed_pts:
            x_time = p["x"]
            p_kwh = p["kwh"]
            actual_hourly_cost = hourly_cost_map.get(x_time)
            if actual_hourly_cost is not None and actual_hourly_cost > 0:
                cost_val = actual_hourly_cost
                is_exact = True
            else:
                cost_val = round(p_kwh * effective_rate, 4)
                is_exact = False

            hourly_records.append({
                "start": p["start"],
                "date": p["date"],
                "kwh": p_kwh,
                "cost": cost_val,
                "is_exact_cost": is_exact,
            })

        # Build daily history (14 days)
        history_14d = []
        for d in sorted_dates:
            day_kwh = round(daily_kwh_map[d], 2)
            actual_day_cost = daily_cost_map.get(d)
            if actual_day_cost is not None and actual_day_cost > 0:
                day_cost = round(actual_day_cost, 2)
                is_exact_day = True
            else:
                day_cost = round(daily_kwh_map[d] * effective_rate, 2)
                is_exact_day = False

            history_14d.append({
                "date": d,
                "kwh": day_kwh,
                "cost": day_cost,
                "is_exact_cost": is_exact_day,
            })

        latest_record = history_14d[-1] if history_14d else {"date": "None", "kwh": 0.0, "cost": 0.0, "is_exact_cost": False}
        prev_record = history_14d[-2] if len(history_14d) > 1 else {"date": "None", "kwh": 0.0, "cost": 0.0, "is_exact_cost": False}

        latest_temp = temp_pts[-1] if temp_pts else {}
        temp_range = latest_temp.get("tr", "")

        return {
            "meter": meter_name,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "latest_date": latest_record["date"],
            "latest_kwh": latest_record["kwh"],
            "latest_cost": latest_record["cost"],
            "is_exact_latest_cost": latest_record.get("is_exact_cost", False),
            "previous_date": prev_record["date"],
            "previous_kwh": prev_record["kwh"],
            "previous_cost": prev_record["cost"],
            "history_14d": history_14d,
            "hourly_records": hourly_records,
            "temperature_range": temp_range,
            "temperature_avg": round(latest_temp.get("y", 0.0), 1) if "y" in latest_temp else None,
            "total_records": len(nav_series),
            "effective_rate": effective_rate,
            "rate_source": rate_source,
            "rate_7d_avg": derived_7d_rate,
            "days_used_for_rate": days_used_for_rate,
        }
