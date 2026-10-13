"""The PSE&G Energy integration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BROWSER_DIR,
    CONF_MFA_METHOD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_MFA_METHOD,
    DOMAIN,
)
from .coordinator import PsegDataUpdateCoordinator
from .pseg_client import PsegClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up PSE&G integration wide configuration and register Lovelace resource."""
    # Register the bundled custom card static path
    frontend_path = Path(__file__).parent / "frontend" / "pseg-energy-card.js"
    if frontend_path.exists():
        hass.http.register_static_path(
            "/pseg/pseg-energy-card.js",
            str(frontend_path),
            cache_headers=False,
        )
        _LOGGER.debug("Registered static path for PSEG custom card: /pseg/pseg-energy-card.js")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PSE&G from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    browser_dir = entry.data.get(
        CONF_BROWSER_DIR, hass.config.path("pseg", "browser_data")
    )

    client = PsegClient(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        browser_dir=browser_dir,
        mfa_method=entry.data.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD),
    )

    coordinator = PsegDataUpdateCoordinator(hass, client)

    # Perform initial refresh to populate sensors
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a PSE&G config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
