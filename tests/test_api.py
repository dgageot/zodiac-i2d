"""Tests for Zodiac cloud API response validation."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class ClientError(Exception):
    pass


class ClientTimeout:
    def __init__(self, **kwargs):
        pass


aiohttp = types.ModuleType("aiohttp")
setattr(aiohttp, "ClientError", ClientError)
setattr(aiohttp, "ClientTimeout", ClientTimeout)

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
with patch.dict(sys.modules, {"aiohttp": aiohttp}):
    spec.loader.exec_module(api)


class RequestContext:
    def __init__(self, error):
        self.error = error

    async def __aenter__(self):
        raise self.error

    async def __aexit__(self, *args):
        pass


class FailingSession:
    def __init__(self, error):
        self.error = error

    def request(self, *args, **kwargs):
        return RequestContext(self.error)


class RecordingRequest:
    def __init__(self, session, response):
        self.session = session
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        pass


class JsonResponse:
    status = 200

    def raise_for_status(self):
        pass

    async def json(self):
        return {"ok": True}


class RecordingSession:
    def __init__(self):
        self.kwargs = None

    def request(self, *args, **kwargs):
        self.kwargs = kwargs
        return RecordingRequest(self, JsonResponse())


class TestRequestParameters(unittest.IsolatedAsyncioTestCase):
    async def test_merges_command_and_credentials_in_query(self):
        session = RecordingSession()
        client = api.ZodiacApi(session, "email", "password")
        client._auth_token = "token"
        client._user_id = "42"

        await client._request(
            "POST",
            "https://example.com/command",
            params={"command": "/command", "params": "request=0A1301&timeout=800"},
        )

        assert session.kwargs is not None
        self.assertEqual(
            session.kwargs["params"],
            {
                "api_key": api.API_KEY,
                "authentication_token": "token",
                "user_id": "42",
                "command": "/command",
                "params": "request=0A1301&timeout=800",
            },
        )
        self.assertIsNone(session.kwargs["json"])


class TestRequestErrors(unittest.IsolatedAsyncioTestCase):
    def api_with_error(self, error):
        client = api.ZodiacApi(FailingSession(error), "email", "password")
        client._auth_token = "secret"
        client._user_id = "42"
        return client

    async def test_drops_client_error_cause(self):
        client = self.api_with_error(ClientError("secret URL"))

        with self.assertRaises(api.ZodiacError) as raised:
            await client._request("GET", "https://example.com/devices")

        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)
        self.assertNotIn("secret", str(raised.exception))

    async def test_translates_timeout(self):
        client = self.api_with_error(TimeoutError())

        with self.assertRaisesRegex(api.ZodiacError, "timed out"):
            await client._request("GET", "https://example.com/devices")


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

    async def test_duration_command_uses_write_timeout(self):
        client = self.api_returning(
            {
                "command": {
                    "request": api.REQUEST_DURATION_LONGER,
                    "response": "ack",
                }
            }
        )

        await client.async_send("serial", api.REQUEST_DURATION_LONGER)

        client._request.assert_awaited_once_with(
            "POST",
            api.COMMAND_URL.format(serial="serial"),
            params={
                "command": "/command",
                "params": f"request={api.REQUEST_DURATION_LONGER}&timeout=800",
            },
        )

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
