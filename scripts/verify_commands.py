#!/usr/bin/env python3
"""Verify the WRITE commands against a real i2d robot.

The read path (status) is confirmed working. The write codes below come from
prior community work and have NOT been confirmed on this endpoint, so they are
gated behind an explicit flag: running this script WILL physically start or
stop your pool cleaner.

Recommended sequence:

    # 1. Read only, always safe:
    python3 verify_commands.py --email you@example.com --password-file /tmp/pw

    # 2. Start the robot, watch the state change, then stop it:
    python3 verify_commands.py --email you@example.com --password-file /tmp/pw \
        --send start --i-understand-this-moves-my-robot

Report the before/after frames in an issue so the byte map can be pinned down.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(
    0,
    str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "zodiac_i2d"),
)

from frame import FrameError, parse_frame  # noqa: E402

API_KEY = "EOOEMOW4YR6QNB07"
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
DEVICES_URL = "https://r-api.iaqualink.net/devices.json"
COMMAND_URL = "https://r-api.iaqualink.net/devices/{serial}/execute_read_command.json"

COMMANDS = {
    "status": "OA11",
    "start": "0A1240",
    "stop": "0A1210",
    "return_home": "0A1701",
    "mode_floor_only": "0A1280",
    "mode_floor_and_walls": "0A1283",
    "mode_waterline": "0A1284",
}

WRITE_COMMANDS = set(COMMANDS) - {"status"}


def call(method, url, *, params=None, body=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(errors="replace")


def send(serial, creds, code):
    params = f"request={code}"
    if code != COMMANDS["status"]:
        params = f"{params}&timeout=800"
    return call(
        "POST",
        COMMAND_URL.format(serial=serial),
        params=creds,
        body={"command": "/command", "params": params, "user_id": creds["user_id"]},
    )


def show_frame(label, payload):
    if not payload:
        print(f"  {label}: no frame returned (robot asleep?)")
        return
    try:
        frame = parse_frame(payload)
    except FrameError as err:
        print(f"  {label}: undecodable ({err}): {payload!r}")
        return
    print(
        f"  {label}: state={frame.state} error={frame.error} mode={frame.mode} "
        f"remaining={frame.minutes_remaining}min raw={frame.raw}"
    )


def command_took_effect(command, before, after):
    """Return whether command-relevant status fields changed."""
    try:
        previous = parse_frame(before)
        current = parse_frame(after)
    except FrameError:
        return False

    if command.startswith("mode_"):
        return current.mode_code != previous.mode_code
    return current.state_code != previous.state_code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password-file", help="file whose first line is the password")
    ap.add_argument("--send", choices=sorted(COMMANDS), default="status")
    ap.add_argument(
        "--i-understand-this-moves-my-robot",
        action="store_true",
        dest="confirmed",
        help="required for any command other than status",
    )
    args = ap.parse_args()

    if args.send in WRITE_COMMANDS and not args.confirmed:
        print(
            f"Refusing to send '{args.send}': it physically controls the cleaner.\n"
            "Re-run with --i-understand-this-moves-my-robot to proceed.",
            file=sys.stderr,
        )
        return 2

    if args.password_file:
        # readline keeps this safe for an empty file, unlike splitlines()[0].
        with open(args.password_file, encoding="utf-8") as handle:
            password = handle.readline().rstrip("\r\n")
        if not password:
            print(f"{args.password_file} is empty", file=sys.stderr)
            return 1
    else:
        import getpass

        password = getpass.getpass("iAqualink password: ")

    status, auth = call(
        "POST", LOGIN_URL, body={"apiKey": API_KEY, "email": args.email, "password": password}
    )
    if status != 200:
        print(f"login failed: {status} {auth}", file=sys.stderr)
        return 1

    creds = {
        "api_key": API_KEY,
        "authentication_token": auth["authentication_token"],
        "user_id": str(auth["id"]),
    }
    status, devices = call("GET", DEVICES_URL, params=creds)
    robots = [d for d in devices if d.get("device_type") == "i2d_robot"]
    if not robots:
        print("no i2d_robot on this account", file=sys.stderr)
        return 1

    for robot in robots:
        serial = robot["serial_number"]
        print(f"\n=== {robot.get('name')} ({serial}) ===")

        status, response = send(serial, creds, COMMANDS["status"])
        before = response.get("command", {}).get("response", "") if status == 200 else ""
        show_frame("before", before)

        if args.send == "status":
            continue

        code = COMMANDS[args.send]
        print(f"  sending {args.send} (request={code}) ...")
        status, response = send(serial, creds, code)
        print(f"  -> HTTP {status}: {json.dumps(response)[:200] if isinstance(response, dict) else response[:200]}")

        # Give the cleaner a moment to act on it, then read back.
        elapsed = 0
        for delay in (5, 10):
            time.sleep(delay)
            elapsed += delay
            status, response = send(serial, creds, COMMANDS["status"])
            after = response.get("command", {}).get("response", "") if status == 200 else ""
            show_frame(f"after +{elapsed}s", after)
            if command_took_effect(args.send, before, after):
                print("  -> command took effect")
                break
        else:
            print("  -> no change detected; the write code may be wrong for this model")

    return 0


if __name__ == "__main__":
    sys.exit(main())
