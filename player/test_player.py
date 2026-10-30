import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from player import Health, command, run_once, validate_url, overlay_text


class PlayerTests(unittest.TestCase):
    def test_actual_fps_uses_wall_clock_and_expires(self):
        health = Health()
        for i in range(61):
            with patch("player.time.monotonic", return_value=10 + i / 30):
                health.feed(f"[showinfo] n: {i} pts: {i} s:1920x1080")
        self.assertAlmostEqual(health.fps(12), 30, places=5)
        self.assertIsNone(health.fps(15))

    def test_overlay_distinguishes_receiver_time(self):
        text = overlay_text(29.97)
        self.assertIn("30.0 fps", text)
        self.assertIn("time(0)*1000", text)
        self.assertIn("NOT capture time", text)

    def test_url_validation(self):
        self.assertEqual(validate_url(" rtsp://u:p@127.0.0.1:8554/live "), "rtsp://u:p@127.0.0.1:8554/live")
        for bad in ("http://camera/live", "rtsp://", "rtsp://host:bad/live", "rtsp://a b/live"):
            with self.assertRaises(ValueError):
                validate_url(bad)

    def test_health_ignores_stats_and_redacts_errors(self):
        health = Health()
        health.feed("10.2 M-V: 0.0")
        self.assertIsNone(health.snapshot()[0])
        health.feed("[Parsed_showinfo_0] n:   42 pts:  234 pts_time:1.2")
        self.assertEqual(health.snapshot()[1], 1)
        health.feed("rtsp://secret:password@camera failed: 401 Unauthorized")
        self.assertNotIn("password", health.snapshot()[2])

    def test_arguments_keep_url_single_and_bound_buffers(self):
        url = "rtsp://user:p%26ss@host/live?a=1&b=2"
        args = command("ffplay", url)
        self.assertEqual(args[-1], url)
        self.assertIn("-noinfbuf", args)
        self.assertNotIn("-autoexit", args)
        self.assertNotIn("nobuffer", command("ffplay", url, compatible=True))

    def test_watchdog_kills_hung_process(self):
        processes = []
        real_popen = subprocess.Popen
        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process
        with patch("player.subprocess.Popen", side_effect=record):
            result = run_once([sys.executable, "-c", "import time; time.sleep(30)"], startup_timeout=0.2)
        self.assertEqual(result[0], "retry")
        self.assertIsNotNone(processes[0].poll())

    def test_stalled_frames_restart(self):
        script = "import sys,time; print('[Parsed_showinfo_0] n: 0 pts: 0',file=sys.stderr,flush=True); time.sleep(30)"
        result = run_once([sys.executable, "-c", script], startup_timeout=2, stall_timeout=0.2)
        self.assertEqual(result[0], "retry")
        self.assertIn("画面中断", result[2])

    def test_clean_exit_does_not_reconnect(self):
        self.assertEqual(run_once([sys.executable, "-c", "pass"])[0], "closed")

    def test_error_exit_reconnects(self):
        self.assertEqual(run_once([sys.executable, "-c", "raise SystemExit(1)"])[0], "retry")

    def test_connection_refused_with_zero_exit_reconnects(self):
        script = "import sys; print('Connection refused', file=sys.stderr)"
        self.assertEqual(run_once([sys.executable, "-c", script])[0], "retry")


if __name__ == "__main__":
    unittest.main()
