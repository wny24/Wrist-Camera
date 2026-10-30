from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import paramiko
from temperature import TemperatureMonitor, parse_temperature, temperature_text, READ_TEMPERATURE


class SSHFixture:
    def __init__(self, folder):
        self.key = paramiko.RSAKey.generate(2048)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.stop = threading.Event()
        self.transports = []
        self.commands = []
        self.auth_count = 0
        self.known_hosts = Path(folder) / "known_hosts"
        self.known_hosts.write_text(f"[127.0.0.1]:{self.port} {self.key.get_name()} {self.key.get_base64()}\n")
        owner = self
        class Server(paramiko.ServerInterface):
            def check_auth_password(self, username, password):
                owner.auth_count += 1
                return paramiko.AUTH_SUCCESSFUL if username == "root" and password == "test-only" else paramiko.AUTH_FAILED

            def get_allowed_auths(self, username):
                return "password"

            def check_channel_request(self, kind, channel_id):
                return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

            def check_channel_exec_request(self, channel, command):
                owner.commands.append(command.decode())
                def reply():
                    time.sleep(0.05)
                    try:
                        channel.sendall(b"soc-thermal\n66584\n")
                        channel.send_exit_status(0)
                        channel.shutdown_write()
                    except OSError:
                        pass
                threading.Thread(target=reply, daemon=True).start()
                return True
        self.server_class = Server
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                sock, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            transport = paramiko.Transport(sock)
            self.transports.append(transport)
            transport.add_server_key(self.key)
            try:
                transport.start_server(server=self.server_class())
            except (EOFError, paramiko.SSHException):
                transport.close()

    def close(self):
        self.stop.set()
        self.sock.close()
        for transport in self.transports:
            transport.close()
        self.thread.join(1)


class TemperatureTests(unittest.TestCase):
    def test_confirmed_board_value(self):
        self.assertEqual(parse_temperature(b"soc-thermal\n66584\n"), 66.584)
        for invalid in (b"cpu\n66584", b"soc-thermal\nnan", b"soc-thermal\n999999", b"66584"):
            with self.assertRaises(ValueError):
                parse_temperature(invalid)

    def test_stale_and_off_labels(self):
        monitor = TemperatureMonitor("unused", "root", "secret")
        monitor.value, monitor.updated, monitor.status = 66.584, 10, "OK"
        self.assertIn("66.6 C", temperature_text(monitor.snapshot(11)))
        self.assertIn("STALE", temperature_text(monitor.snapshot(17)))
        self.assertEqual(temperature_text(None), "SoC: OFF")

    def test_real_ssh_read_reuse_and_reconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            server = SSHFixture(folder)
            monitor = TemperatureMonitor("127.0.0.1", "root", "test-only", server.port, server.known_hosts, interval=0.1)
            try:
                monitor.start()
                deadline = time.monotonic() + 6
                while len(server.commands) < 3 and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(monitor.snapshot()["soc_c"], 66.584)
                self.assertEqual(server.auth_count, 1)
                self.assertTrue(all(c == READ_TEMPERATURE for c in server.commands))
                old_updated = monitor.updated
                for transport in list(server.transports):
                    transport.close()
                deadline = time.monotonic() + 8
                while (server.auth_count < 2 or monitor.snapshot()["soc_status"] != "OK") and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertGreaterEqual(server.auth_count, 2)
                self.assertGreater(monitor.updated, old_updated)
                self.assertEqual(monitor.snapshot()["soc_status"], "OK")
            finally:
                monitor.close()
                server.close()
            self.assertIsNone(monitor.password)
            self.assertFalse(monitor.thread.is_alive())

    def test_unknown_host_is_rejected_before_auth(self):
        with tempfile.TemporaryDirectory() as folder:
            server = SSHFixture(folder)
            monitor = TemperatureMonitor("127.0.0.1", "root", "test-only", server.port, Path(folder)/"missing")
            try:
                monitor.start()
                deadline = time.monotonic() + 4
                while monitor.snapshot()["soc_status"] == "CONNECTING" and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(monitor.snapshot()["soc_status"], "VERIFY SSH HOST FIRST")
                self.assertEqual(server.auth_count, 0)
            finally:
                monitor.close()
                server.close()

    def test_wrong_password_stops_retrying(self):
        with tempfile.TemporaryDirectory() as folder:
            server = SSHFixture(folder)
            monitor = TemperatureMonitor("127.0.0.1", "root", "wrong", server.port, server.known_hosts)
            try:
                monitor.start()
                monitor.thread.join(5)
                self.assertEqual(monitor.snapshot()["soc_status"], "AUTH FAILED")
                self.assertFalse(monitor.thread.is_alive())
            finally:
                monitor.close()
                server.close()


if __name__ == "__main__":
    unittest.main()
