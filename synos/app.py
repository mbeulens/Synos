"""Synos GTK4 + Libadwaita application."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio

from synos.window import SynosWindow


class SynosApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.github.synos",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = SynosWindow(application=self)
        win.present()


def main():
    import sys
    app = SynosApp()
    app.run(sys.argv)
