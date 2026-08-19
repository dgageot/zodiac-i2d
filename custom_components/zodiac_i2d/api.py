"""Minimal async client for Zodiac i2d robots on the legacy iAqualink host.

Transport notes, established empirically against a live robot:

* Login is on ``prod.zodiac-io.com``, but i2d robots live entirely on the
  legacy ``r-api.iaqualink.net`` host. The ``prod`` device endpoints reject
  them outright ("Device does not belong to user"), which is why the model
  name is not retrievable for this family.
* The working command route is
  ``POST /devices/{serial}/execute_read_command.json``.
  Credentials go in the QUERY STRING and there must be NO Authorization
  header. Existing integrations post to ``/v2/devices/{serial}/control.json``
  with an Authorization header, which returns 401 ``error_auth_required``
  unconditionally for this family.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_KEY = "EOOEMOW4YR6QNB07"
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
DEVICES_URL = "https://r-api.iaqualink.net/devices.json"
COMMAND_URL = "https://r-api.iaqualink.net/devices/{serial}/execute_read_command.json"

DEVICE_TYPE = "i2d_robot"

#: Read-only status request. Note the letter "O": the cloud echoes this exact
#: token back in ``command.request``, and it is spelled this way in every
#: known implementation, unlike the write codes which use a leading zero.
REQUEST_STATUS = "OA11"

REQUEST_START = "0A1240"
REQUEST_STOP = "0A1210"
REQUEST_DURATION_SHORTER = "0A1300"
REQUEST_DURATION_LONGER = "0A1301"
REQUEST_RETURN_HOME = "0A1701"

TIMEOUT = aiohttp.ClientTimeout(total=30)


class ZodiacError(Exception):
    """Base error."""


class ZodiacAuthError(ZodiacError):
    """Credentials were rejected."""


class ZodiacOfflineError(ZodiacError):
    """The cloud reports the robot as offline."""


def _error_message(error: Any) -> str:
    if isinstance(error, dict):
        error = error.get("message")
    return str(error) if error else ""


class ZodiacApi:
    """Talks to the legacy iAqualink endpoints for one account."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._auth_token: str | None = None
        self._user_id: str | None = None

    @property
    def user_id(self) -> str | None:
        return self._user_id

    async def login(self) -> None:
        payload = {"apiKey": API_KEY, "email": self._email, "password": self._password}
        try:
            async with self._session.post(
                LOGIN_URL, json=payload, timeout=TIMEOUT
            ) as response:
                if response.status in (401, 403):
                    raise ZodiacAuthError("iAqualink rejected the credentials")
                response.raise_for_status()
                body = await response.json()
        except TimeoutError:
            raise ZodiacError("login request timed out") from None
        except aiohttp.ClientError as err:
            raise ZodiacError(f"login request failed: {type(err).__name__}") from None

        try:
            self._auth_token = body["authentication_token"]
            self._user_id = str(body["id"])
        except (KeyError, TypeError) as err:
            # A 200 with an unexpected shape is how this API signals some
            # credential problems, so treat it as an auth failure.
            raise ZodiacAuthError(f"unexpected login response shape: {err}") from err

    def _credentials(self) -> dict[str, str]:
        if not self._auth_token or not self._user_id:
            raise ZodiacAuthError("not logged in")
        return {
            "api_key": API_KEY,
            "authentication_token": self._auth_token,
            "user_id": self._user_id,
        }

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict | None = None,
    ) -> Any:
        """Perform a request, re-logging in once on 401."""
        for attempt in range(2):
            if not self._auth_token:
                await self.login()
            try:
                async with self._session.request(
                    method,
                    url,
                    params={**self._credentials(), **(params or {})},
                    json=json_body,
                    timeout=TIMEOUT,
                ) as response:
                    if response.status == 401:
                        self._auth_token = None
                        if attempt == 0:
                            _LOGGER.debug("401 on %s, refreshing session", url)
                            continue
                        raise ZodiacAuthError(f"401 from {url} after re-login")
                    if response.status == 500:
                        text = await response.text()
                        if "offline" in text.lower():
                            raise ZodiacOfflineError("cloud reports robot offline")
                        raise ZodiacError(f"server error from {url}: {text[:200]}")
                    response.raise_for_status()
                    return await response.json()
            except TimeoutError:
                raise ZodiacError(f"request to {url} timed out") from None
            except aiohttp.ClientError as err:
                # ClientResponseError includes the credential-bearing URL.
                raise ZodiacError(
                    f"request to {url} failed: {type(err).__name__}"
                ) from None
        raise ZodiacError("request loop exhausted")

    async def async_get_robots(self) -> list[dict[str, Any]]:
        """Return the i2d robots on this account."""
        devices = await self._request("GET", DEVICES_URL)
        if not isinstance(devices, list):
            raise ZodiacError(f"unexpected device list shape: {type(devices).__name__}")
        return [d for d in devices if d.get("device_type") == DEVICE_TYPE]

    async def async_send(self, serial: str, request: str) -> str:
        """Send a raw request code, returning the response payload hex.

        ``request`` is a code such as ``OA11`` (status) or ``0A1240`` (start).
        """
        params = {"command": "/command", "params": f"request={request}"}
        if request != REQUEST_STATUS:
            params["params"] = f"{params['params']}&timeout=800"
        response = await self._request(
            "POST", COMMAND_URL.format(serial=serial), params=params
        )
        if not isinstance(response, dict):
            raise ZodiacError(f"unexpected response shape: {type(response).__name__}")

        status = response.get("status")
        error = response.get("error")
        if status not in (None, 200, "200") or error:
            message = _error_message(error)
            if status in (500, "500") and "offline" in message.lower():
                raise ZodiacOfflineError("cloud reports robot offline")
            detail = f": {message}" if message else ""
            raise ZodiacError(f"command failed with status {status}{detail}")

        command = response.get("command")
        if not isinstance(command, dict):
            raise ZodiacError("response is missing the command envelope")
        if command.get("request") != request:
            raise ZodiacError("response does not match the command request")

        payload = command.get("response")
        if not isinstance(payload, str):
            raise ZodiacError("command response payload is missing")
        payload = payload.strip()
        if request != REQUEST_STATUS and not payload:
            raise ZodiacError("write command was not acknowledged")
        return payload

    async def async_read_status(self, serial: str) -> str:
        """Return the raw status frame hex, or "" if the robot did not answer."""
        return await self.async_send(serial, REQUEST_STATUS)
