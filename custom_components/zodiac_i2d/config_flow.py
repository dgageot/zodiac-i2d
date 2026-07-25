"""Config flow for the Zodiac i2d integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZodiacApi, ZodiacAuthError, ZodiacError
from .const import DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
)

REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class ZodiacConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup and reauthentication."""

    VERSION = 1

    async def _async_validate(self, email: str, password: str) -> tuple[str, dict]:
        """Return (user_id, errors). Empty errors means success."""
        api = ZodiacApi(async_get_clientsession(self.hass), email, password)
        try:
            await api.login()
            robots = await api.async_get_robots()
        except ZodiacAuthError:
            return "", {"base": "invalid_auth"}
        except ZodiacError:
            return "", {"base": "cannot_connect"}
        if not robots:
            return "", {"base": "no_robots"}
        return str(api.user_id), {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            user_id, errors = await self._async_validate(
                email, user_input[CONF_PASSWORD]
            )
            if not errors:
                # Keyed on the account, so the same account cannot be added
                # twice even if the email is typed with different casing.
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=email, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            _, errors = await self._async_validate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={CONF_EMAIL: entry.data[CONF_EMAIL]},
            errors=errors,
        )
