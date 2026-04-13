"""Animated VU meter widget — visualizer style with bouncing bars."""

import math
import random

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib


NUM_BARS = 32
BAR_GAP = 2
UPDATE_MS = 50


class VuMeter(Gtk.Widget):
    """Custom widget that draws an animated bar visualizer."""

    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)

        self._playing = False
        self._tick_id = None
        self._fade_id = None

        self._levels = [0.0] * NUM_BARS
        self._targets = [0.0] * NUM_BARS
        self._peaks = [0.0] * NUM_BARS

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

        t = GLib.get_monotonic_time() / 1_000_000.0
        for i in range(NUM_BARS):
            base = 0.3 + 0.2 * math.sin(t * 2.5 + i * 0.4)
            wave = 0.25 * math.sin(t * 4.0 + i * 0.7)
            noise = random.uniform(-0.15, 0.15)
            self._targets[i] = max(0.05, min(1.0, base + wave + noise))

        for i in range(NUM_BARS):
            diff = self._targets[i] - self._levels[i]
            if diff > 0:
                self._levels[i] += diff * 0.4
            else:
                self._levels[i] += diff * 0.15

            if self._levels[i] > self._peaks[i]:
                self._peaks[i] = self._levels[i]
            else:
                self._peaks[i] *= 0.97

        self.queue_draw()
        return True

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.VERTICAL:
            return 80, 120, -1, -1
        else:
            return 100, 300, -1, -1

    def do_snapshot(self, snapshot):
        width = self.get_width()
        height = self.get_height()
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

                from graphene import Rect
                from gi.repository import Gdk, Gsk

                sy = height - (s + 1) * seg_height
                rect = Rect.alloc()
                rect.init(x, sy, bar_width, max(1, seg_height - 1))
                color = Gdk.RGBA()
                color.red, color.green, color.blue, color.alpha = r, g, b, 0.85
                snapshot.append_color(color, rect)

            # Peak indicator
            peak = self._peaks[i]
            if peak > 0.02:
                from graphene import Rect as Rect2
                py = height - peak * height
                if peak < 0.5:
                    r, g, b = 0.3, 1.0, 0.5
                elif peak < 0.75:
                    r, g, b = 1.0, 0.9, 0.3
                else:
                    r, g, b = 1.0, 0.3, 0.3
                rect = Rect2.alloc()
                rect.init(x, py, bar_width, 2)
                color = Gdk.RGBA()
                color.red, color.green, color.blue, color.alpha = r, g, b, 1.0
                snapshot.append_color(color, rect)
