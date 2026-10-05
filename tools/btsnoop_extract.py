#!/usr/bin/env python3
"""Extract application-level payloads from an Android btsnoop_hci.log.

Supports btsnoop datalink 1002 (HCI UART / H4), which is what Android writes.
Reassembles L2CAP per (ACL handle, direction) and decodes:

  * ATT (LE CID 0x0004, or BR/EDR PSM 0x001F): write req/cmd, notify,
    indicate, read req/rsp (read rsp is tagged with the last requested handle)
  * RFCOMM (BR/EDR PSM 0x0003): UIH frames with DLCI, length and credits
  * anything else on a dynamic channel is emitted as raw L2CAP

Stdlib only. Usage:

  btsnoop_extract.py btsnoop_hci.log
  btsnoop_extract.py btsnoop_hci.log --jsonl > out.jsonl
  btsnoop_extract.py btsnoop_hci.log --proto rfcomm --dlci 18
  btsnoop_extract.py btsnoop_hci.log --proto att --att-handle 0x002a
"""

import argparse
import json
import struct
import sys

BTSNOOP_MAGIC = b"btsnoop\x00"
DATALINK_H4 = 1002
# btsnoop timestamps are microseconds since 0000-01-01; this is the Unix epoch.
BTSNOOP_EPOCH_DELTA_US = 0x00DCDDB30F2F8000

H4_CMD, H4_ACL, H4_SCO, H4_EVT = 0x01, 0x02, 0x03, 0x04

CID_SIGNALING = 0x0001
CID_ATT = 0x0004
CID_LE_SIGNALING = 0x0005

PSM_RFCOMM = 0x0003
PSM_ATT = 0x001F

ATT_OPS = {
    0x01: "error_rsp",
    0x02: "mtu_req",
    0x03: "mtu_rsp",
    0x0A: "read_req",
    0x0B: "read_rsp",
    0x12: "write_req",
    0x13: "write_rsp",
    0x1B: "notify",
    0x1D: "indicate",
    0x1E: "confirm",
    0x52: "write_cmd",
}
# Opcodes whose PDU starts with a 16-bit attribute handle followed by a value.
ATT_HANDLE_VALUE_OPS = {0x12, 0x52, 0x1B, 0x1D}

RFCOMM_FRAME_TYPES = {
    0x2F: "SABM",
    0x63: "UA",
    0x0F: "DM",
    0x43: "DISC",
    0xEF: "UIH",
}

DIR_TX = "tx"  # host -> controller (phone -> headphones)
DIR_RX = "rx"  # controller -> host (headphones -> phone)


def read_records(f):
    """Yield (timestamp_us_unix, direction, h4_packet) from a btsnoop file."""
    header = f.read(16)
    if len(header) < 16 or header[:8] != BTSNOOP_MAGIC:
        raise ValueError("not a btsnoop file")
    _version, datalink = struct.unpack(">II", header[8:16])
    if datalink != DATALINK_H4:
        raise ValueError(f"unsupported btsnoop datalink {datalink} (expected {DATALINK_H4})")
    while True:
        rec = f.read(24)
        if len(rec) < 24:
            return
        _orig_len, incl_len, flags, _drops, ts = struct.unpack(">IIIIq", rec)
        data = f.read(incl_len)
        if len(data) < incl_len:
            return
        direction = DIR_RX if flags & 0x01 else DIR_TX
        yield ts - BTSNOOP_EPOCH_DELTA_US, direction, data


def fmt_bdaddr(raw):
    return ":".join(f"{b:02X}" for b in reversed(raw))


class Extractor:
    def __init__(self):
        self.acl_buf = {}  # (handle, dir) -> bytearray being reassembled
        self.acl_need = {}  # (handle, dir) -> total L2CAP frame length
        self.addr = {}  # ACL handle -> peer bdaddr string
        self.pending_conn = {}  # (handle, dir, sig id) -> (psm, scid)
        self.channels = {}  # (handle, dir, dest cid) -> psm
        self.last_read = {}  # (handle, requester dir) -> ATT handle

    # --- HCI -----------------------------------------------------------

    def feed(self, ts, direction, pkt):
        if not pkt:
            return
        kind = pkt[0]
        if kind == H4_EVT:
            self._event(pkt[1:])
        elif kind == H4_ACL:
            yield from self._acl(ts, direction, pkt[1:])

    def _event(self, ev):
        if len(ev) < 2:
            return
        code, plen = ev[0], ev[1]
        p = ev[2 : 2 + plen]
        if code == 0x03 and len(p) >= 9 and p[0] == 0:  # Connection Complete
            handle = struct.unpack_from("<H", p, 1)[0] & 0x0FFF
            self.addr[handle] = fmt_bdaddr(p[3:9])
        elif code == 0x3E and p and p[0] in (0x01, 0x0A) and len(p) >= 11 and p[1] == 0:
            # LE (Enhanced) Connection Complete
            handle = struct.unpack_from("<H", p, 2)[0] & 0x0FFF
            self.addr[handle] = fmt_bdaddr(p[6:12])

    def _acl(self, ts, direction, acl):
        if len(acl) < 4:
            return
        hdr, length = struct.unpack_from("<HH", acl, 0)
        handle = hdr & 0x0FFF
        pb = (hdr >> 12) & 0x3
        data = acl[4 : 4 + length]
        key = (handle, direction)
        if pb in (0x0, 0x2):  # first fragment
            if len(data) < 4:
                return
            self.acl_buf[key] = bytearray(data)
            self.acl_need[key] = struct.unpack_from("<H", data, 0)[0] + 4
        elif pb == 0x1:  # continuation
            if key not in self.acl_buf:
                return
            self.acl_buf[key] += data
        else:
            return
        buf = self.acl_buf[key]
        if len(buf) >= self.acl_need[key]:
            frame = bytes(buf[: self.acl_need[key]])
            del self.acl_buf[key], self.acl_need[key]
            yield from self._l2cap(ts, direction, handle, frame)

    # --- L2CAP ---------------------------------------------------------

    def _l2cap(self, ts, direction, handle, frame):
        length, cid = struct.unpack_from("<HH", frame, 0)
        payload = frame[4 : 4 + length]
        base = {
            "t": ts / 1e6,
            "dir": direction,
            "handle": handle,
            "addr": self.addr.get(handle),
            "cid": cid,
        }
        if cid == CID_SIGNALING:
            self._signaling(handle, direction, payload)
            return
        if cid == CID_LE_SIGNALING:
            return
        if cid == CID_ATT:
            yield self._att(base, payload)
            return
        psm = self.channels.get((handle, direction, cid))
        base["psm"] = psm
        if psm == PSM_RFCOMM:
            rec = self._rfcomm(base, payload)
            if rec:
                yield rec
        elif psm == PSM_ATT:
            yield self._att(base, payload)
        elif cid >= 0x0040:
            yield dict(base, proto="l2cap", payload=payload.hex())

    def _signaling(self, handle, direction, sig):
        # A C-frame may hold several commands.
        off = 0
        while off + 4 <= len(sig):
            code, ident, clen = struct.unpack_from("<BBH", sig, off)
            body = sig[off + 4 : off + 4 + clen]
            off += 4 + clen
            if code == 0x02 and len(body) >= 4:  # Connection Request
                psm, scid = struct.unpack_from("<HH", body, 0)
                self.pending_conn[(handle, direction, ident)] = (psm, scid)
            elif code == 0x03 and len(body) >= 6:  # Connection Response
                dcid, scid, result = struct.unpack_from("<HHH", body, 0)
                req_dir = DIR_RX if direction == DIR_TX else DIR_TX
                pending = self.pending_conn.pop((handle, req_dir, ident), None)
                if pending is None or result != 0:
                    if pending is not None and result == 1:  # pending: wait for final rsp
                        self.pending_conn[(handle, req_dir, ident)] = pending
                    continue
                psm, _ = pending
                # Frames from the requester are addressed to the responder's CID
                # (dcid); frames to the requester carry the requester's CID (scid).
                self.channels[(handle, req_dir, dcid)] = psm
                self.channels[(handle, direction, scid)] = psm

    # --- ATT -----------------------------------------------------------

    def _att(self, base, pdu):
        rec = dict(base, proto="att")
        if not pdu:
            rec["op"] = "empty"
            rec["payload"] = ""
            return rec
        op = pdu[0]
        rec["op"] = ATT_OPS.get(op, f"0x{op:02x}")
        conn = (base["handle"], base["dir"])
        if op in ATT_HANDLE_VALUE_OPS and len(pdu) >= 3:
            rec["att_handle"] = struct.unpack_from("<H", pdu, 1)[0]
            rec["payload"] = pdu[3:].hex()
        elif op == 0x0A and len(pdu) >= 3:
            att_handle = struct.unpack_from("<H", pdu, 1)[0]
            self.last_read[conn] = att_handle
            rec["att_handle"] = att_handle
            rec["payload"] = ""
        elif op == 0x0B:
            other = DIR_RX if base["dir"] == DIR_TX else DIR_TX
            rec["att_handle"] = self.last_read.pop((base["handle"], other), None)
            rec["payload"] = pdu[1:].hex()
        else:
            rec["payload"] = pdu[1:].hex()
        return rec

    # --- RFCOMM --------------------------------------------------------

    def _rfcomm(self, base, frame):
        if len(frame) < 4:
            return None
        addr, ctrl = frame[0], frame[1]
        dlci = addr >> 2
        pf = bool(ctrl & 0x10)
        ftype = RFCOMM_FRAME_TYPES.get(ctrl & ~0x10 & 0xFF, f"0x{ctrl:02x}")
        if frame[2] & 0x01:
            length = frame[2] >> 1
            off = 3
        else:
            if len(frame) < 5:
                return None
            length = (frame[2] >> 1) | (frame[3] << 7)
            off = 4
        rec = dict(base, proto="rfcomm", dlci=dlci, frame=ftype)
        if ftype == "UIH" and pf and dlci != 0:
            rec["credits"] = frame[off]
            off += 1
        rec["payload"] = frame[off : off + length].hex()
        return rec


def fmt_text(rec, t0):
    arrow = "->" if rec["dir"] == DIR_TX else "<-"
    head = f"{rec['t'] - t0:10.6f} {arrow} h{rec['handle']:03x}"
    proto = rec["proto"]
    if proto == "att":
        ah = rec.get("att_handle")
        ah = f"0x{ah:04x}" if ah is not None else "------"
        mid = f"ATT {rec['op']:<10} {ah}"
    elif proto == "rfcomm":
        cr = f" cr={rec['credits']}" if "credits" in rec else ""
        mid = f"RFCOMM {rec['frame']:<4} dlci={rec['dlci']:<2}{cr}"
    else:
        mid = f"L2CAP cid=0x{rec['cid']:04x} psm={rec.get('psm')}"
    return f"{head} {mid:<34} {rec['payload']}"


def parse_int(s):
    return int(s, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", help="btsnoop_hci.log")
    ap.add_argument("--jsonl", action="store_true", help="emit one JSON object per line")
    ap.add_argument("--handle", type=parse_int, help="only this ACL connection handle")
    ap.add_argument("--proto", choices=["att", "rfcomm", "l2cap"], help="only this protocol")
    ap.add_argument("--dlci", type=int, help="only this RFCOMM DLCI")
    ap.add_argument("--att-handle", type=parse_int, help="only this ATT attribute handle")
    ap.add_argument("--all", action="store_true",
                    help="include RFCOMM control frames, DLCI 0 and empty payloads")
    args = ap.parse_args(argv)

    ex = Extractor()
    t0 = None
    out = sys.stdout
    with open(args.log, "rb") as f:
        for ts, direction, pkt in read_records(f):
            for rec in ex.feed(ts, direction, pkt):
                if args.handle is not None and rec["handle"] != args.handle:
                    continue
                if args.proto and rec["proto"] != args.proto:
                    continue
                if args.dlci is not None and rec.get("dlci") != args.dlci:
                    continue
                if args.att_handle is not None and rec.get("att_handle") != args.att_handle:
                    continue
                if not args.all and rec["proto"] == "rfcomm":
                    if rec["frame"] != "UIH" or rec["dlci"] == 0 or not rec["payload"]:
                        continue
                if t0 is None:
                    t0 = rec["t"]
                if args.jsonl:
                    out.write(json.dumps(rec) + "\n")
                else:
                    out.write(fmt_text(rec, t0) + "\n")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
