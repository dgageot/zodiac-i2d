"""Tests for cleaning-duration buttons."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch


class ButtonEntity:
    pass


@dataclass(frozen=True, kw_only=True)
class ButtonEntityDescription:
    key: str
    translation_key: str
    icon: str


button_component = types.ModuleType("homeassistant.components.button")
setattr(button_component, "ButtonEntity", ButtonEntity)
setattr(button_component, "ButtonEntityDescription", ButtonEntityDescription)
core = types.ModuleType("homeassistant.core")
setattr(core, "HomeAssistant", object)
entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
setattr(entity_platform, "AddConfigEntryEntitiesCallback", object)

package_name = "zodiac_i2d_button_test"
package = types.ModuleType(package_name)
package.__path__ = []
setattr(package, "ZodiacConfigEntry", object)

api_module = types.ModuleType(f"{package_name}.api")
setattr(api_module, "REQUEST_DURATION_LONGER", "0A1301")
setattr(api_module, "REQUEST_DURATION_SHORTER", "0A1300")

coordinator_module = types.ModuleType(f"{package_name}.coordinator")
setattr(coordinator_module, "ZodiacCoordinator", object)

entity_module = types.ModuleType(f"{package_name}.entity")


class ZodiacEntity:
    def __init__(self, coordinator, key):
        self.coordinator = coordinator
        self.key = key

    @property
    def available(self):
        return self.coordinator.last_update_success


setattr(entity_module, "ZodiacEntity", ZodiacEntity)

module_path = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zodiac_i2d"
    / "button.py"
)
spec = importlib.util.spec_from_file_location(f"{package_name}.button", module_path)
assert spec is not None
assert spec.loader is not None
button = importlib.util.module_from_spec(spec)
modules = {
    "homeassistant.components.button": button_component,
    "homeassistant.core": core,
    "homeassistant.helpers.entity_platform": entity_platform,
    package_name: package,
    api_module.__name__: api_module,
    coordinator_module.__name__: coordinator_module,
    entity_module.__name__: entity_module,
    spec.name: button,
}
with patch.dict(sys.modules, modules):
    spec.loader.exec_module(button)


class TestDurationButtons(unittest.IsolatedAsyncioTestCase):
    def entity(self, index=0, *, available=True, can_adjust=True):
        coordinator = types.SimpleNamespace(
            last_update_success=available,
            can_adjust_duration=can_adjust,
            async_adjust_duration=AsyncMock(),
        )
        return button.ZodiacDurationButton(coordinator, button.BUTTONS[index])

    def test_buttons_use_documented_commands(self):
        self.assertEqual(
            {description.key: description.request for description in button.BUTTONS},
            {
                "extend_duration": "0A1301",
                "shorten_duration": "0A1300",
            },
        )

    def test_available_during_active_cycle(self):
        self.assertTrue(self.entity().available)

    def test_unavailable_when_duration_cannot_be_adjusted(self):
        self.assertFalse(self.entity(can_adjust=False).available)

    def test_unavailable_after_coordinator_failure(self):
        self.assertFalse(self.entity(available=False).available)

    async def test_press_delegates_exact_request(self):
        entity = self.entity(index=1)

        await entity.async_press()

        entity.coordinator.async_adjust_duration.assert_awaited_once_with("0A1300")


if __name__ == "__main__":
    unittest.main()
