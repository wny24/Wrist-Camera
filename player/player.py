"""Portable RTSP viewer. Standard-library supervisor, FFplay rendering."""
from __future__ import annotations

import argparse
import getpass
from functools import lru_cache
from collections import deque
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from diagnostics import Diagnostics, NetworkMonitor
from temperature import TemperatureMonitor, AdbTemperatureMonitor, temperature_text
from latency import DelayGrowth


class Health:
    def __init__(self):
        self.started = time.monotonic()
        self.last_frame = None
        self.frames = 0
        self.error = ""
        self.lock = threading.Lock()
        self.arrivals = deque()
        self.delay = DelayGrowth()

    def feed(self, line):
        with self.lock:
            if "showinfo" in line and re.search(r"\bn:\s*\d+\s+pts:", line):
                self.last_frame = time.monotonic()
                self.frames += 1
                pts = re.search(r"\bpts_time:([-+0-9.eE]+)", line)
                if pts:
                    try:
                        self.delay.update(float(pts.group(1)), self.last_frame)
                    except ValueError:
                        pass
                self.arrivals.append(self.last_frame)
                while self.arrivals and self.arrivals[0] < self.last_frame - 2:
                    self.arrivals.popleft()
            # Never display raw FFmpeg output: it can contain camera credentials.
            for marker, message in (
                ("401 Unauthorized", "认证失败，请检查用户名和密码"),
                ("403 Forbidden", "摄像头拒绝访问"),
                ("404 Not Found", "未找到视频流，请检查地址路径"),
                ("Connection refused", "连接被拒绝，请检查地址和摄像头状态"),
                ("Connection timed out", "连接超时"),
                ("Invalid data", "无法解析视频流"),
            ):
                if marker in line:
                    self.error = message

    def snapshot(self):
        with self.lock:
            return self.last_frame, self.frames, self.error

    def delay_snapshot(self, now):
        with self.lock:
            return self.delay.snapshot(now)

    def fps(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            while self.arrivals and self.arrivals[0] < now - 2:
                self.arrivals.popleft()
            if len(self.arrivals) < 2:
                return None
            duration = now - self.arrivals[0]
            return (len(self.arrivals) - 1) / duration if duration >= 0.5 else None


def overlay_text(fps):
    rate = "collecting / insufficient frames" if fps is None else f"{fps:.1f} fps"
    return ("%{eif:w:d} x %{eif:h:d} | Decode (2s): " + rate + "\n"
            r"Receiver: %{localtime:%H\:%M\:%S}.%{eif:mod(time(0)*1000,1000):d:3}" + "\n"
            "Receiver time is NOT capture time")


def atomic_text(folder, name, text):
    temporary = folder / (name + ".next")
    temporary.write_text(text, encoding="utf-8")
    try:
        os.replace(temporary, folder / name)
    except PermissionError:
        pass  # A frame may be reading the old complete file; retry next tick.


def write_overlay(folder, fps, network=None, temperature=None):
    atomic_text(folder, "stats.txt", overlay_text(fps).splitlines()[0])
    value = (network or {}).get("nic_rx_mbps")
    rate = "N/A" if value is None else f"{value:.2f} Mbps"
    atomic_text(folder, "network.txt", f"NIC Rx (TOTAL): {rate}")
    atomic_text(folder, "temperature.txt", temperature_text(temperature))


def find_font():
    override = os.environ.get("CAMERA_PLAYER_FONT")
    candidates = [Path(override)] if override else []
    if sys.platform == "win32":
        fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        candidates += [fonts / "consola.ttf", fonts / "arial.ttf"]
    else:
        candidates += [Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
                       Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf")]
    for font in candidates:
        if font.is_file():
            return font
    raise RuntimeError("未找到字体；Linux 请安装 fonts-dejavu-core，或设置 CAMERA_PLAYER_FONT。")


def prepare_overlay(folder):
    font = find_font()
    shutil.copyfile(font, folder / "overlay.ttf")
    write_overlay(folder, None)
    lines = overlay_text(None).splitlines()
    (folder / "clock.txt").write_text(lines[1], encoding="utf-8")
    (folder / "note.txt").write_text(lines[2], encoding="utf-8")
    filters = ["showinfo=checksum=0"]
    for index, filename in enumerate(("stats.txt", "network.txt", "temperature.txt", "clock.txt", "note.txt")):
        filters.append(f"drawtext=fontfile=overlay.ttf:textfile={filename}:reload={int(index < 3)}:"
                       "fontsize=h/30:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=6:"
                       f"x=12:y=12+{index}*h/22")
    return ",".join(filters)


def read_output(pipe, health):
    try:
        for line in iter(pipe.readline, b""):
            health.feed(line.decode("utf-8", errors="replace"))
    finally:
        pipe.close()


def validate_url(value):
    value = value.strip()
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname:
            raise ValueError
        _ = parsed.port
        if any(c.isspace() for c in value):
            raise ValueError
    except ValueError:
        raise ValueError("请输入完整的 rtsp:// 地址；特殊字符需要进行 URL 编码。") from None
    return value


def find_ffplay():
    root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    bundled = root / ("ffplay.exe" if sys.platform == "win32" else "ffplay")
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("ffplay")
    if not found:
        raise RuntimeError("找不到 FFplay；Ubuntu 请执行 sudo apt install ffmpeg。")
    return found


def rtsp_timeout_option(help_text):
    # FFmpeg 4.4 uses stimeout; its old timeout option has different semantics.
    return "-stimeout" if re.search(r"^\s*-stimeout\s", help_text, re.MULTILINE) else "-timeout"


@lru_cache(maxsize=4)
def detect_timeout_option(executable):
    try:
        result = subprocess.run([executable, "-hide_banner", "-h", "demuxer=rtsp"],
                                capture_output=True, timeout=5)
        return rtsp_timeout_option((result.stdout + result.stderr).decode(errors="replace"))
    except (OSError, subprocess.TimeoutExpired):
        return "-timeout"


def command(executable, url, transport="tcp", compatible=False):
    args = [executable, "-hide_banner", "-loglevel", "info", "-nostats",
            "-window_title", os.environ.get("CAMERA_PLAYER_TITLE", "Camera Live") + " | F: fullscreen | Q: exit",
            "-x", "1280", "-y", "720", "-an", "-sn", "-framedrop",
            "-sync", "ext", "-noinfbuf", "-rtsp_transport", transport,
            "-allowed_media_types", "video", detect_timeout_option(executable), "5000000",
            "-vf", "showinfo=checksum=0"]
    if not compatible:
        args += ["-fflags", "nobuffer", "-flags", "low_delay",
                 "-probesize", "262144", "-analyzeduration", "1000000"]
    if transport == "udp":
        args += ["-max_delay", "100000", "-reorder_queue_size", "64"]
    # No autoexit: clean exit means the user closed the window. A dead input
    # remains open and is restarted by the frame watchdog.
    return args + ["-i", url]


def stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def run_once(args, startup_timeout=20, stall_timeout=5, network=None, diagnostics=None, temperature=None):
    with tempfile.TemporaryDirectory(prefix="camera-player-") as temporary:
        folder = Path(temporary)
        args = list(args)
        if "-vf" in args:
            args[args.index("-vf") + 1] = prepare_overlay(folder)
        return _run_once(args, folder, startup_timeout, stall_timeout, network, diagnostics, temperature)


def _run_once(args, folder, startup_timeout, stall_timeout, network, diagnostics, temperature):
    health = Health()
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, cwd=folder,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    reader = threading.Thread(target=read_output, args=(process.stderr, health), daemon=True)
    reader.start()
    if diagnostics:
        diagnostics.attach(process.pid)
    announced = False
    next_update = 0
    next_log = 0
    try:
        while process.poll() is None:
            now = time.monotonic()
            last, frames, error = health.snapshot()
            net = network.snapshot() if network else {}
            thermal = temperature.snapshot() if temperature else {"soc_c": None, "soc_age_s": None, "soc_status": "OFF"}
            fps = health.fps(now)
            delay = health.delay_snapshot(now)
            if now >= next_update:
                write_overlay(folder, fps, net, thermal if temperature else None)
                next_update = now + 0.5
            if diagnostics and now >= next_log:
                diagnostics.sample(decode_fps=fps, frames=frames,
                                   frame_age_ms=None if last is None else round((now-last)*1000),
                                   uptime_s=round(now-health.started, 1), **net, **thermal, **delay)
                next_log = now + 1
            if last is not None and not announced:
                print("已收到画面。F / 双击：全屏；Q / Esc / 关闭画面窗口：退出。", flush=True)
                announced = True
                if diagnostics:
                    diagnostics.event("first_frame")
            if last is None and now - health.started > startup_timeout:
                if diagnostics:
                    diagnostics.event("startup_timeout", reason=error or "no frames")
                return "retry", False, error or "等待首帧超时"
            if last is not None and now - last > stall_timeout:
                if diagnostics:
                    diagnostics.event("frame_timeout", frame_age_ms=round((now-last)*1000))
                return "retry", now - health.started > 30, "画面中断，正在重新连接"
            if delay["backlog_detected"]:
                if diagnostics:
                    diagnostics.event("delay_growth_reconnect", **delay)
                return "resync", now - health.started > 30, "检测到视频时间戳持续落后，重新拉取实时画面"
            time.sleep(0.1)
        last, frames, error = health.snapshot()
        reader.join(timeout=1)
        last, frames, error = health.snapshot()
        if diagnostics:
            diagnostics.event("player_exit", code=process.returncode, reason=error)
        return ("closed" if process.returncode == 0 and not error else "retry"), bool(
            last is not None and time.monotonic() - health.started > 30), error or "连接已断开"
    finally:
        stop_process(process)
        reader.join(timeout=2)


def main():
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    parser = argparse.ArgumentParser(description="低延迟 RTSP 摄像头播放器")
    parser.add_argument("--url", help="RTSP 地址；省略时启动后输入")
    parser.add_argument("--transport", choices=("tcp", "udp"), default="tcp")
    parser.add_argument("--compatible", action="store_true", help="兼容模式：提高探测和缓存容忍度")
    parser.add_argument("--temperature", action="store_true", help="启用 Luckfox SSH 温度读取，启动时输入密码")
    parser.add_argument("--adb-serial", help="通过指定 USB/ADB 设备读取 SoC 温度，无需 SSH 密码")
    parser.add_argument("--ssh-user", default="root")
    parser.add_argument("--ssh-host", help="可选：温度读取的 SSH 主机，默认与 RTSP 主机相同")
    parser.add_argument("--ssh-port", type=int, default=22)
    parser.add_argument("--ssh-known-hosts", help="可选：指定已核验的 SSH known_hosts 文件")
    parser.add_argument("--ssh-password-stdin", action="store_true", help="自动化专用：从标准输入读取一行 SSH 密码")
    opts = parser.parse_args()
    network = diagnostics = temperature = None
    print("摄像头实时播放器 · 默认 TCP · 自动断线重连\n地址仅在本次运行使用，不保存到文件。\n")
    try:
        executable = find_ffplay()
        url = validate_url(opts.url or os.environ.get("CAMERA_RTSP_URL") or input("粘贴 RTSP 地址，然后回车：\n> "))
        parsed = urlsplit(url)
        enabled = opts.temperature
        if not enabled and not opts.adb_serial and not opts.url and sys.stdin.isatty():
            enabled = input("启用 Luckfox SoC 温度读取？[y/N]：").strip().lower() == "y"
        if opts.adb_serial:
            temperature = AdbTemperatureMonitor(opts.adb_serial)
            temperature.start()
        elif enabled:
            if not 1 <= opts.ssh_port <= 65535:
                raise ValueError("SSH 端口必须在 1–65535 之间。")
            ssh_host = opts.ssh_host or parsed.hostname
            print(f"通过 SSH 读取 {ssh_host} 的温度，用户 {opts.ssh_user}；密码仅用于本次运行。")
            if opts.ssh_password_stdin:
                password = sys.stdin.readline()
                if not password:
                    raise ValueError("未从标准输入读到 SSH 密码。")
                password = password.rstrip("\r\n")
            else:
                password = getpass.getpass("SSH 密码（输入不显示）：")
            temperature = TemperatureMonitor(ssh_host, opts.ssh_user, password, opts.ssh_port, opts.ssh_known_hosts)
            del password
            temperature.start()
        network = NetworkMonitor(parsed.hostname, parsed.port or 554)
        network.start()
        root = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        try:
            diagnostics = Diagnostics(root)
            print(f"诊断日志：{diagnostics.path}\n网速为摄像头路由网卡的总接收速率，包含其他摄像头和程序流量。", flush=True)
        except OSError:
            print("诊断日志不可写，继续播放。", flush=True)
        args = command(executable, url, opts.transport, opts.compatible)
        backoff = 1
        reconnects = 0
        while True:
            print("正在连接…（在此窗口按 Ctrl+C 可停止）", flush=True)
            if diagnostics:
                diagnostics.event("connecting", reconnects=reconnects, transport=opts.transport)
            result, stable, reason = run_once(args, network=network, diagnostics=diagnostics, temperature=temperature)
            if result == "closed":
                return 0
            if stable:
                backoff = 1
            if result == "resync":
                backoff = 1
            print(f"{reason}；{backoff} 秒后重试。", flush=True)
            reconnects += 1
            if diagnostics:
                diagnostics.event("reconnect", count=reconnects, reason=reason, wait_s=backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 8)
    except (KeyboardInterrupt, EOFError):
        print("\n已停止。")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        # Do not print OSError arguments, which could include the input URL.
        print(str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "无法启动播放内核，请检查文件是否完整。")
        if not opts.url:
            try:
                input("按回车退出…")
            except (EOFError, KeyboardInterrupt):
                pass
        return 1
    finally:
        if temperature:
            temperature.close()
        if network:
            network.close()
        if diagnostics:
            diagnostics.close()


if __name__ == "__main__":
    raise SystemExit(main())
