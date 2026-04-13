# Changelog

## v1.0.0 — Major release

### Music Library
- Browse and play local audio files from configurable folders
- Subfolder navigation with back button
- Play single track or entire folder with "Play All"
- Auto-advance to next track when current one finishes
- Supported formats: mp3, flac, aac, ogg, wav, wma, m4a, opus
- Local HTTP server serves files to Sonos speakers

### Play Queue
- Full queue management with prev/next navigation
- Headerbar prev/next buttons wired to queue state
- Queue built automatically from folder contents

### Seek Slider
- Draggable seek slider for local file playback
- Shows current position and total duration
- Debounced seeking — sends command after user stops dragging
- Disabled for streams (no seekable duration)
- Resets immediately when switching tracks

### Performance
- All playback calls run in background threads — no UI freezing
- Responsive slider and controls even with large files

### VU Meter
- Refined random bar patterns (no more ocean wave effect)
- Fixed height at 100px, pinned to bottom of center pane

### Previous features (v0.3.0)
- Three-panel layout: Rooms, Now Playing, Music Browser
- Sonos speaker discovery via SSDP with auto-select
- Stream playback with browsable Streams folder
- Now Playing display with track title, artist, stream name
- Animated VU meter visualizer
- Light/Dark mode toggle with persistent preference
- Transport controls, volume slider, mute/unmute
- Desktop launcher

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
