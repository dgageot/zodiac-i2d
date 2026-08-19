"""Tests for the command verification helper."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

module_path = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "verify_commands.py"
)
spec = importlib.util.spec_from_file_location("verify_commands", module_path)
assert spec is not None
assert spec.loader is not None
verify_commands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_commands)


def build_frame(*, state=0x01, mode=0x00, remaining=0, minute_counter=0):
    raw = bytearray(18)
    raw[1] = 0x11
    raw[2] = state
    raw[4] = mode
    raw[5] = remaining
    raw[6:9] = minute_counter.to_bytes(3, "little")
    return raw.hex()


class TestCommandTookEffect(unittest.TestCase):
    def test_ignores_changing_telemetry_for_state_command(self):
        before = build_frame(state=0x04, remaining=30, minute_counter=100)
        after = build_frame(state=0x04, remaining=29, minute_counter=101)

        self.assertFalse(verify_commands.command_took_effect("stop", before, after))

    def test_detects_state_change(self):
        before = build_frame(state=0x01)
        after = build_frame(state=0x02)

        self.assertTrue(verify_commands.command_took_effect("start", before, after))

    def test_mode_command_uses_mode_change(self):
        before = build_frame(state=0x01, mode=0x00)
        after = build_frame(state=0x01, mode=0x03)

        self.assertTrue(
            verify_commands.command_took_effect("mode_floor_and_walls", before, after)
        )

    def test_rejects_missing_frame(self):
        self.assertFalse(verify_commands.command_took_effect("start", "", ""))


if __name__ == "__main__":
    unittest.main()
