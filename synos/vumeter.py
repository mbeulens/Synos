"""Animated VU meter widget — visualizer style with bouncing bars."""

import math
import random

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib, Gdk


NUM_BARS = 32
BAR_GAP = 2
UPDATE_MS = 50


class VuMeter(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.set_content_height(80)
        self.set_hexpand(True)

        self._playing = False
        self._tick_id = None

        # Each bar has a current level and a target level (0.0–1.0)
        self._levels = [0.0] * NUM_BARS
        self._targets = [0.0] * NUM_BARS
        self._peaks = [0.0] * NUM_BARS

        self.set_draw_func(self._draw)

    def set_playing(self, playing):
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
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
        # Animate bars down to zero
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
        return still_active

    def _tick(self):
        if not self._playing:
            return False

        # Generate new random targets with some coherence
        t = GLib.get_monotonic_time() / 1_000_000.0
        for i in range(NUM_BARS):
            # Mix of sine waves + noise for organic movement
            base = 0.3 + 0.2 * math.sin(t * 2.5 + i * 0.4)
            wave = 0.25 * math.sin(t * 4.0 + i * 0.7)
            noise = random.uniform(-0.15, 0.15)
            self._targets[i] = max(0.05, min(1.0, base + wave + noise))

        # Smooth toward targets
        for i in range(NUM_BARS):
            diff = self._targets[i] - self._levels[i]
            if diff > 0:
                self._levels[i] += diff * 0.4  # fast rise
            else:
                self._levels[i] += diff * 0.15  # slow fall

            # Peak hold
            if self._levels[i] > self._peaks[i]:
                self._peaks[i] = self._levels[i]
            else:
                self._peaks[i] *= 0.97  # slow peak decay

        self.queue_draw()
        return True

    def _draw(self, area, cr, width, height):
        if width <= 0 or height <= 0:
            return

        bar_width = max(1, (width - (NUM_BARS - 1) * BAR_GAP) / NUM_BARS)

        for i in range(NUM_BARS):
            x = i * (bar_width + BAR_GAP)
            level = self._levels[i]
            bar_height = max(1, level * height)

            # Gradient: green at bottom, yellow in middle, red at top
            segments = int(bar_height / 3) + 1
            seg_height = bar_height / max(segments, 1)

            for s in range(segments):
                frac = (s * seg_height) / height
                if frac < 0.5:
                    r, g, b = 0.2, 0.8, 0.4  # green
                elif frac < 0.75:
                    r, g, b = 0.9, 0.8, 0.2  # yellow
                else:
                    r, g, b = 0.9, 0.2, 0.2  # red

                sy = height - (s + 1) * seg_height
                cr.set_source_rgba(r, g, b, 0.85)
                cr.rectangle(x, sy, bar_width, seg_height - 1)
                cr.fill()

            # Peak indicator
            peak = self._peaks[i]
            if peak > 0.02:
                py = height - peak * height
                frac = peak
                if frac < 0.5:
                    r, g, b = 0.3, 1.0, 0.5
                elif frac < 0.75:
                    r, g, b = 1.0, 0.9, 0.3
                else:
                    r, g, b = 1.0, 0.3, 0.3
                cr.set_source_rgba(r, g, b, 1.0)
                cr.rectangle(x, py, bar_width, 2)
                cr.fill()
