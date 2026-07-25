"""Shared entity base for Zodiac i2d robots."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ZodiacCoordinator


class ZodiacEntity(CoordinatorEntity[ZodiacCoordinator]):
    """Base class wiring entities to one robot's device entry."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZodiacCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{key}"

        frame = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            name=coordinator.robot_name,
            manufacturer=MANUFACTURER,
            # The commercial model name is not retrievable for this family:
            # the prod.zodiac-io.com features endpoint answers "Device does
            # not belong to user" because i2d robots are only registered on
            # the legacy host. The hardware id is the best identifier we have.
            model=f"i2d robot (hw {frame.hardware_id})" if frame else "i2d robot",
            sw_version=frame.firmware_id if frame else None,
            serial_number=coordinator.serial,
        )
