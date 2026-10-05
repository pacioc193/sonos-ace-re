#!/usr/bin/env python3
"""Byte-by-byte diff of hex payloads.

Two modes:

  # Compare payloads given on the command line (spaces/colons allowed)
  diff_hex.py 0a0102ff 0a0103ff "0a 01 04 ff"

  # Walk a btsnoop_extract.py --jsonl file; each payload is compared with the
  # previous one on the same channel (dir + ATT handle or RFCOMM DLCI)
  diff_hex.py --jsonl out.jsonl [--dir tx|rx]

Changed bytes are marked with ^^ on the line below. The first payload of a
group is printed as-is. Stdlib only.
"""

import argparse
import json
import re
import sys


def parse_hex(s):
    s = re.sub(r"[\s:,-]", "", s)
    if s.startswith(("0x", "0X")):
        s = s[2:]
    return bytes.fromhex(s)


def diff_lines(prev, cur):
    """Return (hex line, marker line) for cur, marking bytes differing from prev."""
    cells, marks = [], []
    for i, b in enumerate(cur):
        cells.append(f"{b:02x}")
        changed = prev is not None and (i >= len(prev) or prev[i] != b)
        marks.append("^^" if changed else "  ")
    line = " ".join(cells)
    marker = " ".join(marks).rstrip()
    if prev is not None and len(prev) > len(cur):
        marker += f"  (-{len(prev) - len(cur)} bytes)"
    return line, marker


def offsets_header(n):
    return " ".join(f"{i:02d}" for i in range(n))


def cmd_args(payloads):
    blobs = [parse_hex(p) for p in payloads]
    width = max((len(b) for b in blobs), default=0)
    print(f"{'off':>4}  {offsets_header(width)}")
    prev = None
    for idx, blob in enumerate(blobs):
        line, marker = diff_lines(prev, blob)
        print(f"{idx:>4}  {line}")
        if marker.strip():
            print(f"{'':>4}  {marker}")
        prev = blob
    if len(blobs) > 1:
        const = [i for i in range(min(len(b) for b in blobs))
                 if len({b[i] for b in blobs}) == 1]
        varying = [i for i in range(width) if i not in const]
        print(f"\nvarying offsets: {varying}")


def channel_key(rec):
    if rec.get("proto") == "att":
        return (rec["dir"], "att", rec.get("handle"), rec.get("att_handle"), rec.get("op"))
    if rec.get("proto") == "rfcomm":
        return (rec["dir"], "rfcomm", rec.get("handle"), rec.get("dlci"))
    return (rec["dir"], rec.get("proto"), rec.get("handle"), rec.get("cid"))


def fmt_key(key):
    parts = []
    for k in key:
        if k is None:
            continue
        parts.append(f"0x{k:x}" if isinstance(k, int) else str(k))
    return "/".join(parts)


def cmd_jsonl(path, only_dir):
    last = {}
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            if only_dir and rec.get("dir") != only_dir:
                continue
            payload = bytes.fromhex(rec.get("payload", ""))
            if not payload:
                continue
            key = channel_key(rec)
            prev = last.get(key)
            if prev == payload:
                continue  # identical repeat (keepalive/poll); skip noise
            line, marker = diff_lines(prev, payload)
            print(f"{rec['t']:.6f} {fmt_key(key):<28} {line}")
            if marker.strip():
                print(f"{'':>17} {'':<28} {marker}")
            last[key] = payload


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("payloads", nargs="*", help="hex payloads to compare")
    ap.add_argument("--jsonl", help="output of btsnoop_extract.py --jsonl")
    ap.add_argument("--dir", choices=["tx", "rx"], help="with --jsonl: only this direction")
    args = ap.parse_args(argv)
    if args.jsonl:
        cmd_jsonl(args.jsonl, args.dir)
    elif args.payloads:
        cmd_args(args.payloads)
    else:
        ap.error("give hex payloads or --jsonl FILE")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
