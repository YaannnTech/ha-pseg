"""Config flow for the PSE&G Energy integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    """Handle a multi-step guided config flow for PSE&G Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._user_input: Dict[str, Any] = {}
        self._reauth_entry: Optional[config_entries.ConfigEntry] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 1: Choose connection method."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["automated", "cookie"],
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Handle reauthorization request from Home Assistant."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return self.async_show_menu(
            step_id="reauth",
            menu_options=["reauth_confirm", "cookie"],
        )

    async def async_step_reconfigure(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle a reconfiguration flow initialized by the user."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reauth_confirm", "cookie"],
        )

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Confirm reauth credentials and trigger sign-in."""
        errors: Dict[str, str] = {}
        existing_data = self._reauth_entry.data if self._reauth_entry else {}
        default_username = existing_data.get(CONF_USERNAME, "")
        default_mfa = existing_data.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD)

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, default_username).strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            mfa_method = user_input.get(CONF_MFA_METHOD, default_mfa)
            auth_url = existing_data.get(CONF_AUTH_SERVER_URL, DEFAULT_AUTH_SERVER_URL)

            if not username or not password:
                errors["base"] = "missing_credentials"
            else:
                candidate_urls = [auth_url]
                for fallback in ["http://10.0.2.52:8000", "http://127.0.0.1:8000"]:
                    if fallback not in candidate_urls:
                        candidate_urls.append(fallback)

                connected = False
                session = async_get_clientsession(self.hass)
                auth_result = None
                for target_url in candidate_urls:
                    try:
                        async with session.post(
                            f"{target_url}/login",
                            json={
                                "username": username,
                                "password": password,
                                "mfa_method": mfa_method,
                            },
                            timeout=aiohttp.ClientTimeout(total=90),
                        ) as resp:
                            connected = True
                            self.context["auth_url"] = target_url
                            self.context["username"] = username
                            self.context["password"] = password
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("success") and res_json.get("cookies"):
                                    auth_result = ("success", res_json["cookies"], target_url)
                                    break
                                elif res_json.get("mfa_required"):
                                    auth_result = ("mfa", None, target_url)
                                    break
                                else:
                                    _LOGGER.error("Auth helper response: %s", res_json)
                                    errors["base"] = "invalid_auth"
                                    break
                            else:
                                try:
                                    res_json = await resp.json()
                                except Exception:
                                    res_json = {}
                                if resp.status == 403 or res_json.get("recaptcha_blocked"):
                                    errors["base"] = "recaptcha_blocked"
                                elif resp.status == 500:
                                    _LOGGER.error("Auth helper returned 500: %s", res_json)
                                    errors["base"] = "auth_server_error"
                                else:
                                    errors["base"] = "invalid_auth"
                                break
                    except aiohttp.ClientConnectorError:
                        _LOGGER.debug("Could not reach auth server at %s", target_url)
                        continue
                    except Exception as err:
                        _LOGGER.exception("Reauth attempt to %s failed: %s", target_url, err)
                        errors["base"] = "unknown"
                        break

                if auth_result:
                    action, cookies, target_url = auth_result
                    if action == "success":
                        return self.async_update_reload_and_abort(
                            self._reauth_entry,
                            data={
                                **self._reauth_entry.data,
                                CONF_COOKIE: cookies,
                                CONF_USERNAME: username,
                                CONF_PASSWORD: password,
                                CONF_AUTH_SERVER_URL: target_url,
                            },
                        )
                    elif action == "mfa":
                        return await self.async_step_mfa()

                if not connected and not errors:
                    errors["base"] = "auth_server_unavailable"

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=default_username): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_MFA_METHOD, default=default_mfa): vol.In(
                    [MFA_METHOD_SMS, MFA_METHOD_EMAIL]
                ),
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"username": default_username},
        )

    async def async_step_automated(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 2a: Automated sign-in with username, password, and MFA channel."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "").strip()
            mfa_method = user_input.get(CONF_MFA_METHOD, DEFAULT_MFA_METHOD)
            auth_url = DEFAULT_AUTH_SERVER_URL

            if not username or not password:
                errors["base"] = "missing_credentials"
            else:
                candidate_urls = [auth_url]
                for fallback in ["http://10.0.2.52:8000", "http://127.0.0.1:8000"]:
                    if fallback not in candidate_urls:
                        candidate_urls.append(fallback)

                connected = False
                session = async_get_clientsession(self.hass)
                auth_result = None
                for target_url in candidate_urls:
                    try:
                        async with session.post(
                            f"{target_url}/login",
                            json={
                                "username": username,
                                "password": password,
                                "mfa_method": mfa_method,
                            },
                            timeout=aiohttp.ClientTimeout(total=90),
                        ) as resp:
                            connected = True
                            self.context["auth_url"] = target_url
                            self.context["username"] = username
                            self.context["password"] = password
                            if resp.status == 200:
                                res_json = await resp.json()
                                if res_json.get("success") and res_json.get("cookies"):
                                    auth_result = ("success", res_json["cookies"], target_url)
                                    break
                                elif res_json.get("mfa_required"):
                                    auth_result = ("mfa", None, target_url)
                                    break
                                else:
                                    _LOGGER.error("Auth helper response: %s", res_json)
                                    errors["base"] = "invalid_auth"
                                    break
                            else:
                                try:
                                    res_json = await resp.json()
                                except Exception:
                                    res_json = {}
                                if resp.status == 403 or res_json.get("recaptcha_blocked"):
                                    errors["base"] = "recaptcha_blocked"
                                elif resp.status == 500:
                                    _LOGGER.error("Auth helper returned 500: %s", res_json)
                                    errors["base"] = "auth_server_error"
                                else:
                                    err_text = await resp.text()
                                    _LOGGER.error("Auth helper returned status %s: %s", resp.status, err_text)
                                    errors["base"] = "invalid_auth"
                                break
                    except aiohttp.ClientConnectorError:
                        _LOGGER.debug("Could not reach auth server at %s", target_url)
                        continue
                    except Exception as err:
                        _LOGGER.exception("Error calling auth server at %s: %s", target_url, err)
                        errors["base"] = "unknown"
                        break

                if auth_result:
                    action, cookies, target_url = auth_result
                    if action == "success":
                        await self.async_set_unique_id(username.lower())
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"PSE&G ({username})",
                            data={
                                CONF_COOKIE: cookies,
                                CONF_USERNAME: username,
                                CONF_PASSWORD: password,
                                CONF_AUTH_SERVER_URL: target_url,
                            },
                        )
                    elif action == "mfa":
                        return await self.async_step_mfa()

                if not connected and not errors:
                    errors["base"] = "auth_server_unavailable"

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
            step_id="automated",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_mfa(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 3: Verification of 6-digit OTP code."""
        errors: Dict[str, str] = {}
        auth_url = self.context.get("auth_url", DEFAULT_AUTH_SERVER_URL)
        username = self.context.get("username", "")
        password = self.context.get("password", "")

        if user_input is not None:
            code = user_input.get(CONF_MFA_CODE, "").strip()
            if not code:
                errors["base"] = "invalid_code"
            else:
                mfa_success = False
                cookies = None
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{auth_url}/login/mfa",
                        json={"code": code},
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            if res_json.get("success") and res_json.get("cookies"):
                                cookies = res_json["cookies"]
                                mfa_success = True
                            else:
                                errors["base"] = "invalid_code"
                        else:
                            errors["base"] = "invalid_code"
                except Exception as err:
                    _LOGGER.exception("MFA verification error: %s", err)
                    errors["base"] = "unknown"

                if mfa_success and cookies:
                    if getattr(self, "_reauth_entry", None):
                        return self.async_update_reload_and_abort(
                            self._reauth_entry,
                            data={
                                **self._reauth_entry.data,
                                CONF_COOKIE: cookies,
                                CONF_USERNAME: username or self._reauth_entry.data.get(CONF_USERNAME),
                                CONF_PASSWORD: password or self._reauth_entry.data.get(CONF_PASSWORD),
                                CONF_AUTH_SERVER_URL: auth_url,
                            },
                        )
                    if username:
                        await self.async_set_unique_id(username.lower())
                        self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"PSE&G ({username})" if username else "PSE&G Energy",
                        data={
                            CONF_COOKIE: cookies,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_AUTH_SERVER_URL: auth_url,
                        },
                    )

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

    async def async_step_cookie(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Step 2b: Direct browser session cookie entry."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            cookie = user_input.get(CONF_COOKIE, "").strip()
            if not cookie:
                errors["base"] = "missing_credentials"
            else:
                cookie_valid = False
                try:
                    client = PsegClient(cookie)
                    await self.hass.async_add_executor_job(client.test_connection)
                    cookie_valid = True
                except PsegAuthError as err:
                    _LOGGER.error("Cookie validation error: %s", err)
                    errors["base"] = "invalid_cookie"
                except Exception as err:
                    _LOGGER.exception("Unexpected error validating cookie: %s", err)
                    errors["base"] = "unknown"

                if cookie_valid:
                    if getattr(self, "_reauth_entry", None):
                        return self.async_update_reload_and_abort(
                            self._reauth_entry,
                            data={
                                **self._reauth_entry.data,
                                CONF_COOKIE: cookie,
                            },
                        )
                    return self.async_create_entry(
                        title="PSE&G Energy",
                        data={
                            CONF_COOKIE: cookie,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_COOKIE): str,
            }
        )

        return self.async_show_form(
            step_id="cookie",
            data_schema=schema,
            errors=errors,
        )
