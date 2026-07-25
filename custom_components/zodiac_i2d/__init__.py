"""Zodiac i2d pool robot integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZodiacApi, ZodiacAuthError, ZodiacError
from .const import PLATFORMS
from .coordinator import ZodiacCoordinator


@dataclass
class ZodiacData:
    """Runtime data stored on the config entry."""

    api: ZodiacApi
    coordinators: list[ZodiacCoordinator]


type ZodiacConfigEntry = ConfigEntry[ZodiacData]


async def async_setup_entry(hass: HomeAssistant, entry: ZodiacConfigEntry) -> bool:
    """Set up one iAqualink account."""
    api = ZodiacApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )

    try:
        await api.login()
        robots = await api.async_get_robots()
    except ZodiacAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ZodiacError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if not robots:
        # Nothing to do, and retrying will not help until the account changes.
        raise ConfigEntryNotReady("no i2d robots found on this account")

    coordinators = [
        ZodiacCoordinator(
            hass,
            entry,
            api,
            robot["serial_number"],
            robot.get("name") or robot["serial_number"],
        )
        for robot in robots
    ]
    for coordinator in coordinators:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ZodiacData(api=api, coordinators=coordinators)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZodiacConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
