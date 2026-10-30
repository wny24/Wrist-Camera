# Frame timestamps and alignment

The benchmark records four columns per camera:

| Column | Meaning |
| --- | --- |
| `source_seconds` | RealSense API frame timestamp, or Luckfox RTSP presentation timestamp |
| `host_monotonic_seconds` | Time when the Python reader receives the frame, before RGB-array conversion |
| `frame_number` | RealSense frame counter; for Luckfox, the benchmark sample index only |
| `numpy_ready_monotonic_seconds` | Time after conversion/copy to a usable RGB NumPy array |

On the tested D435i, `get_timestamp()` used the `global_time` domain with global time enabled. The camera also supplied sensor/frame metadata. The SDK defines global time as camera time mapped to the OS clock, and sensor timestamp as the middle of exposure calculated by the device. See the [official timestamp definitions](https://github.com/realsenseai/librealsense/blob/master/include/librealsense2/h/rs_frame.h) and [metadata API](https://dev.realsenseai.com/docs/frame-metadata/).

Luckfox's decoded PTS belongs to the RTSP stream timeline. This project has not verified a mapping from that PTS to exposure time on the host clock. During inspection, the board's wall clock was near its 1970 boot epoch. Setting the wall clock alone would not establish exposure synchronization.

Do not subtract the two `source_seconds` columns directly, or assume the first frames were exposed simultaneously. `pair_by_host_time.py` pairs by a common host monotonic clock without reusing frames. The default 20 ms tolerance is a matching rule, **not a bound on exposure error**. Encoding, transport, buffering and decoding introduce different delays in the two paths.

For exposure-level alignment, use a shared visible timing event (such as an LED sequence) to measure offsets and drift, validate residual error over time, and account for variable latency. Matching source FPS does not establish a common frame phase. The tested D435i RGB sensor did not expose `inter_cam_sync_mode`; do not apply depth-sensor hardware-sync instructions to RGB without checking actual support.

The live viewer intentionally shows each camera's latest frame independently. Its on-screen RGB age and saved snapshot timestamps must not be presented as capture latency or synchronized exposure measurements.
