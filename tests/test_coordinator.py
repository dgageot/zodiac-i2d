"""Tests for command error translation."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock


class ConfigEntryAuthFailed(Exception):
    pass


class HomeAssistantError(Exception):
    pass


class UpdateFailed(Exception):
    pass


class DataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, *args, **kwargs):
        pass

    async def async_request_refresh(self):
        pass


homeassistant = types.ModuleType("homeassistant")
config_entries = types.ModuleType("homeassistant.config_entries")
config_entries.ConfigEntry = object
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
exceptions = types.ModuleType("homeassistant.exceptions")
exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed
exceptions.HomeAssistantError = HomeAssistantError
helpers = types.ModuleType("homeassistant.helpers")
update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
update_coordinator.UpdateFailed = UpdateFailed
sys.modules.update(
    {
        "homeassistant": homeassistant,
        "homeassistant.config_entries": config_entries,
        "homeassistant.core": core,
        "homeassistant.exceptions": exceptions,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.update_coordinator": update_coordinator,
    }
)

package_name = "zodiac_i2d_test"
package = types.ModuleType(package_name)
package.__path__ = []
sys.modules[package_name] = package

api_module = types.ModuleType(f"{package_name}.api")


class ZodiacError(Exception):
    pass


class ZodiacAuthError(ZodiacError):
    pass


class ZodiacOfflineError(ZodiacError):
    pass


api_module.ZodiacApi = object
api_module.ZodiacError = ZodiacError
api_module.ZodiacAuthError = ZodiacAuthError
api_module.ZodiacOfflineError = ZodiacOfflineError
sys.modules[api_module.__name__] = api_module

const_module = types.ModuleType(f"{package_name}.const")
const_module.DEFAULT_SCAN_INTERVAL = 30
const_module.DOMAIN = "zodiac_i2d"
sys.modules[const_module.__name__] = const_module

frame_module = types.ModuleType(f"{package_name}.frame")
frame_module.Frame = object
frame_module.FrameError = ValueError
frame_module.parse_frame = lambda payload: payload
sys.modules[frame_module.__name__] = frame_module

module_path = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zodiac_i2d"
    / "coordinator.py"
)
spec = importlib.util.spec_from_file_location(
    f"{package_name}.coordinator", module_path
)
assert spec is not None
assert spec.loader is not None
coordinator_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = coordinator_module
spec.loader.exec_module(coordinator_module)


class TestCommandErrors(unittest.IsolatedAsyncioTestCase):
    def coordinator_with_error(self, error):
        coordinator = coordinator_module.ZodiacCoordinator.__new__(
            coordinator_module.ZodiacCoordinator
        )
        coordinator.api = types.SimpleNamespace(async_send=AsyncMock(side_effect=error))
        coordinator.serial = "serial"
        coordinator.async_request_refresh = AsyncMock()
        return coordinator

    async def test_translates_transport_error(self):
        coordinator = self.coordinator_with_error(ZodiacError("cloud failed"))

        with self.assertRaisesRegex(HomeAssistantError, "cloud failed"):
            await coordinator.async_send("command")

        coordinator.async_request_refresh.assert_not_awaited()

    async def test_preserves_authentication_failure(self):
        coordinator = self.coordinator_with_error(ZodiacAuthError("expired"))

        with self.assertRaisesRegex(ConfigEntryAuthFailed, "expired"):
            await coordinator.async_send("command")


if __name__ == "__main__":
    unittest.main()
