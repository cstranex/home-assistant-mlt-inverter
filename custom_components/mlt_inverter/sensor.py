import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .mappings import DERIVED_POWER_SENSORS, ENERGY_SENSORS, SENSORS

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
        if _definition_available(definition, coordinator.data):
            sensors.append(MLTInverterEnergySensor(coordinator, entry, definition))

    for definition in DERIVED_POWER_SENSORS:
        if _definition_available(definition, coordinator.data):
            sensors.append(MLTInverterDerivedPowerSensor(coordinator, entry, definition))

    async_add_entities(sensors, True)


def _definition_available(definition: dict, data: list) -> bool:
    """Return True if all indexes required by a derived definition are present."""
    for key in (
        "power_idx",
        "subtract_idx",
        "load_idx",
        "grid_idx",
        "voltage_idx",
        "current_idx",
    ):
        idx = definition.get(key)
        if idx is not None and idx >= len(data):
            return False
    return True


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the shared device registry metadata for this inverter."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="MLT",
        model="Inverter",
    )


class MLTInverterSensor(CoordinatorEntity, SensorEntity):
    """Inverter Sensor"""

    def __init__(self, coordinator, entry: ConfigEntry, idx, definition) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.idx = idx
        self._item = coordinator.data[idx]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._attr_device_info = _device_info(entry)
        self._unit = None

        self._attr_device_class = definition["type"]
        self._attr_options = definition.get("options")
        if "options" not in definition:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        # Determine unit of measurement from the value string if possible.
        # The API uses 'C (apostrophe) for Celsius; map it to the HA standard °C.
        _UNIT_MAP = {
            "kW": "kW", "V": "V", "A": "A",
            "Hz": "Hz", "kVA": "kVA", "kVAR": "kVAR",
            "'C": "°C", "°C": "°C", "%": "%",
        }
        if self._item.get("Value"):
            value = self._item["Value"]
            if isinstance(value, str):
                for raw_unit, ha_unit in _UNIT_MAP.items():
                    if value.endswith(raw_unit):
                        self._attr_native_unit_of_measurement = ha_unit
                        self._unit = raw_unit  # keep raw for stripping in native_value
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
        self._power_idx = definition.get("power_idx")
        self._subtract_idx = definition.get("subtract_idx")
        self._load_idx = definition.get("load_idx")
        self._grid_idx = definition.get("grid_idx")
        self._voltage_idx = definition.get("voltage_idx")
        self._current_idx = definition.get("current_idx")
        self._current_positive_is = definition.get("current_positive_is", "discharge")
        self._calculation = definition.get("calculation")
        self._sign = definition["sign"]  # "positive", "negative", or "all"
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._attr_device_info = _device_info(entry)
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

    def _read_kw(self, idx: int) -> float | None:
        """Read a kW value from coordinator data by index."""
        try:
            item = self.coordinator.data[idx]
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

    def _read_number(self, idx: int, unit: str) -> float | None:
        """Read a numeric value with a suffix such as V or A from coordinator data."""
        try:
            item = self.coordinator.data[idx]
        except (IndexError, TypeError):
            return None
        if not item or "Value" not in item or not item["Value"]:
            return None
        value = item["Value"]
        if isinstance(value, str) and unit in value:
            try:
                return float(value.replace(unit, ""))
            except ValueError:
                return None
        return None

    def _get_power_kw(self) -> float | None:
        """Return signed battery power in kW from either a direct power or V*A source."""
        if self._calculation == "solar_balance":
            load = self._read_kw(self._load_idx)
            grid = self._read_kw(self._grid_idx)
            voltage = self._read_number(self._voltage_idx, "V")
            current = self._read_number(self._current_idx, "A")
            if None in (load, grid, voltage, current):
                return None
            battery_power = (voltage * current) / 1000
            battery_net = (
                -battery_power
                if self._current_positive_is == "charge"
                else battery_power
            )
            return load - grid - battery_net

        if self._voltage_idx is not None and self._current_idx is not None:
            voltage = self._read_number(self._voltage_idx, "V")
            current = self._read_number(self._current_idx, "A")
            if voltage is None or current is None:
                return None
            power = (voltage * current) / 1000
            # HA Energy expects positive discharge, negative charge.
            return -power if self._current_positive_is == "charge" else power

        power = self._read_kw(self._power_idx)
        if power is None:
            return None
        if self._subtract_idx is not None:
            subtract = self._read_kw(self._subtract_idx)
            if subtract is not None:
                power -= subtract
        return power

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


class MLTInverterDerivedPowerSensor(CoordinatorEntity, SensorEntity):
    """Instantaneous power sensor derived from one or two source sensors."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, definition: dict) -> None:
        super().__init__(coordinator)
        self._power_idx = definition.get("power_idx")
        self._subtract_idx = definition.get("subtract_idx")
        self._load_idx = definition.get("load_idx")
        self._grid_idx = definition.get("grid_idx")
        self._voltage_idx = definition.get("voltage_idx")
        self._current_idx = definition.get("current_idx")
        self._current_positive_is = definition.get("current_positive_is", "discharge")
        self._calculation = definition.get("calculation")
        self._mode = definition["mode"]
        self._attr_name = definition["name"]
        self._attr_unique_id = f"mlt_inverter_{entry.entry_id}_{definition['name']}"
        self._attr_device_info = _device_info(entry)

    def _read_kw(self, idx: int) -> float | None:
        """Read a kW value from coordinator data by index."""
        try:
            item = self.coordinator.data[idx]
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

    def _read_number(self, idx: int, unit: str) -> float | None:
        """Read a numeric value with a suffix such as V or A from coordinator data."""
        try:
            item = self.coordinator.data[idx]
        except (IndexError, TypeError):
            return None
        if not item or "Value" not in item or not item["Value"]:
            return None
        value = item["Value"]
        if isinstance(value, str) and unit in value:
            try:
                return float(value.replace(unit, ""))
            except ValueError:
                return None
        return None

    def _get_power_kw(self) -> float | None:
        """Return signed battery power in kW from either a direct power or V*A source."""
        if self._calculation == "solar_balance":
            load = self._read_kw(self._load_idx)
            grid = self._read_kw(self._grid_idx)
            voltage = self._read_number(self._voltage_idx, "V")
            current = self._read_number(self._current_idx, "A")
            if None in (load, grid, voltage, current):
                return None
            battery_power = (voltage * current) / 1000
            battery_net = (
                -battery_power
                if self._current_positive_is == "charge"
                else battery_power
            )
            return load - grid - battery_net

        if self._voltage_idx is not None and self._current_idx is not None:
            voltage = self._read_number(self._voltage_idx, "V")
            current = self._read_number(self._current_idx, "A")
            if voltage is None or current is None:
                return None
            power = (voltage * current) / 1000
            return -power if self._current_positive_is == "charge" else power

        power = self._read_kw(self._power_idx)
        if power is None:
            return None
        if self._subtract_idx is not None:
            subtract = self._read_kw(self._subtract_idx)
            if subtract is not None:
                power -= subtract
        return power

    @property
    def native_value(self) -> float | None:
        power = self._get_power_kw()
        if power is None:
            return None
        if self._mode == "positive":
            return round(max(0.0, power), 3)
        if self._mode == "negative":
            return round(max(0.0, -power), 3)
        return round(power, 3)
