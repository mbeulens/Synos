"""Music library — manage local folders and scan for audio files."""

import json
import os

from synos.streams import CONFIG_DIR

LIBRARY_FILE = os.path.join(CONFIG_DIR, "library.json")

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".aac", ".ogg", ".wav", ".wma", ".m4a", ".opus",
}


def load_library_folders():
    """Load the list of library folder paths."""
    if not os.path.exists(LIBRARY_FILE):
        return []
    try:
        with open(LIBRARY_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_library_folders(folders):
    """Save the list of library folder paths."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LIBRARY_FILE, "w") as f:
        json.dump(folders, f, indent=2)


def add_library_folder(path):
    """Add a folder to the library and save."""
    folders = load_library_folders()
    path = os.path.abspath(path)
    if path not in folders:
        folders.append(path)
        save_library_folders(folders)
    return folders


def remove_library_folder(index):
    """Remove a folder by index and save."""
    folders = load_library_folders()
    if 0 <= index < len(folders):
        folders.pop(index)
        save_library_folders(folders)
    return folders


def scan_folder(folder_path):
    """Scan a folder for subdirectories and supported audio files.

    Returns (subdirs, files) where both are sorted name lists.
    """
    subdirs = []
    files = []
    if not os.path.isdir(folder_path):
        return subdirs, files

    for entry in os.scandir(folder_path):
        if entry.is_dir() and not entry.name.startswith("."):
            subdirs.append(entry.name)
        elif entry.is_file():
            ext = os.path.splitext(entry.name)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                files.append(entry.name)

    subdirs.sort(key=str.lower)
    files.sort(key=str.lower)
    return subdirs, files
