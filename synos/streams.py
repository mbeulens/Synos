"""Persistent stream storage — saved as JSON in user config dir."""

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "synos")
STREAMS_FILE = os.path.join(CONFIG_DIR, "streams.json")

DEFAULT_STREAMS = [
    {"name": "DI.FM Hard Dance", "url": "http://prem2.di.fm:80/harddance?10108cc80386cf2a496dbad2"},
]


def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_streams():
    """Load streams from disk. Returns list of {name, url} dicts."""
    if not os.path.exists(STREAMS_FILE):
        save_streams(DEFAULT_STREAMS)
        return list(DEFAULT_STREAMS)
    try:
        with open(STREAMS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_STREAMS)


def save_streams(streams):
    """Save streams list to disk."""
    _ensure_config_dir()
    with open(STREAMS_FILE, "w") as f:
        json.dump(streams, f, indent=2)


def add_stream(name, url):
    """Add a stream and save."""
    streams = load_streams()
    streams.append({"name": name, "url": url})
    save_streams(streams)
    return streams


def remove_stream(index):
    """Remove a stream by index and save."""
    streams = load_streams()
    if 0 <= index < len(streams):
        streams.pop(index)
        save_streams(streams)
    return streams


def edit_stream(index, name, url):
    """Edit a stream's name and URL."""
    streams = load_streams()
    if 0 <= index < len(streams):
        streams[index] = {"name": name, "url": url}
        save_streams(streams)
    return streams


def move_stream(index, direction):
    """Move a stream up (-1) or down (+1)."""
    streams = load_streams()
    new_index = index + direction
    if 0 <= index < len(streams) and 0 <= new_index < len(streams):
        streams[index], streams[new_index] = streams[new_index], streams[index]
        save_streams(streams)
    return streams
