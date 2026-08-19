"""Tests for Zodiac cloud API response validation."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock


class ClientError(Exception):
    pass


class ClientTimeout:
    def __init__(self, **kwargs):
        pass


aiohttp = types.ModuleType("aiohttp")
setattr(aiohttp, "ClientError", ClientError)
setattr(aiohttp, "ClientTimeout", ClientTimeout)
sys.modules.setdefault("aiohttp", aiohttp)

module_path = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "zodiac_i2d"
    / "api.py"
)
spec = importlib.util.spec_from_file_location("zodiac_i2d_api", module_path)
assert spec is not None
assert spec.loader is not None
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class TestCommandResponses(unittest.IsolatedAsyncioTestCase):
    def api_returning(self, response):
        client = api.ZodiacApi(None, "email", "password")
        client._user_id = "42"
        client._request = AsyncMock(return_value=response)
        return client

    async def test_accepts_matching_status_response(self):
        client = self.api_returning(
            {"command": {"request": api.REQUEST_STATUS, "response": " 0011 "}}
        )

        response = await client.async_send("serial", api.REQUEST_STATUS)

        self.assertEqual(response, "0011")

    async def test_allows_empty_status_response_for_sleeping_robot(self):
        client = self.api_returning(
            {"command": {"request": api.REQUEST_STATUS, "response": ""}}
        )

        response = await client.async_send("serial", api.REQUEST_STATUS)

        self.assertEqual(response, "")

    async def test_rejects_embedded_api_error(self):
        client = self.api_returning(
            {"status": "400", "error": {"message": "Invalid command"}}
        )

        with self.assertRaisesRegex(api.ZodiacError, "Invalid command"):
            await client.async_send("serial", api.REQUEST_START)

    async def test_maps_embedded_offline_error(self):
        client = self.api_returning(
            {"status": "500", "error": {"message": "Device offline"}}
        )

        with self.assertRaises(api.ZodiacOfflineError):
            await client.async_send("serial", api.REQUEST_STATUS)

    async def test_rejects_missing_command_envelope(self):
        client = self.api_returning({})

        with self.assertRaisesRegex(api.ZodiacError, "command envelope"):
            await client.async_send("serial", api.REQUEST_STATUS)

    async def test_rejects_mismatched_command(self):
        client = self.api_returning(
            {"command": {"request": api.REQUEST_STOP, "response": "ack"}}
        )

        with self.assertRaisesRegex(api.ZodiacError, "does not match"):
            await client.async_send("serial", api.REQUEST_START)

    async def test_rejects_unacknowledged_write(self):
        client = self.api_returning(
            {"command": {"request": api.REQUEST_START, "response": ""}}
        )

        with self.assertRaisesRegex(api.ZodiacError, "not acknowledged"):
            await client.async_send("serial", api.REQUEST_START)


if __name__ == "__main__":
    unittest.main()
