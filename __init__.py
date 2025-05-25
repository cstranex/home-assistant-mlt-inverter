"""The MLT Inverter integration."""

from __future__ import annotations

import datetime
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_HOST, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_PLATFORMS: list[Platform] = ["sensor"]

_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_HOST): cv.string,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): cv.positive_int,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Your System from a config entry."""
    host = entry.data[CONF_HOST]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = InverterCoordinator(hass, host, scan_interval)
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(DOMAIN, {})["coordinator"] = coordinator

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, _PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop("coordinator", None)
    return unload_ok


class InverterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, scan_interval):
        """Initialize."""
        self.host = host
        self.hass = hass
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        return await self._fetch_data()

    async def _fetch_data(self):
        """Fetch data from the API."""
        url = f"http://{self.host}:81/testdata"

        client = get_async_client(self.hass)
        response = await client.post(url, data="dat", timeout=30)
        response.raise_for_status()

        return response.json()
