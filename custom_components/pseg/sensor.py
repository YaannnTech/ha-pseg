"""Sensors for the PSE&G Energy integration."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PSE&G sensor entries."""
    coordinator: PsegDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Migrate legacy entity unique IDs and entity IDs from 'yesterday' naming
    try:
        ent_reg = er.async_get(hass)
        migrations = [
            ("electricity_yesterday", "electricity_consumption"),
            ("electricity_cost_yesterday", "electricity_cost"),
            ("outdoor_temperature_yesterday", "outdoor_temperature"),
        ]
        for old_suffix, new_suffix in migrations:
            old_uid = f"{entry.entry_id}_{old_suffix}"
            new_uid = f"{entry.entry_id}_{new_suffix}"
            old_ent_id = ent_reg.async_get_entity_id("sensor", DOMAIN, old_uid)
            if old_ent_id:
                _LOGGER.info(
                    "Migrating entity %s (UID: %s) -> (UID: %s, Entity ID: sensor.pseg_%s)",
                    old_ent_id,
                    old_uid,
                    new_uid,
                    new_suffix,
                )
                ent_reg.async_update_entity(
                    old_ent_id,
                    new_unique_id=new_uid,
                    new_entity_id=f"sensor.pseg_{new_suffix}",
                )
    except Exception as err:
        _LOGGER.warning("Could not run entity registry migration: %s", err)

    entities = [
        PsegElectricityConsumptionSensor(coordinator, entry),
        PsegElectricityCostSensor(coordinator, entry),
        PsegElectricityMeterSensor(coordinator, entry),
        PsegElectricityLatestDateSensor(coordinator, entry),
        PsegTemperatureSensor(coordinator, entry),
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
            manufacturer="Public Service Enterprise Group",
            model="Smart AMI Meter",
        )
        self.entity_id = f"sensor.pseg_{key}"


class PsegElectricityConsumptionSensor(PsegBaseSensor):
    """Sensor for electricity consumption in kWh."""

    _attr_name = "Electricity Consumption"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_consumption")

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


class PsegElectricityCostSensor(PsegBaseSensor):
    """Sensor for electricity cost in USD."""

    _attr_name = "Electricity Cost"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "USD"
    _attr_icon = "mdi:currency-usd"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "electricity_cost")

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


class PsegTemperatureSensor(PsegBaseSensor):
    """Sensor for the outdoor average temperature."""

    _attr_name = "Outdoor Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_icon = "mdi:thermometer"

    def __init__(self, coordinator: PsegDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "outdoor_temperature")

    @property
    def native_value(self) -> Optional[float]:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("temperature_avg")
