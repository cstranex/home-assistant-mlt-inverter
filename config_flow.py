from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.httpx_client import get_async_client

from .const import CONF_HOST, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN


class MltInverterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
