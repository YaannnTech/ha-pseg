"""Pytest fixtures and environment configuration."""

import sys
from unittest.mock import MagicMock

# Stub Home Assistant packages if not installed in current environment
for mod in [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.frontend",
    "homeassistant.components.sensor",
    "homeassistant.components.button",
    "homeassistant.components.recorder",
    "homeassistant.components.recorder.statistics",
    "homeassistant.components.recorder.models",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.util",
    "homeassistant.util.dt",
]:
    if mod not in sys.modules:
        m = MagicMock()
        m.__path__ = []
        sys.modules[mod] = m

if "aiohttp" not in sys.modules:
    sys.modules["aiohttp"] = MagicMock()
