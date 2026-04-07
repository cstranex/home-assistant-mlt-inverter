import logging
import re

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .mappings import SETTINGS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator = hass.data[DOMAIN][f"{entry.entry_id}_settings"]

    entities = [
        MLTInverterNumber(coordinator, entry, idx, definition)
        for idx, definition in SETTINGS.items()
        if definition["type"] == "number" and idx < len(coordinator.data)
    ]
    async_add_entities(entities, True)


def _parse_float(value) -> float | None:
    """Extract the leading number from a value string like '4.0kW', '85%', '10h00'."""
    if value is None:
        return None
    match = re.match(r"^(-?[\d.]+)", str(value))
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


class MLTInverterNumber(CoordinatorEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator, entry: ConfigEntry, idx: int, definition: dict
    ) -> None:
        super().__init__(coordinator)
        self.idx = idx
        self._attr_name = definition["description"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        unit = definition.get("unit")
        self._attr_native_unit_of_measurement = unit if unit is not None else None
        self._hint = definition.get("hint")

        item = coordinator.data[idx]
        try:
            self._decimals = int(item.get("Decimals") or 0)
        except (TypeError, ValueError):
            self._decimals = 0

        scale = 10**self._decimals
        self._attr_native_step = 1.0 / scale if self._decimals > 0 else 1.0

        # Min/Max from the API are raw integers scaled by 10^decimals.
        try:
            self._attr_native_min_value = float(item.get("Min") or 0) / scale
        except (TypeError, ValueError):
            self._attr_native_min_value = 0.0

        try:
            raw_max = item.get("Max")
            self._attr_native_max_value = float(raw_max) / scale if raw_max is not None else 100.0
        except (TypeError, ValueError):
            self._attr_native_max_value = 100.0

    @property
    def native_value(self) -> float | None:
        return _parse_float(self.coordinator.data[self.idx].get("Value"))

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {}
        if self._hint:
            attrs["hint"] = self._hint
        return attrs

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value * (10**self._decimals)))
        await self.coordinator.async_write_setting(self.idx, raw)
