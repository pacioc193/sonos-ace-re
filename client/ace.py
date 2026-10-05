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
SETUP_WRITE_UUID = "c44f42b1-f5cf-479b-b515-9f1bb0099c9e"  # unverified role

ID_LOUDNESS = 0x20

# Read-only requests: name -> (group, PDU id). Group 02 = settings, 03 = volume, 00 = status.
GETTERS = {
    "anc": (0x02, 0x0E), "eq": (0x02, 0x1C), "balance": (0x02, 0x21), "name": (0x02, 0x09),
    "adaptive-anc": (0x02, 0x37), "selfvoice": (0x02, 0x35), "autooff": (0x02, 0x1A),
    "wear": (0x02, 0x0C), "spatial": (0x02, 0x10), "buttons": (0x02, 0x04),
    "volume": (0x03, 0x03), "info": (0x00, 0x03), "charging": (0x00, 0x04),
}

# Fixed 17-byte message seen in both captures on the secondary characteristic (handle
# 0x004e) right before the first command. Unknown purpose; replayed as-is on request.
REGISTRATION = bytes.fromhex("01060400140000001051468da4854b7bd88171310705bbebbe")


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

        if args.register:
            if not args.register_uuid:
                sys.exit("--register needs --register-uuid (the secondary characteristic)")
            await client.write_gatt_char(args.register_uuid, REGISTRATION, response=False)
            await asyncio.sleep(0.3)

        cmd = build(args)
        await client.write_gatt_char(write_char, cmd, response=False)
        print(f"-> {cmd.hex()}")
        try:
            reply = await asyncio.wait_for(replies.get(), timeout=3)
            print(f"<- {reply.hex()}  {'(ack)' if is_ack(cmd, reply) and len(reply) == 4 else parse_reply(reply)}")
        except asyncio.TimeoutError:
            print("no reply within 3 s")


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
    ap.add_argument("--register", action="store_true", help="replay the fixed 17-byte registration first")
    ap.add_argument("--register-uuid")
    args = ap.parse_args(argv)
    try:
        build(args)  # validate the value before connecting
    except ValueError as e:
        ap.error(str(e))
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
