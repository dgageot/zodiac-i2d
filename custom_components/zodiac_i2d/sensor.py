"""Sensors for Zodiac i2d robots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZodiacConfigEntry
from .coordinator import ZodiacCoordinator
from .entity import ZodiacEntity
from .frame import ERROR_MAP, MODE_MAP, STATE_MAP, Frame


@dataclass(frozen=True, kw_only=True)
class ZodiacSensorDescription(SensorEntityDescription):
    """Describes a sensor and how to read it off a decoded frame."""

    value_fn: Callable[[Frame], str | int | None]


SENSORS: tuple[ZodiacSensorDescription, ...] = (
    ZodiacSensorDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(STATE_MAP.values())),
        # An unmapped state code would not be a valid enum option, so it is
        # reported as unknown rather than breaking the entity.
        value_fn=lambda f: f.state if f.state in set(STATE_MAP.values()) else None,
    ),
    ZodiacSensorDescription(
        key="error",
        translation_key="error",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(ERROR_MAP.values())),
        value_fn=lambda f: f.error if f.error in set(ERROR_MAP.values()) else None,
    ),
    ZodiacSensorDescription(
        key="mode",
        translation_key="mode",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(MODE_MAP.values())),
        value_fn=lambda f: f.mode if f.mode in set(MODE_MAP.values()) else None,
    ),
    ZodiacSensorDescription(
        key="minutes_remaining",
        translation_key="minutes_remaining",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda f: f.minutes_remaining,
    ),
    # The two counters below are exposed as diagnostics under neutral names:
    # they are confirmed to increase, but their exact meaning is unresolved
    # (see frame.py). Naming them "total hours" or "uptime" would be a guess.
    ZodiacSensorDescription(
        key="hour_counter",
        translation_key="hour_counter",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda f: f.hour_counter,
    ),
    ZodiacSensorDescription(
        key="minute_counter",
        translation_key="minute_counter",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda f: f.minute_counter,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZodiacConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZodiacSensor(coordinator, description)
        for coordinator in entry.runtime_data.coordinators
        for description in SENSORS
    )


class ZodiacSensor(ZodiacEntity, SensorEntity):
    """One decoded field of the status frame."""

    entity_description: ZodiacSensorDescription

    def __init__(
        self, coordinator: ZodiacCoordinator, description: ZodiacSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        frame = self.coordinator.data
        if frame is None:
            return None
        return self.entity_description.value_fn(frame)
