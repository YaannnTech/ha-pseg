"""DataUpdateCoordinator for the PSE&G Energy integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN
from .pseg_client import PsegAuthError, PsegClient

_LOGGER = logging.getLogger(__name__)


class PsegDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching PSE&G energy data from MyMeter."""

    def __init__(self, hass: HomeAssistant, client: PsegClient) -> None:
        """Initialize the coordinator."""
        self.client = client
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
            _LOGGER.warning("Authentication failed or session expired. Attempting silent re-login: %s", err)
            try:
                # Attempt silent session re-authentication with saved browser profile
                await self.hass.async_add_executor_job(self.client.start_login)
                return await self.hass.async_add_executor_job(
                    self.client.fetch_energy_data, 14
                )
            except Exception as login_err:
                raise UpdateFailed(f"Failed to refresh PSE&G session: {login_err}") from login_err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with PSE&G: {err}") from err
