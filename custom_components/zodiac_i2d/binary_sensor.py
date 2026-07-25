"""Binary sensors for Zodiac i2d robots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZodiacConfigEntry
from .coordinator import ZodiacCoordinator
from .entity import ZodiacEntity
from .frame import Frame


@dataclass(frozen=True, kw_only=True)
class ZodiacBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[Frame], bool]


BINARY_SENSORS: tuple[ZodiacBinarySensorDescription, ...] = (
    ZodiacBinarySensorDescription(
        key="canister_full",
        translation_key="canister_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda f: f.canister_full,
    ),
    ZodiacBinarySensorDescription(
        key="error",
        translation_key="error_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda f: f.has_error,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZodiacConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZodiacBinarySensor(coordinator, description)
        for coordinator in entry.runtime_data.coordinators
        for description in BINARY_SENSORS
    )


class ZodiacBinarySensor(ZodiacEntity, BinarySensorEntity):
    """A boolean flag decoded from the status frame."""

    entity_description: ZodiacBinarySensorDescription

    def __init__(
        self,
        coordinator: ZodiacCoordinator,
        description: ZodiacBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, f"binary_{description.key}")
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        frame = self.coordinator.data
        if frame is None:
            return None
        return self.entity_description.value_fn(frame)
