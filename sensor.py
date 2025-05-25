import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .mappings import SENSORS

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
) -> None:
    """Set up the sensor platform."""
    if discovery_info is None:
        return

    coordinator = hass.data[DOMAIN]["coordinator"]

    sensors = []
    for idx, _ in enumerate(coordinator.data):
        sensors.append(MLTInverterSensor(coordinator, idx))

    async_add_entities(sensors, True)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Your System sensor based on a config entry."""
    coordinator = hass.data[DOMAIN]["coordinator"]

    # Create sensors for each item in the JSON response
    sensors = []
    for idx, item in enumerate(coordinator.data):
        if idx not in SENSORS:
            continue
        definition = SENSORS[idx]
        sensors.append(MLTInverterSensor(coordinator, idx, definition))

    async_add_entities(sensors, True)


class MLTInverterSensor(CoordinatorEntity, SensorEntity):
    """ "Inverter Sensor"""

    def __init__(self, coordinator, idx, definition) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.idx = idx
        self._item = coordinator.data[idx]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{definition['name']}"
        self._unit = None

        self._attr_device_class = definition["type"]
        self._attr_options = definition.get("options")
        if "options" not in definition:
            self._attr_state_class = "measurement"

        # Determine unit of measurement from the value string if possible
        if self._item.get("Value"):
            value = self._item["Value"]
            if isinstance(value, str):
                # Extract unit from strings like "0.1kW", "236.7V", etc.
                for unit in ["kW", "V", "A", "Hz", "kVA", "kVAR", "'C", "%"]:
                    if value.endswith(unit):
                        self._attr_native_unit_of_measurement = unit
                        self._unit = unit
                        break

    @property
    def state(self):
        """Return the state of the sensor."""
        self._item = self.coordinator.data[self.idx]

        if "Value" not in self._item or not self._item["Value"]:
            return None

        value = self._item["Value"]

        # For numeric values with units, extract just the number
        if isinstance(value, str) and self._unit and self._unit in value:
            return float(value.replace(self._unit, ""))

        return value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        self._item = self.coordinator.data[self.idx]

        attributes = {
            "min": self._item.get("Min"),
            "max": self._item.get("Max"),
            "decimals": self._item.get("Decimals"),
            "item_index": self._item.get("Item Index"),
        }

        return attributes
