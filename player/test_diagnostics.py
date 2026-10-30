import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diagnostics import Diagnostics, RateCounter, route_interface
from player import Health, prepare_overlay, write_overlay


class DiagnosticsTests(unittest.TestCase):
    def test_mbps_and_reset(self):
        rate = RateCounter()
        self.assertIsNone(rate.update("wifi", 100, 1))
        self.assertEqual(rate.update("wifi", 1_000_100, 2), 8)
        self.assertIsNone(rate.update("ethernet", 2_000_100, 3))
        self.assertIsNone(rate.update("ethernet", 0, 4))
        self.assertIsNone(rate.update("ethernet", 10, 4))

    def test_frame_numbers_do_not_trigger_auth_errors(self):
        health = Health()
        health.feed("[showinfo] n: 401 pts: 404 s:1920x1080")
        self.assertEqual(health.snapshot()[2], "")

    def test_logs_are_isolated_bounded_and_slots_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Diagnostics(folder), Diagnostics(folder)
            self.assertNotEqual(first.path, second.path)
            first.event("reconnect", reason="frame timeout", count=1)
            handler = first.logger.handlers[0]
            self.assertEqual(handler.maxBytes, 2_000_000)
            self.assertEqual(handler.backupCount, 2)
            path = first.path
            first.close()
            third = Diagnostics(folder)
            self.assertEqual(third.path, path)
            third.close()
            second.close()
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(any(r["event"] == "reconnect" for r in rows))
            self.assertFalse(list(Path(folder).rglob("*.lock")))

    def test_atomic_overlay_identifies_total_interface_traffic(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            prepare_overlay(path)
            write_overlay(path, 25, {"nic_rx_mbps": 12.345})
            text = (path / "network.txt").read_text()
            self.assertEqual(text, "NIC Rx (TOTAL): 12.35 Mbps")
            write_overlay(path, None, {})
            self.assertIn("N/A", (path / "network.txt").read_text())


if __name__ == "__main__":
    unittest.main()
