from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    CONF_HOST,
    CONF_PASSCODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_PASSCODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class MltInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MltInverterOptionsFlow:
        """Create the options flow."""
        return MltInverterOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            try:
                client = get_async_client(self.hass)
                url = f"http://{host}:81/testdata"
                response = await client.post(url, data="dat", timeout=10)
                response.raise_for_status()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=host, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                vol.Optional(CONF_PASSCODE, default=DEFAULT_PASSCODE): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class MltInverterOptionsFlow(config_entries.OptionsFlow):
    """Handle MLT Inverter options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_HOST,
                    default=self._config_entry.options.get(
                        CONF_HOST, self._config_entry.data[CONF_HOST]
                    ),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=self._config_entry.options.get(
                        CONF_SCAN_INTERVAL,
                        self._config_entry.data.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ),
                ): int,
                vol.Optional(
                    CONF_PASSCODE,
                    default=self._config_entry.options.get(
                        CONF_PASSCODE,
                        self._config_entry.data.get(CONF_PASSCODE, DEFAULT_PASSCODE),
                    ),
                ): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
