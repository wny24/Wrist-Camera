"""Local, bounded diagnostics. Never accepts a complete RTSP URL for logging."""
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import threading
import time

import psutil


class RateCounter:
    def __init__(self):
        self.previous = None

    def update(self, interface, received, now):
        previous = self.previous
        self.previous = (interface, received, now)
        if previous is None or previous[0] != interface or received < previous[1]:
            return None
        elapsed = now - previous[2]
        return (received - previous[1]) * 8 / elapsed / 1_000_000 if elapsed > 0 else None


def route_interface(host, port):
    for family, kind, protocol, _, address in socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM):
        try:
            with socket.socket(family, kind, protocol) as sock:
                sock.connect(address)  # Route lookup only: no application data sent.
                local = sock.getsockname()[0].split("%")[0]
            for name, addresses in psutil.net_if_addrs().items():
                if any(a.address.split("%")[0] == local for a in addresses):
                    return name
        except OSError:
            continue
    return None


class NetworkMonitor:
    def __init__(self, host, port=554):
        self.host, self.port = host, port
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.data = {"nic": None, "nic_rx_mbps": None}
        self.worker = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.worker.start()

    def snapshot(self):
        with self.lock:
            return dict(self.data)

    def run(self):
        counter = RateCounter()
        interface, next_route = None, 0
        while not self.stop_event.is_set():
            try:
                now = time.monotonic()
                if now >= next_route:
                    interface = route_interface(self.host, self.port)
                    next_route = now + 10
                stats = psutil.net_io_counters(pernic=True, nowrap=False).get(interface)
                rate = counter.update(interface, stats.bytes_recv, now) if stats else None
                if stats is None:
                    counter.previous = None
                with self.lock:
                    self.data = {"nic": interface, "nic_rx_mbps": rate}
            except (OSError, psutil.Error):
                counter.previous = None
                with self.lock:
                    self.data = {"nic": None, "nic_rx_mbps": None}
            self.stop_event.wait(1)

    def close(self):
        self.stop_event.set()
        self.worker.join(timeout=1)


class Diagnostics:
    def __init__(self, root):
        self.logger = logging.Logger(f"camera-{os.getpid()}")
        folder = Path(root) / "logs"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CameraPlayer/logs"
            folder.mkdir(parents=True, exist_ok=True)
        # One bounded file set per live process slot. Reuse inactive slots across
        # launches, so repeated launches do not create unlimited log files.
        for slot in range(100):
            lock = folder / f"camera-{slot}.lock"
            try:
                with lock.open("x") as stream:
                    stream.write(str(os.getpid()))
                self.lock_path = lock
                break
            except FileExistsError:
                try:
                    pid = int(lock.read_text())
                    if not psutil.pid_exists(pid):
                        lock.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
        else:
            raise OSError("No diagnostic log slot available")
        self.path = folder / f"camera-{slot}.jsonl"
        handler = RotatingFileHandler(self.path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        self.logger.addHandler(handler)
        self.process = None
        self.event("session_start")

    def event(self, event, **values):
        self.logger.info(json.dumps({"time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                                    "event": event, **values}, ensure_ascii=False))

    def attach(self, pid):
        try:
            self.process = psutil.Process(pid)
            self.process.cpu_percent()
        except psutil.Error:
            self.process = None

    def sample(self, **values):
        try:
            if self.process is not None:
                values.update(player_cpu_percent=self.process.cpu_percent(),
                              player_rss_mb=self.process.memory_info().rss / 1_000_000)
        except psutil.Error:
            pass
        self.event("sample", **values)

    def close(self):
        self.event("session_end")
        for handler in self.logger.handlers:
            handler.close()
        self.lock_path.unlink(missing_ok=True)
