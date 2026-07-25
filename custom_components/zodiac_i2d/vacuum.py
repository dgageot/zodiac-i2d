"""Vacuum entity for Zodiac i2d robots."""

from __future__ import annotations

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZodiacConfigEntry
from .api import REQUEST_RETURN_HOME, REQUEST_START, REQUEST_STOP
from .coordinator import ZodiacCoordinator
from .entity import ZodiacEntity
from .frame import MODE_COMMANDS

# Mapping from decoded state name to Home Assistant activity. Errors are
# handled before this lookup, since the error byte is independent of state.
_ACTIVITY_MAP = {
    "idle": VacuumActivity.IDLE,
    "starting": VacuumActivity.CLEANING,
    "cleaning": VacuumActivity.CLEANING,
    "finished": VacuumActivity.DOCKED,
    "paused": VacuumActivity.PAUSED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZodiacConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZodiacVacuum(coordinator) for coordinator in entry.runtime_data.coordinators
    )


class ZodiacVacuum(ZodiacEntity, StateVacuumEntity):
    """Controls one i2d robot."""

    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.STATE
    )
    _attr_fan_speed_list = list(MODE_COMMANDS)

    def __init__(self, coordinator: ZodiacCoordinator) -> None:
        super().__init__(coordinator, "vacuum")

    @property
    def activity(self) -> VacuumActivity | None:
        frame = self.coordinator.data
        if frame is None:
            # Powered off or asleep on the dock, which is not an error.
            return None
        if frame.has_error:
            return VacuumActivity.ERROR
        return _ACTIVITY_MAP.get(frame.state)

    @property
    def fan_speed(self) -> str | None:
        frame = self.coordinator.data
        if frame is None:
            return None
        # Only the three commandable modes are valid fan speeds; a custom mode
        # read back from the robot is reported as None rather than an invalid
        # value Home Assistant would reject.
        return frame.mode if frame.mode in MODE_COMMANDS else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        frame = self.coordinator.data
        if frame is None:
            return {}
        return {
            "state_detail": frame.state,
            "mode": frame.mode,
            "error": frame.error,
            "canister_full": frame.canister_full,
            "minutes_remaining": frame.minutes_remaining,
            "hardware_id": frame.hardware_id,
            "firmware_id": frame.firmware_id,
            "raw_frame": frame.raw,
        }

    async def async_start(self) -> None:
        await self.coordinator.async_send(REQUEST_START)

    async def async_stop(self, **kwargs: object) -> None:
        await self.coordinator.async_send(REQUEST_STOP)

    async def async_pause(self) -> None:
        # The i2d protocol has no pause command; stopping is the closest
        # equivalent and matches what the cleaner's own UI does.
        await self.coordinator.async_send(REQUEST_STOP)

    async def async_return_to_base(self, **kwargs: object) -> None:
        await self.coordinator.async_send(REQUEST_RETURN_HOME)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: object) -> None:
        request = MODE_COMMANDS.get(fan_speed)
        if request is None:
            raise ValueError(f"unsupported fan speed: {fan_speed}")
        await self.coordinator.async_send(request)
