import unittest
import sys
from unittest.mock import patch
from latency import DelayGrowth
from player import Health, run_once


class DelayTests(unittest.TestCase):
    def test_supervisor_reopens_accumulated_stream(self):
        script = "import sys,time\nfor i in range(45):\n print(f'[showinfo] n: {i} pts: {i} pts_time:{i*0.01}',file=sys.stderr,flush=True)\n time.sleep(0.1)"
        result = run_once([sys.executable, '-c', script], startup_timeout=2, stall_timeout=5)
        self.assertEqual(result[0], 'resync')

    def test_constant_unknown_delay_is_not_claimed_as_measured(self):
        delay = DelayGrowth()
        for i in range(1000):
            delay.update(i/25, 100+i/25)
        self.assertEqual(delay.snapshot(140)["delay_growth_ms"], 0)
        self.assertFalse(delay.snapshot(140)["backlog_detected"])

    def test_accumulation_despite_continuous_frames(self):
        health = Health()
        for i in range(1000):
            with patch("player.time.monotonic", return_value=100+i/24):
                health.feed(f"[showinfo] n: {i} pts: {i} pts_time:{i/25}")
        self.assertTrue(health.delay_snapshot(100+999/24)["backlog_detected"])

    def test_brief_jitter_recovers(self):
        delay = DelayGrowth()
        delay.update(0,100)
        delay.update(1,102)
        delay.update(2,102.1)
        self.assertFalse(delay.snapshot(105)["backlog_detected"])

    def test_timestamp_reset_rebases(self):
        delay = DelayGrowth()
        delay.update(100,200)
        delay.update(0,201)
        self.assertEqual(delay.snapshot(201)["pts_resets"],1)
        self.assertEqual(delay.snapshot(201)["delay_growth_ms"],0)


if __name__ == '__main__':
    unittest.main()
