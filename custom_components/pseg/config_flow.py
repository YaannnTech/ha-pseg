"""Config flow for the PSE&G Energy integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_AUTH_SERVER_URL,
    CONF_COOKIE,
    CONF_MFA_CODE,
    CONF_MFA_METHOD,
    CONF_PASSWORD,
    CONF_USERNAME,
    DEFAULT_AUTH_SERVER_URL,
    DEFAULT_MFA_METHOD,
    DOMAIN,
    MFA_METHOD_EMAIL,
    MFA_METHOD_SMS,
)
from .pseg_client import PsegAuthError, PsegClient

_LOGGER = logging.getLogger(__name__)


class PsegConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PSE&G Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._user_input: Dict[str, Any] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            cookie = user_input.get(CONF_COOKIE, "").strip()
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            mfa_method = user_input.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD)
            auth_url = user_input.get(CONF_AUTH_SERVER_URL, DEFAULT_AUTH_SERVER_URL)

            # Option 1: Direct Cookie authentication
            if cookie:
                try:
                    client = PsegClient(cookie)
                    await self.hass.async_add_executor_job(client.test_connection)
                    title = f"PSE&G ({username})" if username else "PSE&G Energy"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_COOKIE: cookie,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                        },
                    )
                except PsegAuthError as err:
                    _LOGGER.error("Cookie validation error: %s", err)
                    errors["base"] = "invalid_cookie"
                except Exception as err:
                    _LOGGER.exception("Unexpected error validating cookie: %s", err)
                    errors["base"] = "unknown"

            # Option 2: Automated Login via local auth service
            elif username and password:
                self._user_input = user_input
                self.context["username"] = username
                self.context["password"] = password
                self.context["auth_url"] = auth_url

                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{auth_url}/login",
                            json={
                                "username": username,
                                "password": password,
                                "mfa_method": mfa_method,
                            },
                            timeout=aiohttp.ClientTimeout(total=90),
                        ) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("success") and res_json.get("cookies"):
                                    # Already logged in without MFA
                                    cookies = res_json["cookies"]
                                    return self.async_create_entry(
                                        title=f"PSE&G ({username})",
                                        data={
                                            CONF_COOKIE: cookies,
                                            CONF_USERNAME: username,
                                            CONF_PASSWORD: password,
                                        },
                                    )
                                elif res_json.get("mfa_required"):
                                    # MFA code required -> transition to step mfa
                                    return await self.async_step_mfa()
                                else:
                                    errors["base"] = "invalid_auth"
                            else:
                                err_text = await resp.text()
                                _LOGGER.error("Auth helper returned status %s: %s", resp.status, err_text)
                                errors["base"] = "invalid_auth"
                except aiohttp.ClientConnectorError:
                    _LOGGER.error("Could not reach auth server at %s", auth_url)
                    errors["base"] = "auth_server_unavailable"
                except Exception as err:
                    _LOGGER.exception("Error calling auth server: %s", err)
                    errors["base"] = "unknown"
            else:
                errors["base"] = "missing_credentials"

        schema = vol.Schema(
            {
                vol.Optional(CONF_USERNAME, default=""): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_MFA_METHOD, default=DEFAULT_MFA_METHOD): vol.In(
                    [MFA_METHOD_SMS, MFA_METHOD_EMAIL]
                ),
                vol.Optional(CONF_COOKIE, default=""): str,
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
        auth_url = self.context.get("auth_url", DEFAULT_AUTH_SERVER_URL)
        username = self.context.get("username", "")
        password = self.context.get("password", "")

        if user_input is not None:
            code = user_input.get(CONF_MFA_CODE, "").strip()
            if not code:
                errors["base"] = "invalid_code"
            else:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{auth_url}/login/mfa",
                            json={"code": code},
                            timeout=aiohttp.ClientTimeout(total=60),
                        ) as resp:
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("success") and res_json.get("cookies"):
                                    cookies = res_json["cookies"]
                                    return self.async_create_entry(
                                        title=f"PSE&G ({username})",
                                        data={
                                            CONF_COOKIE: cookies,
                                            CONF_USERNAME: username,
                                            CONF_PASSWORD: password,
                                        },
                                    )
                                else:
                                    errors["base"] = "invalid_code"
                            else:
                                errors["base"] = "invalid_code"
                except Exception as err:
                    _LOGGER.exception("MFA verification error: %s", err)
                    errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_MFA_CODE): str,
            }
        )

        return self.async_show_form(
            step_id="mfa",
            data_schema=schema,
            errors=errors,
        )
