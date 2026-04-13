# Changelog

## v0.3.0 — Minor release

### Features
- Three-panel layout: Rooms, Now Playing, Music Browser
- Sonos speaker discovery via SSDP with auto-select
- Stream playback using `x-rincon-mp3radio://` URI scheme
- Now Playing display with track title, artist, album, position
- Stream/channel name shown below Now Playing header
- Animated VU meter visualizer (32-bar, green/yellow/red gradient with peak hold)
- Browsable Music panel with Streams folder (add/remove/play)
- Stream persistence in `~/.config/synos/streams.json`
- Light/Dark mode toggle with persistent preference
- Transport controls: play, pause, skip (headerbar)
- Volume slider and mute/unmute toggle
- Version shown in titlebar
- Desktop launcher (`com.github.synos.desktop`)

### Technical
- Built with Python 3, GTK4, Libadwaita, SoCo
- Requires system packages: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`
- Theme-aware CSS using Adw color variables
