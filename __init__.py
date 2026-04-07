"""The MLT Inverter integration."""

from __future__ import annotations

import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOST, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MLT Inverter from a config entry."""
    host = entry.data[CONF_HOST]
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    coordinator = InverterCoordinator(hass, host, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


class InverterCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, host: str, scan_interval: int) -> None:
        """Initialize."""
        self.host = host
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=datetime.timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        url = f"http://{self.host}:81/testdata"
        try:
            client = get_async_client(self.hass)
            response = await client.post(url, data="dat", timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as err:
            raise UpdateFailed(f"Error fetching inverter data: {err}") from err
