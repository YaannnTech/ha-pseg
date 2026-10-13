"""Sensors for the PSE&G Energy integration."""

from __future__ import annotations

from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_HISTORY_14D,
    ATTR_LATEST_COST,
    ATTR_LATEST_DATE,
    ATTR_METER,
    ATTR_PREVIOUS_COST,
    ATTR_PREVIOUS_DATE,
    ATTR_PREVIOUS_KWH,
    ATTR_TEMPERATURE_AVG,
    ATTR_TEMPERATURE_HIGH,
    ATTR_TEMPERATURE_LOW,
    DOMAIN,
)
from .coordinator import PsegDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PSE&G sensor entries."""
    coordinator: PsegDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        PsegElectricityYesterdaySensor(coordinator, entry),
        PsegElectricityCostYesterdaySensor(coordinator, entry),
        PsegElectricityMeterSensor(coordinator, entry),
        PsegElectricityLatestDateSensor(coordinator, entry),
        PsegTemperatureYesterdaySensor(coordinator, entry),
    ]

    async_add_entities(entities)


class PsegBaseSensor(CoordinatorEntity[PsegDataUpdateCoordinator], SensorEntity):
    """Base sensor for PSE&G integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PsegDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="PSE&G",
            manufacturer="PSE&G",
            model="MyMeter AMI",
        )
        self.entity_id = f"sensor.pseg_{key}"


class PsegElectricityYesterdaySensor(PsegBaseSensor):
    """Sensor for yesterday's electricity consumption in kWh."""

    _attr_name = "Electricity Yesterday"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_yesterday")

    @property
    def native_value(self) -> Optional[float]:
        """Return the consumption in kWh."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latest_kwh")

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return full history and context attributes for the custom card."""
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        return {
            ATTR_METER: data.get("meter"),
            ATTR_LATEST_DATE: data.get("latest_date"),
            ATTR_PREVIOUS_DATE: data.get("previous_date"),
            ATTR_PREVIOUS_KWH: data.get("previous_kwh"),
            ATTR_PREVIOUS_COST: data.get("previous_cost"),
            ATTR_LATEST_COST: data.get("latest_cost"),
            ATTR_HISTORY_14D: data.get("history_14d", []),
            "last_updated": data.get("last_updated"),
            "temperature_range": data.get("temperature_range"),
        }


class PsegElectricityCostYesterdaySensor(PsegBaseSensor):
    """Sensor for yesterday's electricity cost in USD."""

    _attr_name = "Electricity Cost Yesterday"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_cost_yesterday")

    @property
    def native_value(self) -> Optional[float]:
        """Return the cost in dollars."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latest_cost")


class PsegElectricityMeterSensor(PsegBaseSensor):
    """Sensor for the meter ID/description."""

    _attr_name = "Electricity Meter ID"
    _attr_icon = "mdi:meter-electric"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_meter_id")

    @property
    def native_value(self) -> Optional[str]:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("meter")


class PsegElectricityLatestDateSensor(PsegBaseSensor):
    """Sensor for the latest reading date."""

    _attr_name = "Electricity Latest Date"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_latest_date")

    @property
    def native_value(self) -> Optional[str]:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latest_date")


class PsegTemperatureYesterdaySensor(PsegBaseSensor):
    """Sensor for the outdoor average temperature."""

    _attr_name = "Outdoor Temperature Yesterday"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "outdoor_temperature_yesterday")

    @property
    def native_value(self) -> Optional[float]:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("temperature_avg")
