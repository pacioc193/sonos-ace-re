"""Tests for client/ace.py: command encoding checked against bytes seen in the captures.

Run: python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "client"))
import ace  # noqa: E402


class CommandEncoding(unittest.TestCase):
    def test_modes_match_capture(self):
        # EXP-01/02: 00 02 0f 02 (transparency), 00 (off), 01 (ANC)
        self.assertEqual(ace.mode_command("aware").hex(), "00020f02")
        self.assertEqual(ace.mode_command("off").hex(), "00020f00")
        self.assertEqual(ace.mode_command("anc").hex(), "00020f01")

    def test_signed_values_match_capture(self):
        # EXP-02: bass +10 = 0a, -10 = f6, -1 = ff; treble 1f; balance 22
        self.assertEqual(ace.bass_command(10).hex(), "00021e0a")
        self.assertEqual(ace.bass_command(-10).hex(), "00021ef6")
        self.assertEqual(ace.bass_command(-1).hex(), "00021eff")
        self.assertEqual(ace.treble_command(-6).hex(), "00021ffa")
        self.assertEqual(ace.balance_command(-3).hex(), "000222fd")
        self.assertEqual(ace.balance_command(0).hex(), "00022200")

    def test_range_checked(self):
        for fn in (ace.bass_command, ace.treble_command, ace.balance_command):
            with self.assertRaises(ValueError):
                fn(11)
            with self.assertRaises(ValueError):
                fn(-11)

    def test_unknown_mode(self):
        with self.assertRaises(ValueError):
            ace.mode_command("loud")

    def test_ack(self):
        cmd = ace.bass_command(4)
        self.assertTrue(ace.is_ack(cmd, bytes.fromhex("02021e00")))
        self.assertFalse(ace.is_ack(cmd, bytes.fromhex("02021f00")))
        self.assertFalse(ace.is_ack(cmd, bytes.fromhex("02021e01")))


class AgainstCapture(unittest.TestCase):
    """Re-encode every set command found in a real capture and compare byte for byte."""

    def test_replay(self):
        path = os.environ.get("ACE_JSONL")
        if not path or not os.path.exists(path):
            self.skipTest("set ACE_JSONL to a btsnoop_extract.py --jsonl file")
        import json

        checked = 0
        builders = {ace.ID_MODE: lambda v: ace.command(ace.ID_MODE, v),
                    ace.ID_BASS: lambda v: ace.command(ace.ID_BASS, v),
                    ace.ID_TREBLE: lambda v: ace.command(ace.ID_TREBLE, v),
                    ace.ID_BALANCE: lambda v: ace.command(ace.ID_BALANCE, v)}
        for line in open(path):
            r = json.loads(line)
            if r.get("proto") != "att" or r.get("att_handle") != 0x44 or r["dir"] != "tx":
                continue
            p = bytes.fromhex(r["payload"])
            if len(p) == 4 and p[1] == ace.CAT_SETTINGS and p[2] in builders:
                self.assertEqual(builders[p[2]](p[3]), p)
                checked += 1
        self.assertEqual(checked, 97)  # set commands in the EXP-02 capture


if __name__ == "__main__":
    unittest.main()
