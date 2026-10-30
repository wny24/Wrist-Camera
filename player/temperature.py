"""Read-only Luckfox SoC telemetry over one reusable SSH connection."""
from pathlib import Path
import socket
import subprocess
import threading
import time

import paramiko

READ_TEMPERATURE = "cat /sys/class/thermal/thermal_zone0/type /sys/class/thermal/thermal_zone0/temp"


def parse_temperature(data):
    lines = data.decode("ascii", errors="strict").split()
    if len(lines) != 2 or lines[0] != "soc-thermal":
        raise ValueError("Unexpected sensor")
    value = int(lines[1]) / 1000
    if not -100 <= value <= 200:
        raise ValueError("Invalid sensor value")
    return value


class UnknownHostKey(paramiko.SSHException):
    pass


class RequireKnownHost(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        raise UnknownHostKey("Verify this board with SSH on this computer first")


def temperature_text(data):
    if not data:
        return "SoC: OFF"
    value, age, status = data.get("soc_c"), data.get("soc_age_s"), data.get("soc_status")
    if value is None:
        return f"SoC: N/A ({status})"
    if status != "OK":
        return f"SoC: {value:.1f} C | STALE {age:.0f}s ({status})"
    return f"SoC: {value:.1f} C | age {age:.1f}s"


class TemperatureMonitor:
    def __init__(self, host, username, password, port=22, known_hosts=None, interval=2):
        self.host, self.username, self.password, self.port = host, username, password, port
        self.known_hosts = Path(known_hosts) if known_hosts else Path.home() / ".ssh/known_hosts"
        self.interval = interval
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.value = self.updated = None
        self.status = "CONNECTING"
        self.client = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def snapshot(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            age = None if self.updated is None else max(0, now - self.updated)
            status = self.status
            if status == "OK" and age is not None and age > 6:
                status = "STALE"
            return {"soc_c": self.value, "soc_age_s": None if age is None else round(age, 1),
                    "soc_status": status}

    def set_status(self, status):
        with self.lock:
            changed = status != self.status
            self.status = status
        if changed and status != "OK":
            print(f"温度读取：{status}（视频播放继续）", flush=True)

    def connect(self):
        client = paramiko.SSHClient()
        self.client = client
        if self.known_hosts.is_file():
            client.load_host_keys(str(self.known_hosts))
        client.set_missing_host_key_policy(RequireKnownHost())
        client.connect(self.host, port=self.port, username=self.username, password=self.password,
                       timeout=3, banner_timeout=3, auth_timeout=3, channel_timeout=3,
                       look_for_keys=False, allow_agent=False)
        client.get_transport().set_keepalive(10)
        return client

    def read(self, client):
        channel = client.get_transport().open_session(timeout=3)
        channel.settimeout(3)
        try:
            channel.exec_command(READ_TEMPERATURE)
            deadline = time.monotonic() + 3
            data = bytearray()
            while not self.stop.is_set():
                if time.monotonic() > deadline:
                    raise TimeoutError
                if channel.recv_ready():
                    data.extend(channel.recv(256))
                    if len(data) > 256:
                        raise ValueError("Oversize sensor response")
                    continue
                if channel.exit_status_ready():
                    code = channel.recv_exit_status()
                    if code == -1:
                        raise EOFError("SSH connection closed")
                    if code != 0:
                        raise ValueError("Sensor unavailable")
                    while channel.recv_ready():
                        data.extend(channel.recv(256))
                        if len(data) > 256:
                            raise ValueError("Oversize sensor response")
                    return parse_temperature(bytes(data))
                self.stop.wait(0.02)
            raise InterruptedError
        finally:
            channel.close()

    def run(self):
        delay = 2
        try:
            while not self.stop.is_set():
                terminal = False
                try:
                    client = self.connect()
                    while not self.stop.is_set():
                        value = self.read(client)
                        with self.lock:
                            self.value, self.updated, self.status = value, time.monotonic(), "OK"
                        delay = 2
                        self.stop.wait(self.interval)
                except UnknownHostKey:
                    self.set_status("VERIFY SSH HOST FIRST")
                    # Reload known_hosts on the next attempt: users may verify
                    # this board in Windows SSH while video keeps playing.
                    delay = 15
                except paramiko.BadHostKeyException:
                    self.set_status("HOST KEY CHANGED")
                    terminal = True
                except paramiko.AuthenticationException:
                    self.set_status("AUTH FAILED")
                    terminal = True
                except (ValueError, UnicodeError):
                    self.set_status("SENSOR / CONFIG ERROR")
                    terminal = True
                except (OSError, EOFError, paramiko.SSHException):
                    if not self.stop.is_set():
                        self.set_status("DISCONNECTED")
                finally:
                    if self.client:
                        self.client.close()
                        self.client = None
                if terminal:
                    break
                self.stop.wait(delay)
                delay = min(15, delay * 2)
        finally:
            self.password = None

    def close(self):
        self.stop.set()
        client = self.client
        if client:
            client.close()
        self.thread.join(timeout=1)
        self.password = None


class AdbTemperatureMonitor(TemperatureMonitor):
    """Read the selected board's sensor over USB, without SSH credentials."""

    def __init__(self, serial, interval=2):
        super().__init__("", "", None, interval=interval)
        self.serial = serial

    def run(self):
        while not self.stop.is_set():
            try:
                result = subprocess.run(
                    ["adb", "-s", self.serial, "shell", READ_TEMPERATURE],
                    capture_output=True, timeout=3, check=True)
                value = parse_temperature(result.stdout)
                with self.lock:
                    self.value, self.updated, self.status = value, time.monotonic(), "OK"
            except (ValueError, UnicodeError):
                self.set_status("SENSOR / CONFIG ERROR")
            except (OSError, subprocess.SubprocessError):
                self.set_status("USB DISCONNECTED")
            self.stop.wait(self.interval)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=4)
