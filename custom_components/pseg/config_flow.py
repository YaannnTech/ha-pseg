"""Config flow for the PSE&G Energy integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_BROWSER_DIR,
    CONF_MFA_CODE,
    CONF_MFA_METHOD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_MFA_METHOD,
    DOMAIN,
    MFA_METHOD_EMAIL,
    MFA_METHOD_SMS,
)
from .pseg_client import PsegAuthError, PsegClient, PsegMfaRequired

_LOGGER = logging.getLogger(__name__)


class PsegConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PSE&G Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._client: Optional[PsegClient] = None
        self._user_input: Dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step where credentials are provided."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Check for existing entries with same username
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            self._user_input = user_input
            browser_dir = self.hass.config.path("pseg", "browser_data")
            user_input[CONF_BROWSER_DIR] = browser_dir

            self._client = PsegClient(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                browser_dir=browser_dir,
                mfa_method=user_input.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD),
            )

            try:
                # Attempt login in executor
                logged_in = await self.hass.async_add_executor_job(
                    self._client.start_login
                )
                if logged_in:
                    return self.async_create_entry(
                        title=f"PSE&G ({user_input[CONF_USERNAME]})",
                        data=user_input,
                    )
            except PsegMfaRequired:
                # MFA prompt reached - advance to MFA code step
                return await self.async_step_mfa()
            except PsegAuthError as err:
                _LOGGER.error("Authentication error: %s", err)
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.exception("Unexpected error during login: %s", err)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_MFA_METHOD, default=DEFAULT_MFA_METHOD): vol.In(
                    [MFA_METHOD_SMS, MFA_METHOD_EMAIL]
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_mfa(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle verification of MFA code."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            code = user_input.get(CONF_MFA_CODE, "").strip()
            if self._client:
                try:
                    success = await self.hass.async_add_executor_job(
                        self._client.complete_mfa, code
                    )
                    if success:
                        return self.async_create_entry(
                            title=f"PSE&G ({self._user_input[CONF_USERNAME]})",
                            data=self._user_input,
                        )
                except PsegAuthError as err:
                    _LOGGER.error("MFA verification failed: %s", err)
                    errors["base"] = "invalid_code"
                except Exception as err:
                    _LOGGER.exception("Unexpected error during MFA: %s", err)
                    errors["base"] = "unknown"
            else:
                return await self.async_step_user()

        schema = vol.Schema(
            {
                vol.Required(CONF_MFA_CODE): str,
            }
        )

        return self.async_show_form(
            step_id="mfa",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "method": self._user_input.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD).upper()
            },
        )
