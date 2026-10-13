"""The PSE&G Energy integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_COOKIE, DOMAIN
from .coordinator import PsegDataUpdateCoordinator
from .pseg_client import PsegClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up PSE&G integration wide configuration and register Lovelace resource."""
    frontend_path = Path(__file__).parent / "frontend" / "pseg-energy-card.js"
    if frontend_path.exists():
        try:
            from homeassistant.components.http import StaticPathConfig
            await hass.http.async_register_static_paths([
                StaticPathConfig("/pseg/pseg-energy-card.js", str(frontend_path), False)
            ])
            _LOGGER.debug("Registered static path for PSEG custom card: /pseg/pseg-energy-card.js")
        except Exception as err:
            _LOGGER.debug("Could not register static path: %s", err)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PSE&G from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    cookie = entry.data.get(CONF_COOKIE, "")
    client = PsegClient(cookie)
    coordinator = PsegDataUpdateCoordinator(hass, client, dict(entry.data))

    # Initial data refresh
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
