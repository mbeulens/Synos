"""Main application window — three-panel layout."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import json
import os

from gi.repository import Adw, Gtk, GLib, Gdk, Pango

from synos import __version__
from synos.sonos_client import discover_speakers, play_stream, get_transport_state
from synos.streams import load_streams, add_stream, remove_stream, CONFIG_DIR
from synos.vumeter import VuMeter
from synos.playqueue import PlayQueue
from synos.httpserver import AudioServer
from synos.library import (
    load_library_folders, add_library_folder, remove_library_folder, scan_folder,
)


CSS = """
.side-panel {
    background-color: alpha(@window_fg_color, 0.04);
}
.center-panel {
    background-color: alpha(@window_fg_color, 0.02);
}
.panel-title {
    font-size: 11px;
    font-weight: bold;
    opacity: 0.55;
    letter-spacing: 1px;
}
.now-playing-title {
    font-size: 13px;
    font-weight: bold;
}
.now-playing-detail {
    font-size: 11px;
    opacity: 0.55;
}
.disc-art {
    background-color: alpha(@window_fg_color, 0.08);
    border-radius: 999px;
    min-width: 140px;
    min-height: 140px;
}
"""


class SynosWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(f"Synos v{__version__}")
        self.set_default_size(900, 600)

        self._speakers = []
        self._active_speaker = None
        self._poll_source_id = None
        self._last_transport_state = None
        self._queue = PlayQueue()
        self._audio_server = AudioServer()

        self._load_css()
        self._build_ui()
        self._start_discovery()
        self._start_audio_server()

    # ── CSS ──────────────────────────────────────────────────────────

    def _load_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        self._style_manager = self.get_application().get_style_manager()
        self._load_theme_preference()

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        # Headerbar with transport controls in center
        header = Adw.HeaderBar()

        self._refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self._refresh_btn.set_tooltip_text("Refresh speakers")
        self._refresh_btn.connect("clicked", self._on_refresh_clicked)
        header.pack_start(self._refresh_btn)

        # Transport controls in headerbar center
        transport_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._prev_btn = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self._prev_btn.add_css_class("flat")
        self._prev_btn.set_sensitive(False)
        self._prev_btn.connect("clicked", self._on_prev_clicked)

        self._play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        self._play_btn.add_css_class("flat")
        self._play_btn.set_sensitive(False)
        self._play_btn.connect("clicked", self._on_play_clicked)

        self._pause_btn = Gtk.Button(icon_name="media-playback-pause-symbolic")
        self._pause_btn.add_css_class("flat")
        self._pause_btn.set_sensitive(False)
        self._pause_btn.connect("clicked", self._on_pause_clicked)

        self._next_btn = Gtk.Button(icon_name="media-skip-forward-symbolic")
        self._next_btn.add_css_class("flat")
        self._next_btn.set_sensitive(False)
        self._next_btn.connect("clicked", self._on_next_clicked)

        transport_box.append(self._prev_btn)
        transport_box.append(self._play_btn)
        transport_box.append(self._pause_btn)
        transport_box.append(self._next_btn)
        header.pack_start(transport_box)

        # Volume in headerbar right side
        vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._mute_btn = Gtk.Button(icon_name="audio-volume-high-symbolic")
        self._mute_btn.add_css_class("flat")
        self._mute_btn.set_tooltip_text("Mute")
        self._mute_btn.connect("clicked", self._on_mute_clicked)
        vol_box.append(self._mute_btn)

        self._volume_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1
        )
        self._volume_scale.set_size_request(120, -1)
        self._volume_scale.set_value(20)
        self._volume_scale.set_sensitive(False)
        self._volume_scale.set_draw_value(False)
        self._volume_scale.connect("value-changed", self._on_volume_changed)
        vol_box.append(self._volume_scale)

        self._volume_label = Gtk.Label(label="20")
        self._volume_label.set_width_chars(3)
        vol_box.append(self._volume_label)

        header.pack_end(vol_box)

        # Theme toggle
        self._theme_btn = Gtk.Button()
        self._theme_btn.add_css_class("flat")
        self._theme_btn.connect("clicked", self._on_theme_toggled)
        self._update_theme_icon()
        header.pack_end(self._theme_btn)

        toolbar_view.add_top_bar(header)

        # ── Three-panel layout ───────────────────────────────────────
        paned_outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned_outer.set_shrink_start_child(False)
        paned_outer.set_shrink_end_child(False)

        # Left panel: Rooms
        left_panel = self._build_rooms_panel()
        paned_outer.set_start_child(left_panel)

        # Right area: Center (Now Playing) + Right (Music Source)
        paned_inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned_inner.set_shrink_start_child(False)
        paned_inner.set_shrink_end_child(False)

        center_panel = self._build_now_playing_panel()
        paned_inner.set_start_child(center_panel)

        right_panel = self._build_source_panel()
        paned_inner.set_end_child(right_panel)

        paned_outer.set_end_child(paned_inner)

        # Set initial pane positions
        paned_outer.set_position(180)
        paned_inner.set_position(420)

        toolbar_view.set_content(paned_outer)

    # ── Left panel: Rooms ────────────────────────────────────────────

    def _build_rooms_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("side-panel")
        box.set_size_request(160, -1)

        # Title
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        title_box.set_margin_top(12)
        title_box.set_margin_start(12)
        title_box.set_margin_end(12)
        title_box.set_margin_bottom(8)

        title = Gtk.Label(label="ROOMS")
        title.add_css_class("panel-title")
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)
        title_box.append(title)

        group_btn = Gtk.Button(label="Group")
        group_btn.add_css_class("flat")
        group_btn.set_sensitive(False)
        title_box.append(group_btn)

        box.append(title_box)

        # Speaker list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._speaker_list = Gtk.ListBox()
        self._speaker_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._speaker_list.add_css_class("navigation-sidebar")
        self._speaker_list.connect("row-selected", self._on_speaker_selected)
        scroll.set_child(self._speaker_list)

        # Spinner during discovery
        self._spinner_row = Gtk.ListBoxRow()
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spinner_box.set_margin_start(12)
        spinner_box.set_margin_top(8)
        spinner_box.set_margin_bottom(8)
        spinner = Gtk.Spinner(spinning=True)
        spinner_box.append(spinner)
        spinner_box.append(Gtk.Label(label="Searching..."))
        self._spinner_row.set_child(spinner_box)
        self._speaker_list.append(self._spinner_row)

        box.append(scroll)

        # Playing indicator at bottom
        self._room_now_playing = Gtk.Label(label="")
        self._room_now_playing.set_halign(Gtk.Align.START)
        self._room_now_playing.set_margin_start(12)
        self._room_now_playing.set_margin_bottom(12)
        self._room_now_playing.set_margin_top(8)
        self._room_now_playing.set_ellipsize(Pango.EllipsizeMode.END)
        self._room_now_playing.add_css_class("now-playing-detail")
        box.append(self._room_now_playing)

        return box

    # ── Center panel: Now Playing ────────────────────────────────────

    def _build_now_playing_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("center-panel")
        box.set_size_request(300, -1)

        # Title
        title = Gtk.Label(label="NOW PLAYING")
        title.add_css_class("panel-title")
        title.set_halign(Gtk.Align.START)
        title.set_margin_top(12)
        title.set_margin_start(16)
        title.set_margin_bottom(2)
        box.append(title)

        # Stream/channel name
        self._np_stream_name = Gtk.Label(label="")
        self._np_stream_name.set_halign(Gtk.Align.START)
        self._np_stream_name.set_margin_start(16)
        self._np_stream_name.set_margin_bottom(12)
        self._np_stream_name.add_css_class("now-playing-detail")
        self._np_stream_name.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self._np_stream_name)

        # Content area
        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_valign(Gtk.Align.START)

        # Disc art placeholder
        disc_frame = Gtk.Frame()
        disc_frame.add_css_class("disc-art")
        disc_icon = Gtk.Image(icon_name="media-optical-symbolic")
        disc_icon.set_pixel_size(64)
        disc_icon.set_opacity(0.3)
        disc_frame.set_child(disc_icon)
        content.append(disc_frame)

        # Track info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        info_box.set_valign(Gtk.Align.CENTER)
        info_box.set_hexpand(True)

        self._np_title = Gtk.Label(label="Nothing playing")
        self._np_title.add_css_class("now-playing-title")
        self._np_title.set_halign(Gtk.Align.START)
        self._np_title.set_ellipsize(Pango.EllipsizeMode.END)
        self._np_title.set_max_width_chars(30)
        info_box.append(self._np_title)

        self._np_artist = Gtk.Label(label="")
        self._np_artist.add_css_class("now-playing-detail")
        self._np_artist.set_halign(Gtk.Align.START)
        self._np_artist.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(self._np_artist)

        self._np_album = Gtk.Label(label="")
        self._np_album.add_css_class("now-playing-detail")
        self._np_album.set_halign(Gtk.Align.START)
        self._np_album.set_ellipsize(Pango.EllipsizeMode.END)
        info_box.append(self._np_album)

        content.append(info_box)
        box.append(content)

        # Seek slider
        seek_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        seek_box.set_margin_start(16)
        seek_box.set_margin_end(16)
        seek_box.set_margin_top(12)

        self._seek_position_label = Gtk.Label(label="0:00")
        self._seek_position_label.add_css_class("now-playing-detail")
        self._seek_position_label.set_width_chars(5)
        seek_box.append(self._seek_position_label)

        self._seek_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 1, 1
        )
        self._seek_scale.set_hexpand(True)
        self._seek_scale.set_draw_value(False)
        self._seek_scale.set_sensitive(False)
        self._seeking = False

        # Track drag start/end to suppress polling during seek
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_seek_pressed)
        click.connect("released", self._on_seek_released)
        self._seek_scale.add_controller(click)

        seek_box.append(self._seek_scale)

        self._seek_duration_label = Gtk.Label(label="0:00")
        self._seek_duration_label.add_css_class("now-playing-detail")
        self._seek_duration_label.set_width_chars(5)
        seek_box.append(self._seek_duration_label)

        box.append(seek_box)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        box.append(spacer)

        # VU Meter — fixed height, pinned to bottom
        self._vu_meter = VuMeter()
        self._vu_meter.set_margin_start(16)
        self._vu_meter.set_margin_end(16)
        self._vu_meter.set_margin_bottom(12)
        box.append(self._vu_meter)

        return box

    # ── Right panel: Music Browser ───────────────────────────────────

    def _build_source_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.add_css_class("side-panel")
        box.set_size_request(200, -1)

        # Title row with back and action buttons
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        title_box.set_margin_top(12)
        title_box.set_margin_start(12)
        title_box.set_margin_end(12)
        title_box.set_margin_bottom(8)

        self._browser_back_btn = Gtk.Button(icon_name="go-previous-symbolic")
        self._browser_back_btn.add_css_class("flat")
        self._browser_back_btn.set_tooltip_text("Back")
        self._browser_back_btn.set_visible(False)
        self._browser_back_btn.connect("clicked", self._on_browser_back)
        title_box.append(self._browser_back_btn)

        self._browser_title = Gtk.Label(label="MUSIC")
        self._browser_title.add_css_class("panel-title")
        self._browser_title.set_halign(Gtk.Align.START)
        self._browser_title.set_hexpand(True)
        title_box.append(self._browser_title)

        self._browser_add_btn = Gtk.Button(icon_name="list-add-symbolic")
        self._browser_add_btn.add_css_class("flat")
        self._browser_add_btn.set_tooltip_text("Add")
        self._browser_add_btn.set_visible(False)
        self._browser_add_btn.connect("clicked", self._on_add_stream_clicked)
        title_box.append(self._browser_add_btn)

        box.append(title_box)

        # Browsable list
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._browser_list = Gtk.ListBox()
        self._browser_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._browser_list.add_css_class("navigation-sidebar")
        scroll.set_child(self._browser_list)

        box.append(scroll)

        self._browser_view = "root"
        self._show_browser_root()
        return box

    def _clear_browser_list(self):
        while True:
            row = self._browser_list.get_row_at_index(0)
            if row is None:
                break
            self._browser_list.remove(row)

    def _make_browser_row(self, icon_name, label_text, activatable=True):
        row = Gtk.ListBoxRow()
        row.set_activatable(activatable)
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row_box.set_margin_start(12)
        row_box.set_margin_end(12)
        row_box.set_margin_top(6)
        row_box.set_margin_bottom(6)

        icon = Gtk.Image(icon_name=icon_name)
        icon.set_pixel_size(20)
        row_box.append(icon)

        label = Gtk.Label(label=label_text)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        row_box.append(label)

        row.set_child(row_box)
        return row

    # ── Root view ────────────────────────────────────────────────────

    def _show_browser_root(self):
        self._clear_browser_list()
        self._browser_view = "root"
        self._browser_title.set_text("MUSIC")
        self._browser_back_btn.set_visible(False)
        self._browser_add_btn.set_visible(False)

        # Disconnect previous handler if any
        try:
            self._browser_list.disconnect_by_func(self._on_root_activated)
        except TypeError:
            pass
        try:
            self._browser_list.disconnect_by_func(self._on_stream_activated)
        except TypeError:
            pass

        folders = [
            ("network-transmit-symbolic", "Streams"),
            ("folder-music-symbolic", "Music Library"),
            ("multimedia-player-symbolic", "Music Services"),
        ]

        for icon_name, label_text in folders:
            row = self._make_browser_row(icon_name, label_text)
            # Add a right arrow to indicate it's a folder
            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.set_opacity(0.5)
            row.get_child().append(arrow)
            self._browser_list.append(row)

        self._browser_list.connect("row-activated", self._on_root_activated)

    def _on_root_activated(self, _listbox, row):
        idx = row.get_index()
        if idx == 0:
            self._show_streams_view()
        elif idx == 1:
            self._show_library_folders_view()

    # ── Streams view ─────────────────────────────────────────────────

    def _show_streams_view(self):
        self._clear_browser_list()
        self._browser_view = "streams"
        self._browser_title.set_text("STREAMS")
        self._browser_back_btn.set_visible(True)
        self._browser_add_btn.set_visible(True)
        self._browser_add_btn.set_tooltip_text("Add stream")

        # Reconnect add button for streams
        try:
            self._browser_add_btn.disconnect_by_func(self._on_add_folder_clicked)
        except TypeError:
            pass
        try:
            self._browser_add_btn.disconnect_by_func(self._on_add_stream_clicked)
        except TypeError:
            pass
        self._browser_add_btn.connect("clicked", self._on_add_stream_clicked)

        self._disconnect_browser_signals()

        self._streams = load_streams()

        if not self._streams:
            row = self._make_browser_row(
                "list-add-symbolic", "No streams — click + to add", activatable=False
            )
            self._browser_list.append(row)
            return

        for i, stream in enumerate(self._streams):
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(4)
            row_box.set_margin_top(5)
            row_box.set_margin_bottom(5)

            icon = Gtk.Image(icon_name="network-transmit-symbolic")
            icon.set_pixel_size(16)
            row_box.append(icon)

            label = Gtk.Label(label=stream["name"])
            label.set_halign(Gtk.Align.START)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            row_box.append(label)

            remove_btn = Gtk.Button(icon_name="edit-delete-symbolic")
            remove_btn.add_css_class("flat")
            remove_btn.set_tooltip_text("Remove stream")
            remove_btn.connect("clicked", self._on_remove_stream_clicked, i)
            row_box.append(remove_btn)

            row.set_child(row_box)
            self._browser_list.append(row)

        self._browser_list.connect("row-activated", self._on_stream_activated)

    def _on_browser_back(self, _btn):
        if self._browser_view == "library_files":
            if self._current_subfolder_rel:
                # Go up one level in subfolder
                parent_rel = os.path.dirname(self._current_subfolder_rel)
                if parent_rel:
                    self._show_library_files_view(self._current_folder_index, subfolder_rel=parent_rel)
                else:
                    self._show_library_files_view(self._current_folder_index)
            else:
                self._show_library_folders_view()
        else:
            self._show_browser_root()

    def _on_stream_activated(self, _listbox, row):
        if not self._active_speaker:
            return
        idx = row.get_index()
        if idx < len(self._streams):
            stream = self._streams[idx]
            try:
                play_stream(self._active_speaker, stream["url"], title=stream["name"])
            except Exception:
                pass

    def _on_add_stream_clicked(self, _btn):
        dialog = Adw.AlertDialog(
            heading="Add Stream",
            body="Enter a name and URL for the stream.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_start(12)
        content.set_margin_end(12)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Stream name")
        content.append(name_entry)

        url_entry = Gtk.Entry()
        url_entry.set_placeholder_text("Stream URL (http://...)")
        content.append(url_entry)

        dialog.set_extra_child(content)
        dialog.connect("response", self._on_add_stream_response, name_entry, url_entry)
        dialog.present(self)

    def _on_add_stream_response(self, dialog, response, name_entry, url_entry):
        if response != "add":
            return
        name = name_entry.get_text().strip()
        url = url_entry.get_text().strip()
        if name and url:
            add_stream(name, url)
            self._show_streams_view()

    def _on_remove_stream_clicked(self, _btn, index):
        stream = self._streams[index]
        dialog = Adw.AlertDialog(
            heading="Remove Stream",
            body=f'Remove "{stream["name"]}"?',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_remove_stream_response, index)
        dialog.present(self)

    def _on_remove_stream_response(self, dialog, response, index):
        if response == "remove":
            remove_stream(index)
            self._show_streams_view()

    # ── Music Library views ──────────────────────────────────────────

    def _show_library_folders_view(self):
        """Show list of configured library folders."""
        self._clear_browser_list()
        self._browser_view = "library_folders"
        self._browser_title.set_text("MUSIC LIBRARY")
        self._browser_back_btn.set_visible(True)
        self._browser_add_btn.set_visible(True)
        self._browser_add_btn.set_tooltip_text("Add folder")

        # Reconnect add button for folder adding
        try:
            self._browser_add_btn.disconnect_by_func(self._on_add_stream_clicked)
        except TypeError:
            pass
        try:
            self._browser_add_btn.disconnect_by_func(self._on_add_folder_clicked)
        except TypeError:
            pass
        self._browser_add_btn.connect("clicked", self._on_add_folder_clicked)

        self._disconnect_browser_signals()

        self._library_folders = load_library_folders()

        if not self._library_folders:
            row = self._make_browser_row(
                "list-add-symbolic", "No folders — click + to add", activatable=False
            )
            self._browser_list.append(row)
            return

        for i, folder_path in enumerate(self._library_folders):
            folder_name = os.path.basename(folder_path) or folder_path
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(4)
            row_box.set_margin_top(5)
            row_box.set_margin_bottom(5)

            icon = Gtk.Image(icon_name="folder-music-symbolic")
            icon.set_pixel_size(16)
            row_box.append(icon)

            label = Gtk.Label(label=folder_name)
            label.set_halign(Gtk.Align.START)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_tooltip_text(folder_path)
            row_box.append(label)

            remove_btn = Gtk.Button(icon_name="edit-delete-symbolic")
            remove_btn.add_css_class("flat")
            remove_btn.set_tooltip_text("Remove folder")
            remove_btn.connect("clicked", self._on_remove_folder_clicked, i)
            row_box.append(remove_btn)

            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.set_opacity(0.5)
            row_box.append(arrow)

            row.set_child(row_box)
            self._browser_list.append(row)

        self._browser_list.connect("row-activated", self._on_library_folder_activated)

    def _show_library_files_view(self, folder_index, subfolder_rel=""):
        """Show subdirs and audio files in a library folder/subfolder."""
        self._clear_browser_list()
        self._browser_view = "library_files"
        self._current_folder_index = folder_index
        self._current_subfolder_rel = subfolder_rel
        root_path = self._library_folders[folder_index]
        folder_path = os.path.join(root_path, subfolder_rel) if subfolder_rel else root_path
        folder_name = os.path.basename(folder_path) or folder_path
        self._browser_title.set_text(folder_name.upper())
        self._browser_back_btn.set_visible(True)
        self._browser_add_btn.set_visible(False)

        self._disconnect_browser_signals()

        subdirs, files = scan_folder(folder_path)
        self._current_files = files
        self._current_folder_path = folder_path
        self._current_subdirs = subdirs

        # Track how many non-file rows are at the top
        top_rows = 0

        # Play All row (only if there are files)
        if files:
            play_all_row = Gtk.ListBoxRow()
            pa_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            pa_box.set_margin_start(12)
            pa_box.set_margin_end(12)
            pa_box.set_margin_top(6)
            pa_box.set_margin_bottom(6)
            pa_icon = Gtk.Image(icon_name="media-playback-start-symbolic")
            pa_icon.set_pixel_size(16)
            pa_box.append(pa_icon)
            pa_label = Gtk.Label(label=f"Play All ({len(files)} tracks)")
            pa_label.set_halign(Gtk.Align.START)
            pa_label.add_css_class("now-playing-title")
            pa_box.append(pa_label)
            play_all_row.set_child(pa_box)
            self._browser_list.append(play_all_row)
            top_rows += 1

        # Subdirectories
        for dirname in subdirs:
            row = self._make_browser_row("folder-symbolic", dirname)
            arrow = Gtk.Image(icon_name="go-next-symbolic")
            arrow.set_opacity(0.5)
            row.get_child().append(arrow)
            self._browser_list.append(row)
            top_rows += 1

        self._files_top_rows = top_rows

        # Audio files
        for filename in files:
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)
            row_box.set_margin_top(4)
            row_box.set_margin_bottom(4)

            icon = Gtk.Image(icon_name="audio-x-generic-symbolic")
            icon.set_pixel_size(16)
            row_box.append(icon)

            name_no_ext = os.path.splitext(filename)[0]
            label = Gtk.Label(label=name_no_ext)
            label.set_halign(Gtk.Align.START)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_tooltip_text(filename)
            row_box.append(label)

            row.set_child(row_box)
            self._browser_list.append(row)

        if not subdirs and not files:
            row = self._make_browser_row(
                "folder-symbolic", "Empty folder", activatable=False
            )
            self._browser_list.append(row)

        self._browser_list.connect("row-activated", self._on_library_file_activated)

    def _disconnect_browser_signals(self):
        """Disconnect all browser list activation handlers."""
        for handler in (
            self._on_root_activated,
            self._on_stream_activated,
            self._on_library_folder_activated,
            self._on_library_file_activated,
        ):
            try:
                self._browser_list.disconnect_by_func(handler)
            except TypeError:
                pass

    def _on_library_folder_activated(self, _listbox, row):
        idx = row.get_index()
        if idx < len(self._library_folders):
            self._show_library_files_view(idx)

    def _on_library_file_activated(self, _listbox, row):
        idx = row.get_index()
        top_rows = self._files_top_rows
        files = self._current_files
        subdirs = self._current_subdirs
        has_play_all = len(files) > 0

        # Determine what was clicked
        if has_play_all and idx == 0:
            # Play All
            if self._active_speaker:
                self._play_folder_files(files, start_index=0)
            return

        # Offset past Play All row
        adjusted = idx - (1 if has_play_all else 0)

        if adjusted < len(subdirs):
            # Subfolder clicked — navigate into it
            subdir = subdirs[adjusted]
            new_rel = os.path.join(self._current_subfolder_rel, subdir) if self._current_subfolder_rel else subdir
            self._show_library_files_view(self._current_folder_index, subfolder_rel=new_rel)
            return

        # Audio file clicked
        file_index = adjusted - len(subdirs)
        if self._active_speaker and 0 <= file_index < len(files):
            self._play_folder_files(files, start_index=file_index)

    def _play_folder_files(self, files, start_index=0):
        """Build queue from files in current folder path and start playing."""
        if not self._active_speaker or not files:
            return

        folder_path = self._current_folder_path
        folder_idx = self._current_folder_index
        subfolder_rel = self._current_subfolder_rel

        # Update audio server dirs
        folders = load_library_folders()
        self._audio_server.set_dirs(folders)

        # Build queue items — use subfolder-relative paths for the HTTP server
        items = []
        for filename in files:
            rel_path = os.path.join(subfolder_rel, filename) if subfolder_rel else filename
            url = self._audio_server.file_url(folder_idx, rel_path)
            name_no_ext = os.path.splitext(filename)[0]
            items.append({"name": filename, "url": url, "title": name_no_ext})

        self._queue.set_queue(items, start_index=start_index)
        track = self._queue.current
        if track:
            self._play_queue_track(track)
        self._update_skip_buttons()

    def _on_add_folder_clicked(self, _btn):
        """Open a folder chooser dialog."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Music Folder")
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                add_library_folder(path)
                # Update audio server
                folders = load_library_folders()
                self._audio_server.set_dirs(folders)
                self._show_library_folders_view()
        except Exception:
            pass

    def _on_remove_folder_clicked(self, _btn, index):
        folder = self._library_folders[index]
        folder_name = os.path.basename(folder) or folder
        dialog = Adw.AlertDialog(
            heading="Remove Folder",
            body=f'Remove "{folder_name}" from library?',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self._on_remove_folder_response, index)
        dialog.present(self)

    def _on_remove_folder_response(self, dialog, response, index):
        if response == "remove":
            remove_library_folder(index)
            folders = load_library_folders()
            self._audio_server.set_dirs(folders)
            self._show_library_folders_view()

    # ── Theme ────────────────────────────────────────────────────────

    def _load_theme_preference(self):
        prefs_file = os.path.join(CONFIG_DIR, "preferences.json")
        dark = True  # default to dark
        if os.path.exists(prefs_file):
            try:
                with open(prefs_file, "r") as f:
                    prefs = json.load(f)
                    dark = prefs.get("dark_mode", True)
            except (json.JSONDecodeError, OSError):
                pass
        self._dark_mode = dark
        self._apply_theme()

    def _save_theme_preference(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        prefs_file = os.path.join(CONFIG_DIR, "preferences.json")
        prefs = {}
        if os.path.exists(prefs_file):
            try:
                with open(prefs_file, "r") as f:
                    prefs = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        prefs["dark_mode"] = self._dark_mode
        with open(prefs_file, "w") as f:
            json.dump(prefs, f, indent=2)

    def _apply_theme(self):
        if self._dark_mode:
            self._style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            self._style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)

    def _update_theme_icon(self):
        if self._dark_mode:
            self._theme_btn.set_icon_name("weather-clear-symbolic")
            self._theme_btn.set_tooltip_text("Switch to light mode")
        else:
            self._theme_btn.set_icon_name("weather-clear-night-symbolic")
            self._theme_btn.set_tooltip_text("Switch to dark mode")

    def _on_theme_toggled(self, _btn):
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        self._update_theme_icon()
        self._save_theme_preference()

    # ── Audio server ─────────────────────────────────────────────────

    def _start_audio_server(self):
        folders = load_library_folders()
        self._audio_server.set_dirs(folders)
        self._audio_server.start()

    # ── Discovery ────────────────────────────────────────────────────

    def _start_discovery(self):
        self._refresh_btn.set_sensitive(False)
        discover_speakers(self._on_speakers_found)

    def _on_speakers_found(self, speakers):
        self._speakers = speakers
        self._refresh_btn.set_sensitive(True)

        # Clear the list
        while True:
            row = self._speaker_list.get_row_at_index(0)
            if row is None:
                break
            self._speaker_list.remove(row)

        if not speakers:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label="No speakers found")
            label.set_margin_start(12)
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            row.set_child(label)
            self._speaker_list.append(row)
            return

        for speaker in speakers:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=speaker.player_name)
            label.set_halign(Gtk.Align.START)
            label.set_margin_start(12)
            label.set_margin_top(8)
            label.set_margin_bottom(8)
            row.set_child(label)
            self._speaker_list.append(row)

        if len(speakers) == 1:
            self._speaker_list.select_row(self._speaker_list.get_row_at_index(0))

    def _on_refresh_clicked(self, _btn):
        while True:
            row = self._speaker_list.get_row_at_index(0)
            if row is None:
                break
            self._speaker_list.remove(row)

        self._spinner_row = Gtk.ListBoxRow()
        spinner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spinner_box.set_margin_start(12)
        spinner_box.set_margin_top(8)
        spinner_box.set_margin_bottom(8)
        spinner = Gtk.Spinner(spinning=True)
        spinner_box.append(spinner)
        spinner_box.append(Gtk.Label(label="Searching..."))
        self._spinner_row.set_child(spinner_box)
        self._speaker_list.append(self._spinner_row)

        self._stop_polling()
        self._set_controls_sensitive(False)
        self._active_speaker = None
        self._start_discovery()

    # ── Speaker selection ────────────────────────────────────────────

    def _on_speaker_selected(self, _listbox, row):
        if row is None:
            self._active_speaker = None
            self._set_controls_sensitive(False)
            return

        idx = row.get_index()
        if idx < len(self._speakers):
            self._active_speaker = self._speakers[idx]
            self._set_controls_sensitive(True)
            self._volume_scale.set_value(self._active_speaker.volume)
            if self._active_speaker.mute:
                self._mute_btn.set_icon_name("audio-volume-muted-symbolic")
                self._mute_btn.set_tooltip_text("Unmute")
            else:
                self._mute_btn.set_icon_name("audio-volume-high-symbolic")
                self._mute_btn.set_tooltip_text("Mute")
            self._start_polling()

    # ── Transport controls ───────────────────────────────────────────

    def _on_play_clicked(self, _btn):
        if not self._active_speaker:
            return
        try:
            self._active_speaker.play()
        except Exception:
            pass

    def _on_pause_clicked(self, _btn):
        if not self._active_speaker:
            return
        try:
            state = get_transport_state(self._active_speaker)
            if state == "PLAYING":
                self._active_speaker.pause()
            else:
                self._active_speaker.play()
        except Exception:
            pass

    def _on_mute_clicked(self, _btn):
        if not self._active_speaker:
            return
        try:
            is_muted = self._active_speaker.mute
            self._active_speaker.mute = not is_muted
            if is_muted:
                self._mute_btn.set_icon_name("audio-volume-high-symbolic")
                self._mute_btn.set_tooltip_text("Mute")
            else:
                self._mute_btn.set_icon_name("audio-volume-muted-symbolic")
                self._mute_btn.set_tooltip_text("Unmute")
        except Exception:
            pass

    def _on_prev_clicked(self, _btn):
        if not self._active_speaker:
            return
        track = self._queue.prev()
        if track:
            self._play_queue_track(track)
        self._update_skip_buttons()

    def _on_next_clicked(self, _btn):
        if not self._active_speaker:
            return
        track = self._queue.next()
        if track:
            self._play_queue_track(track)
        self._update_skip_buttons()

    def _play_queue_track(self, track):
        """Play a track from the queue on the active speaker."""
        if not self._active_speaker:
            return
        try:
            play_stream(self._active_speaker, track["url"], title=track["title"])
        except Exception:
            pass

    def _update_skip_buttons(self):
        """Update prev/next button sensitivity based on queue state."""
        has_speaker = self._active_speaker is not None
        self._prev_btn.set_sensitive(has_speaker and self._queue.has_prev)
        self._next_btn.set_sensitive(has_speaker and self._queue.has_next)

    def _on_seek_pressed(self, gesture, n_press, x, y):
        """User started dragging the seek slider."""
        self._seeking = True

    def _on_seek_released(self, gesture, n_press, x, y):
        """User released the seek slider — perform the seek."""
        self._seeking = False
        if not self._active_speaker:
            return
        seconds = max(0, int(self._seek_scale.get_value()))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        time_str = f"{h}:{m:02d}:{s:02d}"
        try:
            self._active_speaker.seek(time_str)
        except Exception:
            pass

    def _on_volume_changed(self, scale):
        vol = int(scale.get_value())
        self._volume_label.set_text(str(vol))
        if self._active_speaker:
            self._active_speaker.volume = vol

    def _set_controls_sensitive(self, sensitive):
        self._play_btn.set_sensitive(sensitive)
        self._pause_btn.set_sensitive(sensitive)
        self._prev_btn.set_sensitive(sensitive)
        self._next_btn.set_sensitive(sensitive)
        self._volume_scale.set_sensitive(sensitive)

    # ── Now Playing polling ──────────────────────────────────────────

    def _start_polling(self):
        if self._poll_source_id is not None:
            return
        self._poll_source_id = GLib.timeout_add_seconds(3, self._poll_track_info)
        self._poll_track_info()

    def _stop_polling(self):
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None

    @staticmethod
    def _time_to_seconds(time_str):
        """Convert 'H:MM:SS' or 'M:SS' to total seconds."""
        parts = time_str.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
        return 0

    @staticmethod
    def _format_time(seconds):
        """Format seconds as M:SS or H:MM:SS."""
        if seconds <= 0:
            return "0:00"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _poll_track_info(self):
        if not self._active_speaker:
            self._np_stream_name.set_text("")
            self._np_title.set_text("Nothing playing")
            self._np_artist.set_text("")
            self._np_album.set_text("")
            self._np_position.set_text("")
            self._room_now_playing.set_text("")
            return False

        try:
            track = self._active_speaker.get_current_track_info()
            media = self._active_speaker.get_current_media_info()
            state = get_transport_state(self._active_speaker)

            title = track.get("title", "").strip()
            artist = track.get("artist", "").strip()
            album = track.get("album", "").strip()
            position = track.get("position", "0:00:00")
            duration = track.get("duration", "0:00:00")
            channel = media.get("channel", "").strip()

            pos_secs = self._time_to_seconds(position)
            dur_secs = self._time_to_seconds(duration)

            self._vu_meter.set_playing(state == "PLAYING")

            # Auto-advance to next track when current one finishes
            if (state == "STOPPED"
                    and self._last_transport_state == "PLAYING"
                    and self._queue.has_next):
                next_track = self._queue.next()
                if next_track:
                    self._play_queue_track(next_track)
                    self._update_skip_buttons()
                    self._last_transport_state = "PLAYING"
                    return True

            self._last_transport_state = state

            if state == "STOPPED":
                self._np_stream_name.set_text("")
                self._np_title.set_text("Stopped")
                self._np_artist.set_text("")
                self._np_album.set_text("")
                self._room_now_playing.set_text("")
                self._seek_scale.set_sensitive(False)
                self._seek_scale.set_range(0, 1)
                self._seek_scale.set_value(0)
                self._seek_position_label.set_text("0:00")
                self._seek_duration_label.set_text("0:00")
            else:
                self._np_stream_name.set_text(channel)
                # Fall back to queue track title if Sonos metadata is empty
                display_title = title
                if not display_title and self._queue.current:
                    display_title = self._queue.current.get("title", "")
                self._np_title.set_text(display_title or "Unknown")
                self._np_artist.set_text(artist)
                self._np_album.set_text(album)
                if display_title:
                    self._room_now_playing.set_text(f"  {display_title}")

                # Update seek slider (skip if user is dragging)
                if dur_secs > 0:
                    self._seek_scale.set_sensitive(True)
                    self._seek_scale.set_range(0, dur_secs)
                    if not self._seeking:
                        self._seek_scale.set_value(pos_secs)
                    self._seek_position_label.set_text(self._format_time(pos_secs))
                    self._seek_duration_label.set_text(self._format_time(dur_secs))
                else:
                    # Stream — no seekable duration
                    self._seek_scale.set_sensitive(False)
                    self._seek_scale.set_range(0, 1)
                    if not self._seeking:
                        self._seek_scale.set_value(0)
                    self._seek_position_label.set_text(self._format_time(pos_secs) if pos_secs else "")
                    self._seek_duration_label.set_text("")
        except Exception:
            pass

        return True
