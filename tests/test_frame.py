"""Unit tests for the pure frame decoder.

Runnable with the standard library alone (no Home Assistant, no pytest):

    python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zodiac_i2d")
)

from frame import (  # noqa: E402
    FRAME_HEX_LENGTH,
    MODE_COMMANDS,
    FrameError,
    parse_frame,
)

# Two consecutive live reads from a real robot (serial QBA..., 2021 unit),
# captured about two minutes apart.
LIVE_1 = "0011040000C128B10AC009001F43090F4580"
LIVE_2 = "0011040000C02AB10AC009001F43090F4580"


class TestLiveFrames(unittest.TestCase):
    def test_decodes_live_frame(self):
        frame = parse_frame(LIVE_1)
        self.assertEqual(frame.header, "0011")
        self.assertEqual(frame.state, "cleaning")
        self.assertEqual(frame.error, "no_error")
        self.assertEqual(frame.mode, "floor_only")
        self.assertFalse(frame.canister_full)
        self.assertEqual(frame.minutes_remaining, 193)
        self.assertEqual(frame.hour_counter, 2496)
        self.assertEqual(frame.hardware_id, "1f4309")
        self.assertEqual(frame.firmware_id, "0f4580")

    def test_countdown_decreases_between_reads(self):
        first, second = parse_frame(LIVE_1), parse_frame(LIVE_2)
        self.assertEqual(first.minutes_remaining - second.minutes_remaining, 1)

    def test_minute_counter_increases_between_reads(self):
        first, second = parse_frame(LIVE_1), parse_frame(LIVE_2)
        self.assertGreater(second.minute_counter, first.minute_counter)

    def test_stable_fields_do_not_drift(self):
        first, second = parse_frame(LIVE_1), parse_frame(LIVE_2)
        self.assertEqual(first.hardware_id, second.hardware_id)
        self.assertEqual(first.firmware_id, second.firmware_id)
        self.assertEqual(first.hour_counter, second.hour_counter)

    def test_flags(self):
        frame = parse_frame(LIVE_1)
        self.assertTrue(frame.is_cleaning)
        self.assertFalse(frame.has_error)


def build(state=0x01, error=0x00, mode_byte=0x00, remaining=0x00) -> str:
    """Compose a synthetic frame with the given header fields."""
    body = bytes([0x00, 0x11, state, error, mode_byte, remaining])
    return (body + bytes(FRAME_HEX_LENGTH // 2 - len(body))).hex()


class TestDecoding(unittest.TestCase):
    def test_state_codes(self):
        for code, expected in [
            (0x01, "idle"),
            (0x02, "starting"),
            (0x03, "finished"),
            (0x04, "cleaning"),
            (0x0C, "paused"),
        ]:
            self.assertEqual(parse_frame(build(state=code)).state, expected)

    def test_unknown_state_is_surfaced_not_hidden(self):
        frame = parse_frame(build(state=0x7F))
        self.assertEqual(frame.state, "Unknown (0x7F)")

    def test_error_code_sets_has_error(self):
        frame = parse_frame(build(error=0x07))
        self.assertEqual(frame.error, "floats_on_surface")
        self.assertTrue(frame.has_error)

    def test_canister_flag_is_high_nibble(self):
        self.assertTrue(parse_frame(build(mode_byte=0x10)).canister_full)
        self.assertFalse(parse_frame(build(mode_byte=0x0F)).canister_full)

    def test_mode_is_low_nibble_independent_of_canister(self):
        # Canister full must not corrupt the decoded mode.
        frame = parse_frame(build(mode_byte=0xF3))
        self.assertEqual(frame.mode, "floor_and_walls")
        self.assertTrue(frame.canister_full)

    def test_is_cleaning_covers_starting_and_cleaning(self):
        self.assertTrue(parse_frame(build(state=0x02)).is_cleaning)
        self.assertTrue(parse_frame(build(state=0x04)).is_cleaning)
        self.assertFalse(parse_frame(build(state=0x01)).is_cleaning)

    def test_little_endian_counters(self):
        raw = bytes([0, 0x11, 1, 0, 0, 0]) + bytes([0x01, 0x02, 0x03])
        raw += bytes([0x04, 0x05, 0x06]) + bytes(6)
        frame = parse_frame(raw.hex())
        self.assertEqual(frame.minute_counter, 0x030201)
        self.assertEqual(frame.hour_counter, 0x060504)

    def test_whitespace_is_tolerated(self):
        spaced = " ".join(LIVE_1[i : i + 2] for i in range(0, len(LIVE_1), 2))
        self.assertEqual(parse_frame(spaced).raw, LIVE_1.lower())

    def test_as_dict_roundtrip(self):
        self.assertEqual(parse_frame(LIVE_1).as_dict()["mode"], "floor_only")


class TestErrors(unittest.TestCase):
    def test_rejects_short_payload(self):
        with self.assertRaises(FrameError):
            parse_frame("0011")

    def test_rejects_long_payload(self):
        with self.assertRaises(FrameError):
            parse_frame(LIVE_1 + "00")

    def test_rejects_non_hex(self):
        with self.assertRaises(FrameError):
            parse_frame("z" * FRAME_HEX_LENGTH)

    def test_rejects_empty(self):
        with self.assertRaises(FrameError):
            parse_frame("")

    def test_rejects_non_string(self):
        with self.assertRaises(FrameError):
            parse_frame(None)


class TestModeCommands(unittest.TestCase):
    def test_every_commandable_mode_is_a_known_mode(self):
        # A fan speed the robot can never report back would be a bug.
        for mode in MODE_COMMANDS:
            self.assertIn(mode, {parse_frame(build(mode_byte=c)).mode for c in range(16)})

    def test_command_codes_are_hex(self):
        for code in MODE_COMMANDS.values():
            int(code, 16)


if __name__ == "__main__":
    unittest.main()
