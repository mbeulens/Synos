"""Album art fetcher via MusicBrainz + Cover Art Archive.

All lookups are blocking — call from a background thread.
Results are cached to disk in ~/.config/synos/artcache/.
"""

import hashlib
import os

import requests

from synos.streams import CONFIG_DIR

# MusicBrainz requires a User-Agent
_HEADERS = {
    "User-Agent": "Synos/1.4 (https://github.com/mbeulens/Synos)",
    "Accept": "application/json",
}

_MB_BASE = "https://musicbrainz.org/ws/2"
_CAA_BASE = "https://coverartarchive.org"

_CACHE_DIR = os.path.join(CONFIG_DIR, "artcache")
# Sentinel file written when a lookup found no art, so we don't retry
_NO_ART_MARKER = b"__no_art__"


def _cache_key(artist, title):
    """Generate a filesystem-safe cache key."""
    raw = f"{artist.lower().strip()}|{title.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def fetch_album_art(artist, title):
    """Fetch album art for a given artist + title.

    Returns image bytes (JPEG/PNG) or None if not found.
    This is a blocking call — run in a background thread.
    """
    if not title:
        return None

    key = _cache_key(artist, title)
    cache_path = os.path.join(_CACHE_DIR, key)

    # Check disk cache
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            data = f.read()
        if data == _NO_ART_MARKER:
            return None
        return data

    image_data = _lookup(artist, title)

    # Write to disk cache
    _ensure_cache_dir()
    with open(cache_path, "wb") as f:
        f.write(image_data if image_data else _NO_ART_MARKER)

    return image_data


def _lookup(artist, title):
    """Query MusicBrainz for release, then fetch cover from CAA."""
    query_parts = [f'recording:"{title}"']
    if artist:
        query_parts.append(f'artist:"{artist}"')
    query = " AND ".join(query_parts)

    try:
        resp = requests.get(
            f"{_MB_BASE}/recording",
            params={"query": query, "limit": 5, "fmt": "json"},
            headers=_HEADERS,
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        recordings = data.get("recordings", [])

        for recording in recordings:
            releases = recording.get("releases", [])
            for release in releases:
                release_id = release.get("id")
                if not release_id:
                    continue
                art = _fetch_cover(release_id)
                if art:
                    return art

    except (requests.RequestException, ValueError, KeyError):
        pass

    return None


def _fetch_cover(release_id):
    """Fetch front cover image from Cover Art Archive."""
    try:
        resp = requests.get(
            f"{_CAA_BASE}/release/{release_id}/front-250",
            timeout=5,
            allow_redirects=True,
        )
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
    except requests.RequestException:
        pass
    return None
