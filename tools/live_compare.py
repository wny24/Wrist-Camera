"""Live RGB comparison: independent latest frames, never exposure-synchronized."""

import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import signal
import subprocess
from settings import ROOT, comparison_args, resolve_comparison, ensure_forward
import threading
import time
import tkinter as tk

import av
import numpy as np
from PIL import Image, ImageTk
import pyrealsense2 as rs


@dataclass
class Camera:
    name: str
    image: object = None
    received: float = 0
    source: float = 0
    sequence: int = 0
    status: str = "Connecting"
    domain: str = ""
    arrivals: deque = field(default_factory=deque)
    lock: object = field(default_factory=threading.Lock)

    def publish(self, rgb, source, domain):
        now = time.monotonic()
        with self.lock:
            self.image = rgb
            self.received, self.source, self.domain = now, source, domain
            self.sequence += 1
            self.status = "LIVE"
            self.arrivals.append(now)
            while self.arrivals and self.arrivals[0] < now - 3:
                self.arrivals.popleft()

    def set_status(self, status):
        with self.lock:
            self.status = status
            self.arrivals.clear()

    def snapshot(self):
        now = time.monotonic()
        with self.lock:
            times = [t for t in self.arrivals if t >= now - 3]
            fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0
            age = now - self.received if self.received else None
            return dict(
                name=self.name,
                image=self.image,
                sequence=self.sequence,
                received=self.received,
                source=self.source,
                domain=self.domain,
                status=self.status,
                age=age,
                fps=fps,
            )


class Capture:
    def __init__(self, args):
        self.args = args
        self.stop = threading.Event()
        self.forward_ready = threading.Event()
        self.cameras = [Camera("LUCKFOX / SC3336"), Camera("REALSENSE D435i / RGB")]
        self.threads = []

    def start(self):
        for target in (self.forward_loop, self.luckfox, self.realsense):
            worker = threading.Thread(target=target, daemon=True)
            worker.start()
            self.threads.append(worker)

    def forward_loop(self):
        a = self.args
        while not self.stop.is_set():
            try:
                ensure_forward(a.luckfox_serial, a.port)
                self.forward_ready.set()
            except ValueError:
                self.forward_ready.clear()
                self.cameras[0].set_status("ADB port belongs to another camera")
            except (OSError, subprocess.SubprocessError, RuntimeError):
                self.forward_ready.clear()
                self.cameras[0].set_status("Waiting for USB / ADB")
            self.stop.wait(2)

    def luckfox(self):
        camera = self.cameras[0]
        while not self.stop.is_set():
            if not self.forward_ready.wait(0.5):
                continue
            try:
                with av.open(
                    f"rtsp://127.0.0.1:{self.args.port}/live/{self.args.stream}",
                    options={
                        "rtsp_transport": "tcp",
                        "fflags": "nobuffer",
                        "flags": "low_delay",
                        "probesize": "262144",
                        "analyzeduration": "1000000",
                    },
                    timeout=(5, 3),
                ) as container:
                    for frame in container.decode(video=0):
                        if self.stop.is_set():
                            return
                        camera.publish(
                            frame.to_ndarray(format="rgb24"),
                            float(frame.pts * frame.time_base)
                            if frame.pts is not None
                            else None,
                            "RTSP PTS",
                        )
                camera.set_status("Stream ended; reconnecting")
            except Exception as exc:
                if not self.stop.is_set():
                    camera.set_status("USB / RTSP unavailable; retrying")
                    print(f"Luckfox: {type(exc).__name__}", flush=True)
            self.stop.wait(2)

    def realsense(self):
        camera = self.cameras[1]
        while not self.stop.is_set():
            pipeline, sensor, original = rs.pipeline(), None, None
            started = False
            try:
                config = rs.config()
                config.enable_device(self.args.realsense_serial)
                config.enable_stream(rs.stream.color, 1920, 1080, rs.format.rgb8, 30)
                profile = pipeline.start(config)
                started = True
                sensor = profile.get_device().first_color_sensor()
                if sensor.supports(rs.option.auto_exposure_priority):
                    original = sensor.get_option(rs.option.auto_exposure_priority)
                    sensor.set_option(rs.option.auto_exposure_priority, 0)
                while not self.stop.is_set():
                    frame = pipeline.wait_for_frames(3000).get_color_frame()
                    camera.publish(
                        np.asanyarray(frame.get_data()).copy(),
                        frame.get_timestamp() / 1000,
                        str(frame.get_frame_timestamp_domain()).split(".")[-1],
                    )
            except Exception as exc:
                if not self.stop.is_set():
                    camera.set_status("Unavailable; pause other viewer streams")
                    print(f"RealSense: {exc}", flush=True)
            finally:
                if sensor is not None and original is not None:
                    try:
                        sensor.set_option(rs.option.auto_exposure_priority, original)
                    except RuntimeError:
                        pass
                if started:
                    try:
                        pipeline.stop()
                    except RuntimeError:
                        pass
            self.stop.wait(2)

    def close(self):
        self.stop.set()
        deadline = time.monotonic() + 7
        for worker in self.threads:
            worker.join(max(0, deadline - time.monotonic()))


class Viewer:
    BG = "#10151d"

    def __init__(self, root, capture):
        self.root, self.capture = root, capture
        self.mode, self.fullscreen = "both", False
        root.title("Camera comparison | Luckfox + RealSense")
        root.geometry("1500x650")
        root.minsize(800, 450)
        root.configure(bg=self.BG)
        bar = tk.Frame(root, bg=self.BG)
        bar.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(
            bar,
            text="CAMERA COMPARISON",
            font=("DejaVu Sans", 16, "bold"),
            fg="#edf2fa",
            bg=self.BG,
        ).pack(side="left")
        for label, callback in [
            ("Both [0]", lambda: self.set_mode("both")),
            ("Luckfox [1]", lambda: self.set_mode(0)),
            ("RealSense [2]", lambda: self.set_mode(1)),
            ("Snapshot [S]", self.save),
            ("Fullscreen [F]", self.toggle_fullscreen),
        ]:
            tk.Button(
                bar,
                text=label,
                command=callback,
                bg="#263446",
                fg="white",
                activebackground="#3b506b",
                activeforeground="white",
                relief="flat",
                padx=9,
                pady=6,
            ).pack(side="left", padx=(8, 0))
        tk.Label(
            root,
            text="RGB 1920 x 1080 / target 30 fps  |  Latest frames, NOT exposure-synchronized",
            bg=self.BG,
            fg="#a9b6ca",
            anchor="w",
        ).pack(fill="x", padx=18)
        self.canvas = tk.Canvas(root, bg=self.BG, highlightthickness=0)
        self.footer = tk.Label(
            root,
            text="0: side by side    1 / 2: enlarge    S: snapshot    Q / Esc: quit",
            fg="#a9b6ca",
            bg=self.BG,
            anchor="w",
        )
        self.footer.pack(side="bottom", fill="x", padx=18, pady=(0, 12))
        self.canvas.pack(fill="both", expand=True, padx=12, pady=10)
        self.photos, self.cache = {}, {}
        self.last_states = None
        root.bind("<Key>", self.key)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        self.update()

    def set_mode(self, mode):
        self.mode = mode

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def key(self, event):
        key = event.keysym.lower()
        if key in ("q", "escape"):
            self.root.destroy()
        elif key == "f":
            self.toggle_fullscreen()
        elif key == "s":
            self.save()
        elif key in ("0", "1", "2"):
            self.set_mode("both" if key == "0" else int(key) - 1)

    def update(self):
        states = [c.snapshot() for c in self.capture.cameras]
        self.last_states = states
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.canvas.delete("all")
        indexes = [0, 1] if self.mode == "both" else [self.mode]
        for slot, index in enumerate(indexes):
            state = states[index]
            x = slot * width / len(indexes) + 6
            panel_w = max(1, width / len(indexes) - 12)
            self.canvas.create_rectangle(
                x, 0, x + panel_w, height, fill="#192330", outline=""
            )
            color = "#52dcc3" if index == 0 else "#75afff"
            self.canvas.create_text(
                x + 14,
                20,
                text=state["name"],
                anchor="w",
                fill=color,
                font=("DejaVu Sans", 12, "bold"),
            )
            stale = state["age"] is None or state["age"] > 1
            status = (
                state["status"]
                if state["status"] != "LIVE"
                else ("STALE" if stale else "LIVE")
            )
            self.canvas.create_text(
                x + 14,
                45,
                text=f"{status}   |   RGB ready: {state['fps']:.2f} fps (3s)",
                fill="#e2e9f3" if not stale else "#ffbf69",
                anchor="w",
            )
            available_h = max(1, height - 120)
            if state["image"] is not None:
                image = state["image"]
                h, w = image.shape[:2]
                scale = min((panel_w - 20) / w, available_h / h)
                size = (max(1, int(w * scale)), max(1, int(h * scale)))
                cache = (state["sequence"], size)
                if self.cache.get(index) != cache:
                    self.photos[index] = ImageTk.PhotoImage(
                        Image.fromarray(image).resize(size, Image.Resampling.BILINEAR)
                    )
                    self.cache[index] = cache
                self.canvas.create_image(
                    x + panel_w / 2, 65 + available_h / 2, image=self.photos[index]
                )
                if stale:
                    self.canvas.create_text(
                        x + panel_w / 2,
                        65 + available_h / 2,
                        text="STALE FRAME",
                        fill="#ffbf69",
                        font=("DejaVu Sans", 24, "bold"),
                    )
            age = "--" if state["age"] is None else f"{state['age'] * 1000:.0f} ms"
            self.canvas.create_text(
                x + 14,
                height - 32,
                anchor="w",
                fill="#a9b6ca",
                text=f"RGB age: {age}   |   Frames: {state['sequence']}",
            )
            self.canvas.create_text(
                x + 14,
                height - 13,
                anchor="w",
                fill="#a9b6ca",
                text=f"Clock: {state['domain'] or 'waiting'} | age is not capture latency",
            )
        self.root.after(33, self.update)

    def save(self):
        if not self.last_states:
            return
        folder = (
            ROOT / "output" / "snapshots" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        )
        folder.mkdir(parents=True)
        metadata = {"exposure_synchronized": False, "frames": []}
        for index, state in enumerate(self.last_states):
            if state["image"] is not None:
                Image.fromarray(state["image"]).save(
                    folder / ("luckfox.png" if index == 0 else "d435i.png")
                )
            metadata["frames"].append({k: v for k, v in state.items() if k != "image"})
        (folder / "timestamps.json").write_text(json.dumps(metadata, indent=2))
        self.footer.configure(text=f"Saved original-resolution images: {folder}")


def main():
    parser = argparse.ArgumentParser()
    comparison_args(parser)
    parser.add_argument(
        "--headless-seconds",
        type=float,
        default=0,
        help="Exercise the same readers without a window",
    )
    try:
        args = resolve_comparison(parser.parse_args())
    except ValueError as exc:
        parser.error(str(exc))
    capture = Capture(args)
    root = None
    if not args.headless_seconds:
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            parser.error(
                "Run in a Linux desktop terminal to display the comparison window."
            )
        root = tk.Tk()
        Viewer(root, capture)
        signal.signal(signal.SIGTERM, lambda *_: root.destroy())
    capture.start()
    try:
        if root is not None:
            root.mainloop()
        else:
            time.sleep(args.headless_seconds)
            results = [
                {k: v for k, v in c.snapshot().items() if k != "image"}
                for c in capture.cameras
            ]
            print(json.dumps(results, indent=2), flush=True)
            if any(
                r["sequence"] < 30 or r["age"] is None or r["age"] > 1 for r in results
            ):
                raise RuntimeError("Both live camera readers must deliver frames")
    finally:
        capture.close()


if __name__ == "__main__":
    main()
