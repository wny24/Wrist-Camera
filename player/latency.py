"""Detect growth of media age, not absolute capture-to-display latency."""
import math


class DelayGrowth:
    def __init__(self, threshold=0.8, sustain=2):
        self.threshold, self.sustain = threshold, sustain
        self.minimum_offset = self.previous_pts = self.previous_now = None
        self.exceeded_since = None
        self.growth = 0
        self.resets = 0

    def update(self, pts, now):
        if not math.isfinite(pts):
            return
        offset = now - pts
        # Reset the estimate after a discontinuity instead of treating it as
        # congestion. The first frame of a new connection is only a baseline.
        if self.previous_pts is not None:
            media_delta, wall_delta = pts - self.previous_pts, now - self.previous_now
            if media_delta < -0.1 or abs(media_delta - wall_delta) > 10:
                self.minimum_offset = None
                self.exceeded_since = None
                self.resets += 1
        self.previous_pts, self.previous_now = pts, now
        self.minimum_offset = offset if self.minimum_offset is None else min(self.minimum_offset, offset)
        self.growth = max(0, offset - self.minimum_offset)
        if self.growth > self.threshold:
            if self.exceeded_since is None:
                self.exceeded_since = now
        else:
            self.exceeded_since = None

    def snapshot(self, now):
        return {"delay_growth_ms": None if self.minimum_offset is None else round(self.growth * 1000),
                "pts_resets": self.resets,
                "backlog_detected": bool(self.exceeded_since is not None and
                                         now - self.exceeded_since >= self.sustain)}
