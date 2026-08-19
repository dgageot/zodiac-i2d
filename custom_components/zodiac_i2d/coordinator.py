"""Update coordinator for Zodiac i2d robots."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ZodiacApi, ZodiacAuthError, ZodiacError, ZodiacOfflineError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .frame import Frame, FrameError, parse_frame

_LOGGER = logging.getLogger(__name__)


class ZodiacCoordinator(DataUpdateCoordinator[Frame | None]):
    """Polls one robot and exposes the decoded frame.

    ``data`` is ``None`` when the robot is reachable but not answering, which
    happens whenever it is powered off or asleep on its dock. Entities stay
    available in that case and report unknown values, because "asleep" is a
    normal state for a pool cleaner rather than an error.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: ZodiacApi,
        serial: str,
        name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {serial}",
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
        )
        self.api = api
        self.serial = serial
        self.robot_name = name
        self._command_lock = asyncio.Lock()

    @property
    def can_adjust_duration(self) -> bool:
        """Return whether the active cycle can be adjusted."""
        frame = self.data
        return (
            self.last_update_success
            and frame is not None
            and frame.is_cleaning
            and not frame.has_error
        )

    async def _async_update_data(self) -> Frame | None:
        try:
            payload = await self.api.async_read_status(self.serial)
        except ZodiacAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ZodiacOfflineError:
            return None
        except ZodiacError as err:
            raise UpdateFailed(str(err)) from err

        if not payload:
            return None

        try:
            return parse_frame(payload)
        except FrameError as err:
            raise UpdateFailed(f"could not decode status frame: {err}") from err

    async def async_send(self, request: str) -> None:
        """Send a command, then refresh so the UI reflects the new state."""
        await self._async_send(request, require_active_cycle=False)

    async def async_adjust_duration(self, request: str) -> None:
        """Adjust the duration of the active cleaning cycle."""
        await self._async_send(request, require_active_cycle=True)

    async def _async_send(self, request: str, *, require_active_cycle: bool) -> None:
        async with self._command_lock:
            if require_active_cycle:
                await self.async_refresh()
                if not self.can_adjust_duration:
                    raise ServiceValidationError(
                        translation_domain=DOMAIN,
                        translation_key="inactive_cleaning_cycle",
                    )

            try:
                await self.api.async_send(self.serial, request)
            except ZodiacAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except ZodiacError as err:
                await self.async_refresh()
                raise HomeAssistantError(str(err)) from err
            await self.async_refresh()
