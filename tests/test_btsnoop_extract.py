"""Tests for tools/btsnoop_extract.py against a synthetic btsnoop log.

Run: python3 -m unittest discover -s tests
"""

import io
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import btsnoop_extract as bx  # noqa: E402

PEER = bytes([0x66, 0x55, 0x44, 0x33, 0x22, 0x11])  # 11:22:33:44:55:66 on the wire


def record(direction, h4, ts_us=0):
    flags = 1 if direction == "rx" else 0
    ts = ts_us + bx.BTSNOOP_EPOCH_DELTA_US
    return struct.pack(">IIIIq", len(h4), len(h4), flags, 0, ts) + h4


def acl(handle, l2cap_frame, pb=0x2):
    return bytes([bx.H4_ACL]) + struct.pack("<HH", handle | (pb << 12), len(l2cap_frame)) + l2cap_frame


def l2cap(cid, payload):
    return struct.pack("<HH", len(payload), cid) + payload


def rfcomm_uih(dlci, payload, credits=None, cr=1):
    addr = (dlci << 2) | (cr << 1) | 1
    ctrl = 0xFF if credits is not None else 0xEF
    n = len(payload)
    length = bytes([(n << 1) | 1]) if n < 128 else struct.pack("<H", n << 1)
    body = bytes([addr, ctrl]) + length
    if credits is not None:
        body += bytes([credits])
    return body + payload + b"\x00"  # FCS (not checked)


def build_log():
    recs = []
    t = 1_000_000
    # BR/EDR Connection Complete, handle 0x000b
    recs.append(record("rx", bytes([bx.H4_EVT, 0x03, 11, 0x00]) + struct.pack("<H", 0x0B) + PEER + b"\x01\x00", t))
    # L2CAP Connection Request PSM=RFCOMM scid=0x0041 (phone -> headset), id=7
    req = struct.pack("<BBHHH", 0x02, 7, 4, bx.PSM_RFCOMM, 0x0041)
    recs.append(record("tx", acl(0x0B, l2cap(bx.CID_SIGNALING, req)), t + 1))
    # Response: dcid=0x0070 scid=0x0041 result=success
    rsp = struct.pack("<BBHHHHH", 0x03, 7, 8, 0x0070, 0x0041, 0, 0)
    recs.append(record("rx", acl(0x0B, l2cap(bx.CID_SIGNALING, rsp)), t + 2))
    # UIH with credits on DLCI 18, phone -> headset, addressed to dcid 0x0070,
    # split into two ACL fragments
    frame = l2cap(0x0070, rfcomm_uih(18, bytes.fromhex("aa0102030405"), credits=5))
    recs.append(record("tx", acl(0x0B, frame[:5], pb=0x0), t + 3))
    recs.append(record("tx", acl(0x0B, frame[5:], pb=0x1), t + 4))
    # Reply headset -> phone on scid 0x0041, long payload (2-byte length)
    long_payload = bytes(range(200))
    recs.append(record("rx", acl(0x0B, l2cap(0x0041, rfcomm_uih(18, long_payload, cr=0))), t + 5))
    # LE Connection Complete, handle 0x0040
    le = bytes([0x01, 0x00]) + struct.pack("<H", 0x40) + b"\x00\x00" + PEER + b"\x00" * 7
    recs.append(record("rx", bytes([bx.H4_EVT, 0x3E, len(le)]) + le, t + 6))
    # ATT write command handle 0x002a value 01 02
    recs.append(record("tx", acl(0x40, l2cap(bx.CID_ATT, bytes([0x52, 0x2A, 0x00, 0x01, 0x02]))), t + 7))
    # ATT read req 0x0030 / read rsp
    recs.append(record("tx", acl(0x40, l2cap(bx.CID_ATT, bytes([0x0A, 0x30, 0x00]))), t + 8))
    recs.append(record("rx", acl(0x40, l2cap(bx.CID_ATT, bytes([0x0B, 0xDE, 0xAD]))), t + 9))
    # Notify handle 0x002c
    recs.append(record("rx", acl(0x40, l2cap(bx.CID_ATT, bytes([0x1B, 0x2C, 0x00, 0x07]))), t + 10))
    header = bx.BTSNOOP_MAGIC + struct.pack(">II", 1, bx.DATALINK_H4)
    return header + b"".join(recs)


def extract_all():
    ex = bx.Extractor()
    out = []
    for ts, d, pkt in bx.read_records(io.BytesIO(build_log())):
        out.extend(ex.feed(ts, d, pkt))
    return out


class ExtractTest(unittest.TestCase):
    def setUp(self):
        self.recs = extract_all()

    def test_rfcomm_reassembly_and_credits(self):
        r = [x for x in self.recs if x["proto"] == "rfcomm"]
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["dir"], "tx")
        self.assertEqual(r[0]["dlci"], 18)
        self.assertEqual(r[0]["credits"], 5)
        self.assertEqual(r[0]["payload"], "aa0102030405")
        self.assertEqual(r[0]["addr"], "11:22:33:44:55:66")

    def test_rfcomm_long_length(self):
        r = [x for x in self.recs if x["proto"] == "rfcomm"][1]
        self.assertEqual(r["dir"], "rx")
        self.assertNotIn("credits", r)
        self.assertEqual(r["payload"], bytes(range(200)).hex())

    def test_att(self):
        a = [x for x in self.recs if x["proto"] == "att"]
        ops = [(x["op"], x.get("att_handle"), x["payload"]) for x in a]
        self.assertEqual(ops, [
            ("write_cmd", 0x2A, "0102"),
            ("read_req", 0x30, ""),
            ("read_rsp", 0x30, "dead"),
            ("notify", 0x2C, "07"),
        ])

    def test_text_format(self):
        line = bx.fmt_text(self.recs[0], self.recs[0]["t"])
        self.assertIn("RFCOMM UIH", line)
        self.assertIn("dlci=18", line)


if __name__ == "__main__":
    unittest.main()
