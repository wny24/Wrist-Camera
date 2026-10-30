# 实验室相机快速使用

首次使用先运行 `bash scripts/setup.sh`，然后填写 `config.local.json` 中的设备序列号。Luckfox 用 `adb devices -l` 查询，RealSense 用 Viewer 或 `rs-enumerate-devices` 查询。设备按序列号识别，换 USB 线和插口无需改配置，换板子则需要更新序列号。

## 实时对比

连接 Luckfox 和 RealSense，在 Linux 桌面终端进入仓库并运行：

```bash
bash scripts/view.sh
```

左右分别显示 Luckfox 和 RealSense 彩色画面，目标均为 1080p30。

- `0`：左右并排；`1` / `2`：单独放大。
- `F`：全屏；`S`：保存原分辨率图片及时间戳到 `output/snapshots/`。
- `Q` / `Esc`：退出并释放设备。

先暂停其他程序对 RealSense 的取流，避免争用。窗口显示真实 RGB 数组取图 FPS，不是屏幕刷新率。`RGB age` 不是曝光到显示的总延迟。两路按各自最新帧显示，不保证同时曝光。断线后会重试，旧画面会明确标记为 STALE。

## 单独查看 Luckfox 和温度

```bash
bash scripts/play.sh
```

这个入口使用原 CameraPlayer 的 FFplay 窗口，支持多台 Luckfox，每台都会通过 ADB 读取 SoC 温度，无需 SSH 密码。请为多台相机配置不同的本地端口。

当前已验证的 30 fps 设置使用 `/live/1`，分辨率为 1920×1080；原始主码流 `/live/0` 可能仍是 25 fps。新开发板需要先按 [30 fps 配置说明](luckfox-30fps.md) 检查和配置。

## 测帧率

先关闭对比窗口，再运行：

```bash
bash scripts/benchmark.sh --duration 60 --warmup 5
```

结果保存到新的 `output/benchmark-*` 目录，包括汇总 JSON 和逐帧 CSV。代码使用 Python API，实际生成 RGB NumPy 数组，不做补帧。取图增加算法处理后应重新测量。

## 无法连接时

先检查设备序列号、USB 数据线、供电及其他程序占用。启动等待默认 45 秒；物理连接恢复后，监控程序会重建 ADB 转发。若内核出现描述符读取错误或过流提示，应检查线缆和供电，不能只依靠软件重试。

本地配置、运行日志、图片、完整开发板 INI 备份及虚拟环境都不提交到 Git。完整 INI 可能包含账号设置，请保留在本地 `output/` 下。
