# Zodiac i2d Pool Robot — Home Assistant integration

A Home Assistant custom integration for Zodiac / Polaris robotic pool cleaners
that report **`device_type: i2d_robot`** in the iAqualink cloud API.

This family includes the corded cleaners sold as **OV 5490 iQ**, **EX 4000 iQ**,
**RF 5600 iQ** and rebrands. It is the one family that no existing integration
talks to successfully.

## Why this exists

The official Home Assistant `iaqualink` integration cannot represent these
robots at all: it creates no `vacuum` platform, and the `iaqualink==0.7.0`
library it pins registers only the `iaqua` and `exo` device types.

The community integrations *claim* i2d support, but all of them post to:

```
POST https://r-api.iaqualink.net/v2/devices/{serial}/control.json
Authorization: <IdToken>
```

which returns **HTTP 401 `error_auth_required`** unconditionally for this
family. Verified against a live robot with every combination of raw token,
`Bearer` token, request body shape and HMAC signature.

The route that actually works is the legacy one, with credentials in the
**query string** and **no `Authorization` header**:

```
POST https://r-api.iaqualink.net/devices/{serial}/execute_read_command.json
     ?api_key=...&authentication_token=...&user_id=...

{"command": "/command", "params": "request=OA11", "user_id": ...}

200 OK
{"requestID":"","command":{"request":"OA11","response":"0011040000C128B10AC009001F43090F4580"}}
```

Both conditions must hold at once, which is likely why this went undiagnosed.

## Install

Requires **Home Assistant 2025.2 or newer**.

1. Copy `custom_components/zodiac_i2d/` into `<config>/custom_components/`.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Zodiac i2d Pool Robot**.
4. Enter your iAqualink email and password.

All `i2d_robot` devices on the account are added automatically.

## Entities

| Entity | Notes |
| --- | --- |
| `vacuum` | Start, stop, return to base, cleaning-mode selection |
| Status | idle / starting / cleaning / finished / paused |
| Error | Decoded error, e.g. `floats_on_surface`, `out of water` |
| Cleaning mode | Floor only / floor and walls / waterline |
| Time remaining | Minutes left in the current cycle |
| Canister full | Problem-class binary sensor |
| Problem | Set whenever the error byte is non-zero |
| Hour counter, Minute counter | Diagnostic, see caveats |

The raw status frame is exposed as a `raw_frame` attribute on the vacuum entity
for debugging.

## What is verified, and what is not

Being explicit, because most of the pain here came from code that guessed:

**Verified against a live robot (2021 unit, hardware id `1f4309`):**

- The `execute_read_command.json` route and its query-string auth.
- Status frame decoding. `minutes_remaining` was observed counting
  193 → 192 → 185 across reads, and the minute counter incrementing.
- Header, state, error, mode, canister-full and the id fields.

**Not yet verified:**

- **The write commands.** `start` / `stop` / `return_home` / mode-selection
  codes are carried over from prior community work. They are sent over the
  same proven transport, but the codes themselves are unconfirmed on this
  route. Use `scripts/verify_commands.py` to test them (see below).
- **The two counters.** `hour_counter` reads 2496 while `minute_counter`
  reads ~700714 (≈11678 h). They cannot both be lifetime totals, so they are
  exposed under neutral names as diagnostics rather than being labelled
  "total hours" or "uptime" on a guess.

## Verifying the write commands

Read-only, always safe:

```bash
python3 scripts/verify_commands.py --email you@example.com --password-file /tmp/pw
```

Actually moving the cleaner requires an explicit flag:

```bash
python3 scripts/verify_commands.py --email you@example.com --password-file /tmp/pw \
    --send start --i-understand-this-moves-my-robot
```

It prints the frame before, then re-reads at +5 s and +15 s and reports
whether anything changed. Starting a cycle and watching which bytes move is
also the way to resolve the counter ambiguity above.

## Known limitations

- **No model name.** `prod.zodiac-io.com/devices/v2/{serial}/features` answers
  *"Device does not belong to user"* for this family — i2d robots are only
  registered on the legacy host. The device shows as
  `i2d robot (hw <hardware_id>)`. This is a cloud-side limitation.
- **No pause.** The protocol has no pause command; `pause` maps to `stop`.
- **No directional control.** Remote steering exists only for the `vr` and
  `vortrax` families.
- **Polling, 30 s.** i2d robots use HTTP request/response, not the WebSocket
  shadow stream the other families use, so there is no push channel. Commands
  trigger an immediate refresh, so the interval does not affect
  responsiveness.

## Tests

The frame decoder is deliberately free of Home Assistant imports so it can be
tested with the standard library alone:

```bash
python3 -m unittest discover -s tests -v
```

## Credits

Device-type list, command codes and the initial byte map come from
[galletn/iaqualink](https://github.com/galletn/iaqualink). The signing scheme
and multi-host layout were cross-checked against
[flz/iaqualink-py](https://github.com/flz/iaqualink-py), and the
`Bearer`-vs-raw-token question against
[ErikVabu-Personal/iaqualink-homeassistant](https://github.com/ErikVabu-Personal/iaqualink-homeassistant),
whose notes come from decompiling the iAqualink Android app.

Unofficial; not affiliated with Zodiac, Fluidra or Jandy.
