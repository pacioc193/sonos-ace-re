#!/usr/bin/env python3
"""Sonos Ace control client (BLE / GATT) -- proof of concept.

Protocol notes: ../protocol/NOTES.md. Reverse engineered from HCI captures and from the
identifiers of the Sonos app. The control characteristics default to the UUIDs listed
there; if the headphones expose something different, run ``services`` and pass
``--write-uuid`` / ``--notify-uuid``.

Usage (needs ``pip install bleak``; Windows 10/11, Linux or macOS):

  ace.py scan                               # find "Sonos Ace" and its address
  ace.py services <addr>                    # dump services/characteristics (UUIDs)
  ace.py <addr> mode anc|aware|off
  ace.py <addr> bass  -10..10
  ace.py <addr> treble -10..10
  ace.py <addr> balance -10..10             # + = right, - = left
  ace.py <addr> get anc|eq|balance|name|volume|...   # read a setting (see GETTERS)
  ace.py <addr> raw 00020f01                # send an arbitrary command, print the reply

The headphones must accept an LE connection from this host: if the phone app is
connected, close it first, and pair the headphones with the host if asked.
"""

import argparse
import asyncio
import sys

# --- protocol (pure functions, unit-tested without any Bluetooth hardware) ----------

CAT_SETTINGS = 0x02
ID_MODE = 0x0F
ID_BASS = 0x1E
ID_TREBLE = 0x1F
ID_BALANCE = 0x22

MODES = {"off": 0x00, "anc": 0x01, "aware": 0x02, "transparency": 0x02}

# GATT UUIDs from the app's identifiers (NOTES.md): service 0xFE07, control channel.
SERVICE_UUID = "0000fe07-0000-1000-8000-00805f9b34fb"
CONTROL_WRITE_UUID = "c44f42b1-f5cf-479b-b515-9f1bb0099c9a"
CONTROL_NOTIFY_UUID = "c44f42b1-f5cf-479b-b515-9f1bb0099c9b"
# Setup/handshake characteristics (the "gate" before control). In the captures the
# handshake rides handle 0x4e (write) / 0x50 (notify); the UUID binding is from the APK.
SETUP_WRITE_UUID = "c44f42b1-f5cf-479b-b515-9f1bb0099c9e"
SETUP_NOTIFY_UUID = "c44f42b1-f5cf-479b-b515-9f1bb0099c9f"

ID_LOUDNESS = 0x20

# Read-only requests: name -> (group, PDU id). Group 02 = settings, 03 = volume, 00 = status.
GETTERS = {
    "anc": (0x02, 0x0E), "eq": (0x02, 0x1C), "balance": (0x02, 0x21), "name": (0x02, 0x09),
    "adaptive-anc": (0x02, 0x37), "selfvoice": (0x02, 0x35), "autooff": (0x02, 0x1A),
    "wear": (0x02, 0x0C), "spatial": (0x02, 0x10), "buttons": (0x02, 0x04),
    "volume": (0x03, 0x03), "info": (0x00, 0x03), "charging": (0x00, 0x04),
}

# Handshake ("registration") written on the setup characteristic (handle 0x4e) right
# before the first control command, identical across three captures (EXP-01/02/03b). It is
# the gate: only after the accepted reply do control commands return SUCCESS instead of
# NO_PERMISSIONS (protocol/AUTH.md). Message = 9-byte prefix + 16-byte access token (the
# trailing 0x10 of the prefix is the token length). The real token is a per-device
# credential bound to the phone's bond and is NOT committed; supply it with --token.
REGISTRATION_PREFIX = bytes.fromhex("010604001400000010")
PLACEHOLDER_TOKEN = bytes(16)  # redacted; not a working credential
# Reply the phone receives on the setup notify characteristic when the handshake is
# accepted (EXP-01/02/03b). A different host replaying the same bytes was rejected with
# `01 07 00 00 02 80 01` (status 0x8001) -> the token is bound to the BLE identity.
SETUP_REPLY_OK = bytes.fromhex("01070000020000")


def registration_message(token: bytes = PLACEHOLDER_TOKEN) -> bytes:
    """Build the setup-characteristic handshake: 9-byte prefix + 16-byte token."""
    if len(token) != 16:
        raise ValueError("token must be 16 bytes (32 hex digits)")
    return REGISTRATION_PREFIX + token


def parse_setup_reply(reply: bytes):
    """Classify a setup/handshake reply. Returns (accepted: bool, text: str).

    Accepted = the status word (last 2 bytes after the `02` length byte) is `00 00`,
    i.e. the same reply the phone gets. `80 01` is the observed cross-host rejection.
    """
    if reply == SETUP_REPLY_OK:
        return True, "accepted (same as the phone)"
    if len(reply) >= 7 and reply[0] == 0x01 and reply[1] == 0x07 and reply[4] == 0x02:
        status = reply[5:7]
        if status == b"\x00\x00":
            return True, "accepted"
        if status == b"\x80\x01":
            return False, "rejected (0x8001): token not valid for this host/bond (see AUTH.md)"
        return False, f"rejected (status {status.hex()})"
    return False, "unexpected reply: " + reply.hex()


def int8(value: int) -> int:
    if not -10 <= value <= 10:
        raise ValueError("value must be between -10 and 10")
    return value & 0xFF


def command(setting_id: int, value: int, category: int = CAT_SETTINGS) -> bytes:
    """Build ``00 <category> <id> <value>`` (value already an unsigned byte)."""
    return bytes([0x00, category, setting_id, value & 0xFF])


def mode_command(name: str) -> bytes:
    try:
        return command(ID_MODE, MODES[name.lower()])
    except KeyError:
        raise ValueError(f"unknown mode {name!r} (use: {', '.join(sorted(MODES))})")


def bass_command(level: int) -> bytes:
    return command(ID_BASS, int8(level))


def treble_command(level: int) -> bytes:
    return command(ID_TREBLE, int8(level))


def balance_command(level: int) -> bytes:
    return command(ID_BALANCE, int8(level))


def loudness_command(on: bool) -> bytes:
    return command(ID_LOUDNESS, 1 if on else 0)


def get_command(name: str) -> bytes:
    try:
        group, pdu = GETTERS[name.lower()]
    except KeyError:
        raise ValueError(f"unknown getter {name!r} (use: {', '.join(sorted(GETTERS))})")
    return bytes([0x00, group, pdu])


def parse_reply(reply: bytes) -> str:
    """Human-readable decode of ``02 <group> <pdu> <status> <data...>``."""
    status_names = {0: "OK", 1: "NAMESPACE_NOT_SUPPORTED", 2: "COMMAND_NOT_SUPPORTED",
                    3: "INSUFFICIENT_RESOURCES", 4: "INVALID_PARAMETER", 5: "INVALID_STATE",
                    6: "INVALID_HEADER", 7: "INVALID_LENGTH", 8: "UNEXPECTED_ERROR", 9: "NO_PERMISSIONS"}
    if len(reply) < 4 or reply[0] != 0x02:
        return reply.hex()
    status, data = reply[3], reply[4:]
    text = f"{status_names.get(status, status)}"
    if status == 0 and data:
        text += f" data={data.hex()}"
        if reply[1:3] == bytes([0x02, 0x1C]) and len(data) >= 3:
            b, t = int.from_bytes(data[0:1], "big", signed=True), int.from_bytes(data[1:2], "big", signed=True)
            text += f" (bass={b} treble={t} loudness={data[2]})"
        elif reply[1:3] == bytes([0x02, 0x0E]):
            text += f" ({ {0: 'off', 1: 'anc', 2: 'aware'}.get(data[0], '?') })"
        elif reply[1:3] == bytes([0x02, 0x09]) and len(data) > 1:
            text += f" ({data[1:1 + data[0]].decode(errors='replace')!r})"
    return text


def is_ack(command_bytes: bytes, reply: bytes) -> bool:
    """A set command is acknowledged by ``02 <category> <id> 00``."""
    return len(reply) >= 4 and reply[0] == 0x02 and reply[1:3] == command_bytes[1:3] and reply[3] == 0x00


# --- BLE ---------------------------------------------------------------------

def autodetect(services):
    """Pick (write char, notify char) from a bleak service collection.

    Heuristic until the real UUIDs are known: in the custom (non-standard) service that
    has a write-without-response characteristic and a notify characteristic, take them.
    """
    for svc in services:
        if svc.uuid.lower().startswith("0000") and svc.uuid.lower().endswith("-0000-1000-8000-00805f9b34fb"):
            continue  # standard 16-bit service
        writes = [c for c in svc.characteristics if "write-without-response" in c.properties]
        notifies = [c for c in svc.characteristics if "notify" in c.properties]
        if writes and notifies:
            yield svc, writes, notifies


async def scan(timeout: float) -> None:
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for addr, (dev, adv) in sorted(found.items(), key=lambda kv: -kv[1][1].rssi):
        name = adv.local_name or dev.name or ""
        mark = "  <-- Sonos Ace" if "sonos ace" in name.lower() else ""
        print(f"{addr}  rssi={adv.rssi:4}  {name}{mark}")


async def dump_services(address: str) -> None:
    from bleak import BleakClient

    async with BleakClient(address) as client:
        for svc in client.services:
            print(f"service {svc.uuid}")
            for ch in svc.characteristics:
                print(f"  char {ch.uuid}  handle=0x{ch.handle:04x}  {','.join(ch.properties)}")


async def run(args) -> None:
    from bleak import BleakClient

    async with BleakClient(args.address) as client:
        write_char = notify_char = None
        if args.write_uuid and args.notify_uuid:
            write_char, notify_char = args.write_uuid, args.notify_uuid
        elif client.services.get_characteristic(CONTROL_WRITE_UUID) and \
                client.services.get_characteristic(CONTROL_NOTIFY_UUID):
            write_char, notify_char = CONTROL_WRITE_UUID, CONTROL_NOTIFY_UUID
        else:
            for svc, writes, notifies in autodetect(client.services):
                print(f"auto-detected service {svc.uuid}: "
                      f"write={[c.uuid for c in writes]} notify={[c.uuid for c in notifies]}")
                write_char, notify_char = writes[0].uuid, notifies[0].uuid
                break
        if not write_char:
            sys.exit("no suitable service found: run 'services' and pass --write-uuid/--notify-uuid")

        replies: asyncio.Queue = asyncio.Queue()
        await client.start_notify(notify_char, lambda _c, data: replies.put_nowait(bytes(data)))

        if not args.no_register:
            await do_register(client, args)

        cmd = build(args)
        await client.write_gatt_char(write_char, cmd, response=False)
        print(f"-> {cmd.hex()}")
        try:
            reply = await asyncio.wait_for(replies.get(), timeout=3)
            print(f"<- {reply.hex()}  {'(ack)' if is_ack(cmd, reply) and len(reply) == 4 else parse_reply(reply)}")
        except asyncio.TimeoutError:
            print("no reply within 3 s")


async def do_register(client, args) -> None:
    """Run the setup handshake exactly as the phone does in EXP-03b: enable the setup
    notify characteristic, write the handshake, then read and classify the reply."""
    setup_write = args.register_uuid or SETUP_WRITE_UUID
    setup_notify = args.register_notify_uuid or SETUP_NOTIFY_UUID
    if not client.services.get_characteristic(setup_write):
        print(f"setup characteristic {setup_write} not found: skipping handshake "
              "(run 'services', pass --register-uuid/--register-notify-uuid, or --no-register)")
        return

    token = PLACEHOLDER_TOKEN
    if args.token:
        token = bytes.fromhex(args.token)
    msg = registration_message(token)

    setup_replies: asyncio.Queue = asyncio.Queue()
    have_notify = bool(client.services.get_characteristic(setup_notify))
    if have_notify:
        await client.start_notify(setup_notify, lambda _c, data: setup_replies.put_nowait(bytes(data)))
    note = "" if args.token else " (placeholder token; not a working credential)"
    print(f"-> setup {msg.hex()}{note}")
    await client.write_gatt_char(setup_write, msg, response=False)
    if not have_notify:
        print("   setup notify characteristic not found: cannot read handshake reply")
        await asyncio.sleep(0.3)
        return
    try:
        reply = await asyncio.wait_for(setup_replies.get(), timeout=3)
        accepted, text = parse_setup_reply(reply)
        print(f"<- setup {reply.hex()}  {'OK' if accepted else 'FAIL'}: {text}")
        if not accepted:
            print("   control commands will likely return NO_PERMISSIONS until the handshake is accepted")
    except asyncio.TimeoutError:
        print("   no handshake reply within 3 s")


def build(args) -> bytes:
    if args.cmd == "mode":
        return mode_command(args.value)
    if args.cmd == "bass":
        return bass_command(int(args.value))
    if args.cmd == "treble":
        return treble_command(int(args.value))
    if args.cmd == "balance":
        return balance_command(int(args.value))
    if args.cmd == "loudness":
        return loudness_command(args.value.lower() in ("1", "on", "true"))
    if args.cmd == "get":
        return get_command(args.value)
    if args.cmd == "raw":
        return bytes.fromhex(args.value)
    raise ValueError(args.cmd)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["scan"]:
        asyncio.run(scan(float(argv[1]) if len(argv) > 1 else 8.0))
        return
    if argv[:1] == ["services"] and len(argv) == 2:
        asyncio.run(dump_services(argv[1]))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("address", help="BLE address (Windows/Linux) or UUID (macOS)")
    ap.add_argument("cmd", choices=["mode", "bass", "treble", "balance", "loudness", "get", "raw"])
    ap.add_argument("value")
    ap.add_argument("--write-uuid")
    ap.add_argument("--notify-uuid")
    ap.add_argument("--no-register", action="store_true",
                    help="skip the setup handshake (default: handshake first, like the phone app)")
    ap.add_argument("--token", help="16-byte access token as 32 hex digits (default: redacted placeholder)")
    ap.add_argument("--register-uuid", help="setup write characteristic (default: %(default)s)",
                    default=SETUP_WRITE_UUID)
    ap.add_argument("--register-notify-uuid", help="setup notify characteristic (default: %(default)s)",
                    default=SETUP_NOTIFY_UUID)
    args = ap.parse_args(argv)
    try:
        build(args)  # validate the value before connecting
        if args.token:
            registration_message(bytes.fromhex(args.token))  # validate token length
    except ValueError as e:
        ap.error(str(e))
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
