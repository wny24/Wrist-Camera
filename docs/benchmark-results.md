# Observed Python RGB-array performance

Measured on 2026-10-30 on one Linux host. Both cameras ran concurrently, with 5 seconds of warmup and approximately 60 seconds of measurement per reader. Both generated 1920×1080 RGB NumPy arrays, with a nominal target of 30 fps. Depth was disabled. RealSense auto-exposure priority was 0; auto exposure remained enabled. No application processing beyond capture, RGB conversion and timing was included.

| Metric | Luckfox SC3336 | RealSense D435i RGB |
| --- | ---: | ---: |
| Frames received | 1800 | 1795 |
| NumPy-ready FPS | 29.9990 | 29.8948 |
| Median source interval | 33.333 ms | 33.358 ms |
| Receive interval P99 | 39.338 ms | 33.971 ms |
| Maximum receive interval | 75.230 ms | 132.743 ms |
| Source intervals above 50 ms | 0 | 3 |
| Frame counter gaps | Not available | 5 frames |
| RGB conversion/copy P99 | 0.610 ms | 0.816 ms |

Luckfox had a continuous output PTS timeline in this run, but did not expose a sensor frame counter, so this is not proof that no frames were lost anywhere in the sensor pipeline. The five D435i frame-number gaps do not identify whether loss occurred in transport, SDK queues or another part of capture. Host scheduling and other workloads can affect these results.

A separate decode-only Python run measured approximately 30.00 fps on Luckfox and 29.94 fps on D435i, with two D435i frame-number gaps. These short samples show run-to-run variation; neither result is a guarantee of sustained throughput or exposure synchronization. The live viewer later observed approximately 30.00 and 29.98 fps in a short window.

Reproduce with `bash scripts/benchmark.sh`. New results go to ignored, timestamped `output/` directories; original device identifiers, wall-clock metadata and raw lab frame logs are not included in this repository.
