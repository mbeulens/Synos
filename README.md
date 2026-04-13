# Synos

A GTK4 + Libadwaita Sonos controller for Linux.

## Features

- **Speaker Discovery** — Automatically finds Sonos speakers on your network
- **Stream Playback** — Play internet radio streams (Icecast, SHOUTcast, etc.)
- **Now Playing** — Live track info with title, artist, and stream name
- **VU Meter** — Animated 32-bar visualizer with peak hold
- **Music Browser** — Manage saved streams with add/remove/play
- **Light/Dark Mode** — Toggle with persistent preference
- **Transport Controls** — Play, pause, volume, mute from the headerbar

## Requirements

### System packages (Ubuntu/Debian)

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

### Python packages

```bash
pip install soco
```

## Running

```bash
cd Synos
python3 -m synos
```

## Screenshot

Three-panel layout with Rooms, Now Playing (with VU meter), and Music Browser.

## License

MIT
