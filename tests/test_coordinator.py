"""Tests for command error translation."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class ConfigEntryAuthFailed(Exception):
    pass


class HomeAssistantError(Exception):
    pass


class ServiceValidationError(HomeAssistantError):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.translation_domain = kwargs.get("translation_domain")
        self.translation_key = kwargs.get("translation_key")


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
exceptions.ServiceValidationError = ServiceValidationError
helpers = types.ModuleType("homeassistant.helpers")
update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")
update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
update_coordinator.UpdateFailed = UpdateFailed
homeassistant_modules = {
    "homeassistant": homeassistant,
    "homeassistant.config_entries": config_entries,
    "homeassistant.core": core,
    "homeassistant.exceptions": exceptions,
    "homeassistant.helpers": helpers,
    "homeassistant.helpers.update_coordinator": update_coordinator,
}

package_name = "zodiac_i2d_test"
package = types.ModuleType(package_name)
package.__path__ = []

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

const_module = types.ModuleType(f"{package_name}.const")
const_module.DEFAULT_SCAN_INTERVAL = 30
const_module.DOMAIN = "zodiac_i2d"

frame_module = types.ModuleType(f"{package_name}.frame")
frame_module.Frame = object
frame_module.FrameError = ValueError
frame_module.parse_frame = lambda payload: payload

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
modules = {
    **homeassistant_modules,
    package_name: package,
    api_module.__name__: api_module,
    const_module.__name__: const_module,
    frame_module.__name__: frame_module,
    spec.name: coordinator_module,
}
with patch.dict(sys.modules, modules):
    spec.loader.exec_module(coordinator_module)


class TestCommandErrors(unittest.IsolatedAsyncioTestCase):
    def coordinator_with_error(self, error):
        coordinator = coordinator_module.ZodiacCoordinator.__new__(
            coordinator_module.ZodiacCoordinator
        )
        coordinator.api = types.SimpleNamespace(async_send=AsyncMock(side_effect=error))
        coordinator.serial = "serial"
        coordinator._command_lock = asyncio.Lock()
        coordinator.async_refresh = AsyncMock()
        return coordinator

    async def test_translates_transport_error(self):
        coordinator = self.coordinator_with_error(ZodiacError("cloud failed"))

        with self.assertRaisesRegex(HomeAssistantError, "cloud failed"):
            await coordinator.async_send("command")

        coordinator.async_refresh.assert_awaited_once()

    async def test_reconciles_after_transport_error(self):
        coordinator = self.coordinator_with_error(ZodiacError("cloud failed"))

        with self.assertRaises(HomeAssistantError):
            await coordinator.async_send("command")

        coordinator.async_refresh.assert_awaited_once()

    async def test_preserves_authentication_failure(self):
        coordinator = self.coordinator_with_error(ZodiacAuthError("expired"))

        with self.assertRaisesRegex(ConfigEntryAuthFailed, "expired"):
            await coordinator.async_send("command")


class TestDurationAdjustment(unittest.IsolatedAsyncioTestCase):
    def coordinator(self, *, cleaning=True, has_error=False, update_success=True):
        coordinator = coordinator_module.ZodiacCoordinator.__new__(
            coordinator_module.ZodiacCoordinator
        )
        coordinator.api = types.SimpleNamespace(
            async_send=AsyncMock(return_value="ack")
        )
        coordinator.serial = "serial"
        coordinator._command_lock = asyncio.Lock()
        coordinator.data = types.SimpleNamespace(
            is_cleaning=cleaning,
            has_error=has_error,
        )
        coordinator.last_update_success = update_success
        coordinator.async_refresh = AsyncMock()
        return coordinator

    async def test_active_cycle_adjusts_after_preflight_refresh(self):
        coordinator = self.coordinator()

        await coordinator.async_adjust_duration("0A1301")

        coordinator.api.async_send.assert_awaited_once_with("serial", "0A1301")
        self.assertEqual(coordinator.async_refresh.await_count, 2)

    async def test_preflight_uses_refreshed_state(self):
        coordinator = self.coordinator()

        async def refresh():
            coordinator.data = types.SimpleNamespace(
                is_cleaning=False,
                has_error=False,
            )

        coordinator.async_refresh.side_effect = refresh

        with self.assertRaises(ServiceValidationError):
            await coordinator.async_adjust_duration("0A1301")

        coordinator.api.async_send.assert_not_awaited()

    async def test_rejects_inactive_cycle(self):
        coordinator = self.coordinator(cleaning=False)

        with self.assertRaises(ServiceValidationError) as raised:
            await coordinator.async_adjust_duration("0A1301")

        self.assertEqual(raised.exception.translation_domain, "zodiac_i2d")
        self.assertEqual(raised.exception.translation_key, "inactive_cleaning_cycle")
        coordinator.api.async_send.assert_not_awaited()
        coordinator.async_refresh.assert_awaited_once()

    async def test_rejects_cycle_with_error(self):
        coordinator = self.coordinator(has_error=True)

        with self.assertRaises(ServiceValidationError):
            await coordinator.async_adjust_duration("0A1300")

        coordinator.api.async_send.assert_not_awaited()

    async def test_serializes_mutating_commands(self):
        coordinator = self.coordinator()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        calls = []

        async def send(serial, request):
            calls.append(request)
            if request == "first":
                first_started.set()
                await release_first.wait()
            return "ack"

        coordinator.api.async_send.side_effect = send

        first = asyncio.create_task(coordinator.async_send("first"))
        await first_started.wait()
        second = asyncio.create_task(coordinator.async_send("second"))
        await asyncio.sleep(0)
        self.assertEqual(calls, ["first"])

        release_first.set()
        await asyncio.gather(first, second)
        self.assertEqual(calls, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
