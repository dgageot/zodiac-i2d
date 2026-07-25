"""Pure decoder for the 18-byte i2d status frame.

Deliberately free of Home Assistant and aiohttp imports so it can be unit
tested with the standard library alone, and reused by the standalone CLI.

Byte layout, as observed on a Zodiac i2d robot (serial prefix QBA, 2021):

    offset  size  meaning
    0-1     2     header, always 0011 on the observed unit
    2       1     state code
    3       1     error code
    4       1     low nibble = cleaning mode, high nibble = canister full flag
    5       1     minutes remaining in the current cycle
    6-8     3     little-endian counter, increments ~1 per minute
    9-11    3     little-endian hour counter
    12-14   3     hardware id
    15-17   3     firmware id

Confidence notes (honesty matters more than a tidy table):

* ``minutes_remaining`` is CONFIRMED: it decremented 193 -> 192 across two
  live reads taken about two minutes apart.
* ``minute_counter`` is CONFIRMED to increment about once per minute, but its
  meaning is unclear: 700714 minutes is ~11678 hours, which contradicts
  ``hour_counter`` = 2496. Both are exposed as diagnostics under neutral
  names rather than guessing at "uptime" or "total hours".
* The state/error/mode tables come from prior community work
  (galletn/iaqualink protocols/i2d.py). Unknown codes are surfaced as
  ``Unknown (0xNN)`` instead of being silently coerced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

FRAME_HEX_LENGTH = 36
FRAME_BYTE_LENGTH = 18

STATE_IDLE = 0x01
STATE_STARTING = 0x02
STATE_FINISHED = 0x03
STATE_CLEANING = 0x04
STATE_PAUSED = 0x0C

STATE_MAP: dict[int, str] = {
    STATE_IDLE: "idle",
    STATE_STARTING: "starting",
    STATE_FINISHED: "finished",
    STATE_CLEANING: "cleaning",
    STATE_PAUSED: "paused",
    0x0D: "error_d",
    0x0E: "error_e",
}

NO_ERROR = 0x00

ERROR_MAP: dict[int, str] = {
    NO_ERROR: "no_error",
    0x01: "pump_short_circuit",
    0x02: "right_drive_motor_short_circuit",
    0x03: "left_drive_motor_short_circuit",
    0x04: "pump_motor_overconsumption",
    0x05: "right_drive_motor_overconsumption",
    0x06: "left_drive_motor_overconsumption",
    0x07: "floats_on_surface",
    0x08: "running_out_of_water",
    0x0A: "communication_error",
}

MODE_FLOOR_ONLY = 0x00
MODE_FLOOR_AND_WALLS = 0x03
MODE_WATERLINE = 0x04

MODE_MAP: dict[int, str] = {
    MODE_FLOOR_ONLY: "floor_only",
    MODE_FLOOR_AND_WALLS: "floor_and_walls",
    MODE_WATERLINE: "waterline",
    0x08: "floor_only_quick",
    0x09: "floor_only_high",
    0x0A: "floor_and_walls_standard",
    0x0B: "floor_and_walls_high",
    0x0C: "waterline_standard",
    0x0D: "waterline_high",
    0x0E: "waterline_custom",
}

#: Modes the integration offers as vacuum fan speeds, mapped to the hex
#: command suffix used by ``set_mode``. Only the three the cleaner's own UI
#: exposes are offered; the custom variants above are read-only.
MODE_COMMANDS: dict[str, str] = {
    "floor_only": "0A1280",
    "floor_and_walls": "0A1283",
    "waterline": "0A1284",
}


class FrameError(ValueError):
    """Raised when a status payload is not a decodable 18-byte frame."""


@dataclass(frozen=True)
class Frame:
    """Decoded view of one status frame."""

    raw: str
    header: str
    state_code: int
    state: str
    error_code: int
    error: str
    mode_code: int
    mode: str
    canister_full: bool
    minutes_remaining: int
    minute_counter: int
    hour_counter: int
    hardware_id: str
    firmware_id: str

    @property
    def is_cleaning(self) -> bool:
        return self.state_code in (STATE_STARTING, STATE_CLEANING)

    @property
    def has_error(self) -> bool:
        return self.error_code != NO_ERROR

    def as_dict(self) -> dict:
        return asdict(self)


def parse_frame(payload: str) -> Frame:
    """Decode a status payload into a :class:`Frame`.

    Raises :class:`FrameError` on anything that is not 36 hex characters.
    """
    if not isinstance(payload, str):
        raise FrameError(f"expected a hex string, got {type(payload).__name__}")

    # Cloud diagnostic dumps mix in spaces, tabs and newlines.
    compact = "".join(payload.split())
    if len(compact) != FRAME_HEX_LENGTH:
        raise FrameError(
            f"expected {FRAME_HEX_LENGTH} hex characters, got {len(compact)}"
        )
    try:
        raw = bytes.fromhex(compact)
    except ValueError as err:
        raise FrameError(f"payload is not valid hex: {err}") from err

    state_code = raw[2]
    error_code = raw[3]
    mode_byte = raw[4]
    mode_code = mode_byte & 0x0F

    return Frame(
        raw=compact.lower(),
        header=raw[0:2].hex(),
        state_code=state_code,
        state=STATE_MAP.get(state_code, f"Unknown (0x{state_code:02X})"),
        error_code=error_code,
        error=ERROR_MAP.get(error_code, f"Unknown (0x{error_code:02X})"),
        mode_code=mode_code,
        mode=MODE_MAP.get(mode_code, f"Unknown (0x{mode_code:02X})"),
        canister_full=(mode_byte & 0xF0) != 0,
        minutes_remaining=raw[5],
        minute_counter=int.from_bytes(raw[6:9], "little"),
        hour_counter=int.from_bytes(raw[9:12], "little"),
        hardware_id=raw[12:15].hex(),
        firmware_id=raw[15:18].hex(),
    )
