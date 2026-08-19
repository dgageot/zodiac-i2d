"""Buttons for adjusting Zodiac i2d cleaning duration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ZodiacConfigEntry
from .api import REQUEST_DURATION_LONGER, REQUEST_DURATION_SHORTER
from .coordinator import ZodiacCoordinator
from .entity import ZodiacEntity


@dataclass(frozen=True, kw_only=True)
class ZodiacButtonDescription(ButtonEntityDescription):
    request: str


BUTTONS: tuple[ZodiacButtonDescription, ...] = (
    ZodiacButtonDescription(
        key="extend_duration",
        translation_key="extend_duration",
        icon="mdi:timer-plus-outline",
        request=REQUEST_DURATION_LONGER,
    ),
    ZodiacButtonDescription(
        key="shorten_duration",
        translation_key="shorten_duration",
        icon="mdi:timer-minus-outline",
        request=REQUEST_DURATION_SHORTER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZodiacConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        ZodiacDurationButton(coordinator, description)
        for coordinator in entry.runtime_data.coordinators
        for description in BUTTONS
    )


class ZodiacDurationButton(ZodiacEntity, ButtonEntity):
    """Adjusts the active cleaning cycle by one 30-minute step."""

    entity_description: ZodiacButtonDescription

    def __init__(
        self, coordinator: ZodiacCoordinator, description: ZodiacButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.can_adjust_duration

    async def async_press(self) -> None:
        await self.coordinator.async_adjust_duration(self.entity_description.request)
