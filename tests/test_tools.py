import json
import subprocess
from unittest.mock import patch

import pytest

from compare_fps import summarize
from make_1080p30_config import patch_ini
from pair_by_host_time import pair
from settings import ensure_forward, load_settings


def test_config_rejects_duplicate_ports(tmp_path):
    config = tmp_path / "local.json"
    config.write_text(
        json.dumps(
            {
                "luckfox": [
                    {"serial": "a", "port": 18554, "stream": 0},
                    {"serial": "b", "port": 18554, "stream": 1},
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="unique port"):
        load_settings(config)


def test_missing_config_explains_setup(tmp_path):
    with pytest.raises(ValueError, match="copy config.example.json"):
        load_settings(tmp_path / "missing.json")


def test_forward_recreated_after_usb_disconnect():
    def mock_run(args, **kwargs):
        if args[-1] == "get-state":
            return subprocess.CompletedProcess(args, 0, stdout="device\n")
        return subprocess.CompletedProcess(args, 0, stdout="")

    with patch("settings.subprocess.run", side_effect=mock_run) as run:
        ensure_forward("board-a", 18554)
        ensure_forward("board-a", 18554)
    creates = [c.args[0] for c in run.call_args_list if "--no-rebind" in c.args[0]]
    assert len(creates) == 2


def test_forward_never_overwrites_other_board():
    replies = [
        subprocess.CompletedProcess([], 0, stdout="device\n"),
        subprocess.CompletedProcess([], 0, stdout="board-b tcp:18554 tcp:554\n"),
    ]
    with patch("settings.subprocess.run", side_effect=replies) as run:
        with pytest.raises(ValueError, match="another ADB forward"):
            ensure_forward("board-a", 18554)
    assert run.call_count == 2


def test_patch_preserves_unrelated_settings_and_adds_missing_keys():
    original = "; keep comment\n[video.1]\nwidth = 704 ; old\n[other]\ncustom = keep\n"
    changes = {"video.1": {"width": "1920", "height": "1080"}, "new": {"fps": "30"}}
    result = patch_ini(original, changes)
    assert "; keep comment" in result and "custom = keep" in result
    assert "width = 1920\n" in result and "height = 1080\n" in result
    assert "[new]\nfps = 30\n" in result
    assert patch_ini(result, changes) == result


def test_pair_threshold_and_no_frame_reuse():
    def row(t, number):
        return {"host_monotonic_seconds": t, "frame_number": number}

    left = [row(0, 0), row(0.001, 1), row(1, 2)]
    right = [row(0.002, 10), row(1.1, 11)]
    result = list(pair(left, right, 0.02))
    assert len(result) == 1 and result[0][:2] == (0, 10)


def test_measure_real_dropped_frame_instead_of_advertised_fps():
    times = [0, 1 / 30, 3 / 30, 4 / 30]
    rows = [(t, t + 10, i, t + 10.001) for i, t in enumerate(times)]
    result = summarize(rows, {"advertised_fps": "30/1"})
    assert result["source_fps"] == pytest.approx(22.5)
    assert result["source_gaps_over_50ms"] == 1


def test_measure_requires_frames():
    with pytest.raises(ValueError, match="Not enough"):
        summarize([], {})
