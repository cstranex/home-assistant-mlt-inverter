import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .mappings import ENERGY_SENSORS, SENSORS

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

    for definition in ENERGY_SENSORS:
        if definition["power_idx"] < len(coordinator.data):
            sensors.append(MLTInverterEnergySensor(coordinator, entry, definition))

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


class MLTInverterEnergySensor(CoordinatorEntity, SensorEntity, RestoreEntity):
    """Energy sensor that integrates a power sensor (kW) over time to produce kWh totals.

    Suitable for use with the HA Energy dashboard.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, entry: ConfigEntry, definition: dict) -> None:
        super().__init__(coordinator)
        self._power_idx = definition["power_idx"]
        self._sign = definition["sign"]  # "positive", "negative", or "all"
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._accumulated: float = 0.0
        self._last_update = dt_util.utcnow()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in (None, "unknown", "unavailable"):
            try:
                self._accumulated = float(state.state)
            except ValueError:
                pass
        # Reset the clock so the first coordinator tick doesn't count stale time.
        self._last_update = dt_util.utcnow()

    def _get_power_kw(self) -> float | None:
        """Extract the current power reading in kW from coordinator data."""
        try:
            item = self.coordinator.data[self._power_idx]
        except (IndexError, TypeError):
            return None

        if not item or "Value" not in item or not item["Value"]:
            return None

        value = item["Value"]
        if isinstance(value, str) and "kW" in value:
            try:
                return float(value.replace("kW", ""))
            except ValueError:
                return None
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        now = dt_util.utcnow()
        power = self._get_power_kw()

        if power is not None:
            delta_hours = (now - self._last_update).total_seconds() / 3600

            if self._sign == "positive":
                energy_delta = max(0.0, power) * delta_hours
            elif self._sign == "negative":
                energy_delta = max(0.0, -power) * delta_hours
            else:  # "all"
                energy_delta = abs(power) * delta_hours

            self._accumulated += energy_delta

        self._last_update = now
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._accumulated, 3)
