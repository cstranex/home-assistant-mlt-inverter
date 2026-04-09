import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .mappings import SETTINGS

_LOGGER = logging.getLogger(__name__)

_OPTIONS = ["No", "Yes"]


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the shared device registry metadata for this inverter."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="MLT",
        model="Inverter",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator = hass.data[DOMAIN][f"{entry.entry_id}_settings"]

    entities = [
        MLTInverterSelect(coordinator, entry, idx, definition)
        for idx, definition in SETTINGS.items()
        if definition["type"] == "select" and idx < len(coordinator.data)
    ]
    async_add_entities(entities, True)


class MLTInverterSelect(CoordinatorEntity, SelectEntity):
    _attr_options = _OPTIONS

    def __init__(
        self, coordinator, entry: ConfigEntry, idx: int, definition: dict
    ) -> None:
        super().__init__(coordinator)
        self.idx = idx
        self._attr_name = definition["description"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._attr_device_info = _device_info(entry)
        self._hint = definition.get("hint")

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data[self.idx].get("Value")
        if value in _OPTIONS:
            return value
        # Fallback: treat truthy raw values as "Yes"
        if value in (1, "1", True):
            return "Yes"
        if value in (0, "0", False):
            return "No"
        return None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        if self._hint:
            attrs["hint"] = self._hint
        return attrs

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write_setting(self.idx, _OPTIONS.index(option))
