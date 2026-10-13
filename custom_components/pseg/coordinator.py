"""DataUpdateCoordinator for the PSE&G Energy integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTH_SERVER_URL,
    CONF_COOKIE,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_AUTH_SERVER_URL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
)
from .pseg_client import PsegAuthError, PsegClient

_LOGGER = logging.getLogger(__name__)


class PsegDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching PSE&G energy data from MyMeter."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PsegClient,
        entry_data: Dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry_data = entry_data
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=DEFAULT_SCAN_INTERVAL_HOURS),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from PSE&G."""
        try:
            return await self.hass.async_add_executor_job(
                self.client.fetch_energy_data, 14
            )
        except PsegAuthError as err:
            _LOGGER.warning("Session error: %s. Attempting silent re-authentication...", err)
            username = self.entry_data.get(CONF_USERNAME)
            password = self.entry_data.get(CONF_PASSWORD)
            auth_url = self.entry_data.get(CONF_AUTH_SERVER_URL, DEFAULT_AUTH_SERVER_URL)

            if username and password:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{auth_url}/login",
                            json={"username": username, "password": password},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("success") and res_json.get("cookies"):
                                    new_cookies = res_json["cookies"]
                                    self.client.update_cookie(new_cookies)
                                    return await self.hass.async_add_executor_job(
                                        self.client.fetch_energy_data, 14
                                    )
                except Exception as refresh_err:
                    _LOGGER.error("Silent refresh failed: %s", refresh_err)

            raise UpdateFailed(f"Session expired. Please update authentication in integration options: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with PSE&G: {err}") from err
