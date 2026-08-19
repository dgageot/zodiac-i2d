"""Constants for the Zodiac i2d integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

# Must match the manifest domain and this directory's name.
DOMAIN: Final = "zodiac_i2d"

PLATFORMS: Final = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

# The robot reports a minute-resolution countdown, so polling faster than this
# gains nothing and only adds cloud load. Commands trigger an immediate
# refresh, so responsiveness does not depend on this interval.
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=30)

MANUFACTURER: Final = "Zodiac"
