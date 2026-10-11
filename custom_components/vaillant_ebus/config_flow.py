"""Config flow."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN
from .ebusd import EbusdClient, EbusdError


class VaillantEbusConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            try:
                await EbusdClient(user_input[CONF_HOST], user_input[CONF_PORT]).command("info")
            except EbusdError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=f"ebusd {user_input[CONF_HOST]}", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST): str, vol.Required(CONF_PORT, default=DEFAULT_PORT): int}
            ),
            errors=errors,
        )

