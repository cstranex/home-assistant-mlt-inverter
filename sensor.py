import logging

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .mappings import SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up MLT Inverter sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    for idx, item in enumerate(coordinator.data):
        if idx not in SENSORS:
            continue
        definition = SENSORS[idx]
        sensors.append(MLTInverterSensor(coordinator, entry, idx, definition))

    async_add_entities(sensors, True)


class MLTInverterSensor(CoordinatorEntity, SensorEntity):
    """Inverter Sensor"""

    def __init__(self, coordinator, entry: ConfigEntry, idx, definition) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.idx = idx
        self._item = coordinator.data[idx]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._unit = None

        self._attr_device_class = definition["type"]
        self._attr_options = definition.get("options")
        if "options" not in definition:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        # Determine unit of measurement from the value string if possible
        if self._item.get("Value"):
            value = self._item["Value"]
            if isinstance(value, str):
                # Extract unit from strings like "0.1kW", "236.7V", etc.
                for unit in ["kW", "V", "A", "Hz", "kVA", "kVAR", "°C", "%"]:
                    if value.endswith(unit):
                        self._attr_native_unit_of_measurement = unit
                        self._unit = unit
                        break

    @property
    def native_value(self):
        """Return the state of the sensor."""
        self._item = self.coordinator.data[self.idx]

        if "Value" not in self._item or not self._item["Value"]:
            return None

        value = self._item["Value"]

        # For numeric values with units, extract just the number
        if isinstance(value, str) and self._unit and self._unit in value:
            try:
                return float(value.replace(self._unit, ""))
            except ValueError:
                return None

        return value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        item = self.coordinator.data[self.idx]

        return {
            "min": item.get("Min"),
            "max": item.get("Max"),
            "decimals": item.get("Decimals"),
            "item_index": item.get("Item Index"),
        }
