"""Animated VU meter widget — visualizer style with bouncing bars."""

import math
import random

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

NUM_BARS = 32
BAR_GAP = 2
UPDATE_MS = 50


class VuMeter(Gtk.DrawingArea):
    """Bar visualizer using DrawingArea with cairo."""

    def __init__(self):
        super().__init__()
        self.set_content_width(200)
        self.set_content_height(100)
        self.set_hexpand(True)

        self._playing = False
        self._tick_id = None
        self._fade_id = None

        self._levels = [0.0] * NUM_BARS
        self._targets = [0.0] * NUM_BARS
        self._peaks = [0.0] * NUM_BARS

        self.set_draw_func(self._on_draw)

    def set_playing(self, playing):
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            if self._fade_id is not None:
                GLib.source_remove(self._fade_id)
                self._fade_id = None
            self._start_animation()
        else:
            self._stop_animation()

    def _start_animation(self):
        if self._tick_id is not None:
            return
        self._tick_id = GLib.timeout_add(UPDATE_MS, self._tick)

    def _stop_animation(self):
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        self._targets = [0.0] * NUM_BARS
        self._fade_id = GLib.timeout_add(UPDATE_MS, self._fade_out)

    def _fade_out(self):
        still_active = False
        for i in range(NUM_BARS):
            self._levels[i] *= 0.85
            self._peaks[i] *= 0.92
            if self._levels[i] > 0.01:
                still_active = True
            else:
                self._levels[i] = 0.0
                self._peaks[i] = 0.0
        self.queue_draw()
        if not still_active:
            self._fade_id = None
        return still_active

    def _tick(self):
        if not self._playing:
            return False

        for i in range(NUM_BARS):
            # Each bar gets a fully random target — no spatial correlation
            if random.random() < 0.3:
                # 30% chance to jump to a new random level
                self._targets[i] = random.uniform(0.05, 1.0)
            # Occasional spikes
            if random.random() < 0.05:
                self._targets[i] = random.uniform(0.7, 1.0)

        for i in range(NUM_BARS):
            diff = self._targets[i] - self._levels[i]
            if diff > 0:
                self._levels[i] += diff * 0.5  # fast rise
            else:
                self._levels[i] += diff * 0.25  # faster fall

            if self._levels[i] > self._peaks[i]:
                self._peaks[i] = self._levels[i]
            else:
                self._peaks[i] *= 0.97

        self.queue_draw()
        return True

    def _on_draw(self, area, cr, width, height):
        if width <= 0 or height <= 0:
            return

        bar_width = max(1, (width - (NUM_BARS - 1) * BAR_GAP) / NUM_BARS)

        for i in range(NUM_BARS):
            x = i * (bar_width + BAR_GAP)
            level = self._levels[i]
            bar_height = max(0, level * height)

            if bar_height < 1:
                continue

            segments = max(1, int(bar_height / 3))
            seg_height = bar_height / segments

            for s in range(segments):
                frac = (s * seg_height) / height
                if frac < 0.5:
                    r, g, b = 0.2, 0.8, 0.4
                elif frac < 0.75:
                    r, g, b = 0.9, 0.8, 0.2
                else:
                    r, g, b = 0.9, 0.2, 0.2

                sy = height - (s + 1) * seg_height
                cr.set_source_rgba(r, g, b, 0.85)
                cr.rectangle(x, sy, bar_width, max(1, seg_height - 1))
                cr.fill()

            # Peak indicator
            peak = self._peaks[i]
            if peak > 0.02:
                py = height - peak * height
                if peak < 0.5:
                    r, g, b = 0.3, 1.0, 0.5
                elif peak < 0.75:
                    r, g, b = 1.0, 0.9, 0.3
                else:
                    r, g, b = 1.0, 0.3, 0.3
                cr.set_source_rgba(r, g, b, 1.0)
                cr.rectangle(x, py, bar_width, 2)
                cr.fill()
