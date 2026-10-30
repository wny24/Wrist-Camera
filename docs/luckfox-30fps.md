# Tested Luckfox 1080p30 configuration

This profile was tested on a Luckfox Pico RV1103 board with an SC3336 sensor and its installed RKIPC firmware. It is not a universal profile for every Luckfox firmware release.

The original configuration requested 25 fps in both the ISP and main encoder. Merely changing those fields to 30 made the stream advertise 30 fps but produced about 15 frames/s: the main ISP path reported one capture buffer and alternating frame losses. Reducing main-stream resolution did not resolve that behavior.

The working configuration uses the secondary path with **two input buffers**, 1920×1080, H.265 and 30 fps. The main encoder and JPEG path are disabled. Its RTSP URL ends in `/live/1`. A 20-second test observed 600 packets with approximately 33.3 ms PTS spacing; subsequent Python RGB-array tests measured approximately 30 fps.

## Generate a candidate configuration

Keep the board's original INI file. It includes settings beyond video and can include credentials, so do not commit it.

```bash
mkdir -p output/board-config
adb -s YOUR_ADB_SERIAL pull /userdata/rkipc.ini output/board-config/original.ini
.venv/bin/python tools/make_1080p30_config.py \
    output/board-config/original.ini output/board-config/1080p30.ini
```

The generator applies only the values in `configs/luckfox_1080p30.json`, preserving unrelated configuration. It does not write to a device and refuses to overwrite an existing output file. Review the generated settings for the installed firmware before deployment.

To deploy to the tested RKIPC layout, first stop playback and back up the active configuration on the board:

```bash
adb -s YOUR_ADB_SERIAL shell 'cp -p /userdata/rkipc.ini /userdata/rkipc.ini.before-1080p30'
adb -s YOUR_ADB_SERIAL shell 'killall rkipc'
adb -s YOUR_ADB_SERIAL shell 'pidof rkipc'
```

Wait until `pidof rkipc` returns no process; shutdown can take several seconds. Do not start a second RKIPC process while the first is still stopping. Then deploy and restart the application:

```bash
adb -s YOUR_ADB_SERIAL push output/board-config/1080p30.ini /userdata/rkipc.ini.new
adb -s YOUR_ADB_SERIAL shell 'mv /userdata/rkipc.ini.new /userdata/rkipc.ini; sync'
adb -s YOUR_ADB_SERIAL shell 'nohup /oem/usr/bin/rkipc -a /oem/usr/share/iqfiles >/tmp/rkipc.log 2>&1 </dev/null & sleep 2'
```

Use `stream: 1` in `config.local.json`, then validate actual frames with the Python benchmark. A `30/1` header alone does not prove 30 frames/s. To roll back, stop RKIPC, restore the saved INI and restart using the same method. If USB disconnects, restore communication before attempting further configuration changes.

The final profile is saved under `/userdata` and is loaded by the tested firmware's normal startup. Changing frame rate can affect motion blur, exposure and bandwidth. Preserving 2304×1296 at true 30 fps on the original main path was not achieved in these tests.
