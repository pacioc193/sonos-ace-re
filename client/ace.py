#!/usr/bin/env python3
"""Sonos Ace control client (BLE / GATT) -- proof of concept.

Protocol notes: ../protocol/NOTES.md. Everything here is reverse engineered from
HCI captures; the GATT UUIDs are not known yet, so the first run uses ``scan`` and
``services`` to find them, then the characteristics are selected by UUID with
``--write-uuid`` / ``--notify-uuid`` (or auto-detected, see ``autodetect``).

Usage (needs ``pip install bleak``; Windows 10/11, Linux or macOS):

  ace.py scan                               # find "Sonos Ace" and its address
  ace.py services <addr>                    # dump services/characteristics (UUIDs)
  ace.py <addr> mode anc|aware|off
  ace.py <addr> bass  -10..10
  ace.py <addr> treble -10..10
  ace.py <addr> balance -10..10             # + = right, - = left
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
            print(f"<- {reply.hex()}  {'(ack)' if is_ack(cmd, reply) else ''}")
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
    ap.add_argument("cmd", choices=["mode", "bass", "treble", "balance", "raw"])
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
