"""Album art fetcher via MusicBrainz + Cover Art Archive.

All lookups are blocking — call from a background thread.
Results are cached to disk in ~/.config/synos/artcache/.
"""

import hashlib
import os
import re

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
_NO_ART_MARKER = b"__no_art__"

# Optional log callback — set by the window
_log = None


def set_log_callback(callback):
    """Set a logging callback: callback(message, tag=None)."""
    global _log
    _log = callback


def _logmsg(msg, tag=None):
    if _log:
        _log(msg, tag)


def _cache_key(artist, title):
    """Generate a filesystem-safe cache key."""
    raw = f"{artist.lower().strip()}|{title.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _clean_artist_variants(artist):
    """Generate artist variants: original, then first artist if multi-artist."""
    if not artist:
        return [""]
    variants = [artist]
    # Split on comma, slash, &, "feat.", "ft."
    first = re.split(r"[,/&]|\bfeat\.?\b|\bft\.?\b", artist, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if first and first != artist:
        variants.append(first)
    return variants


def _clean_title_variants(artist, title):
    """Generate up to 3 cleaned title variants for retry.

    1. Original title as-is
    2. Strip track numbers (e.g. "06 - ") and artist prefix (e.g. "Artist - ")
    3. Also strip parenthesized content (e.g. "(Original Mix)")
    """
    variants = []

    # Variant 1: original
    variants.append(title)

    # Variant 2: strip leading track number and artist prefix
    cleaned = title
    # Remove leading track numbers like "01 - ", "06 ", "12. ", "01-"
    cleaned = re.sub(r"^\d{1,3}\s*[-.\)]\s*", "", cleaned)
    # Remove artist prefix like "Artist - " or "Artist- "
    if artist:
        pattern = re.escape(artist) + r"\s*[-–]\s*"
        cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if cleaned and cleaned != title:
        variants.append(cleaned)

    # Variant 3: also strip parenthesized content
    stripped = re.sub(r"\s*\(.*?\)", "", cleaned).strip()
    if stripped and stripped not in variants:
        variants.append(stripped)

    return variants[:3]


def fetch_album_art(artist, title):
    """Fetch album art for a given artist + title.

    Tries up to 3 cleaned title variants. Returns image bytes or None.
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
            _logmsg(f"Art cache hit (no art): {artist} - {title}")
            return None
        _logmsg(f"Art cache hit ({len(data)} bytes): {artist} - {title}", "success")
        return data

    _logmsg(f"Art cache miss, fetching: {artist} - {title}", "info")

    # Build list of (artist, title) pairs to try
    title_variants = _clean_title_variants(artist, title)
    artist_variants = _clean_artist_variants(artist)

    attempts = []
    seen = set()
    for a in artist_variants:
        for t in title_variants:
            pair = (a, t)
            if pair not in seen:
                seen.add(pair)
                attempts.append(pair)
    # Cap at 3 attempts
    attempts = attempts[:3]

    image_data = None
    for i, (a, t) in enumerate(attempts):
        label = f"[attempt {i + 1}/{len(attempts)}]"
        _logmsg(f"  {label} artist: \"{a}\", title: \"{t}\"", "info")
        image_data = _lookup(a, t)
        if image_data:
            _logmsg(f"  {label} Found art!", "success")
            break
        _logmsg(f"  {label} No art found")

    # Write to disk cache
    _ensure_cache_dir()
    with open(cache_path, "wb") as f:
        f.write(image_data if image_data else _NO_ART_MARKER)

    if image_data:
        _logmsg(f"Art cached ({len(image_data)} bytes): {artist} - {title}", "success")
    else:
        _logmsg(f"Art not found after {len(variants)} attempts, cached negative: {artist} - {title}")

    return image_data


def _lookup(artist, title):
    """Query MusicBrainz for release, then fetch cover from CAA."""
    query_parts = [f'recording:"{title}"']
    if artist:
        query_parts.append(f'artist:"{artist}"')
    query = " AND ".join(query_parts)

    url = f"{_MB_BASE}/recording"
    params = {"query": query, "limit": 5, "fmt": "json"}
    _logmsg(f"MusicBrainz query: {query}")
    _logmsg(f"  GET {url}?query={query}&limit=5&fmt=json")

    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=5)
        _logmsg(f"  MusicBrainz response: {resp.status_code}")
        if resp.status_code != 200:
            _logmsg(f"  MusicBrainz error: HTTP {resp.status_code}", "error")
            return None

        data = resp.json()
        recordings = data.get("recordings", [])
        _logmsg(f"  Found {len(recordings)} recording(s)")

        for recording in recordings:
            releases = recording.get("releases", [])
            for release in releases:
                release_id = release.get("id")
                release_title = release.get("title", "?")
                if not release_id:
                    continue
                _logmsg(f"  Trying release: {release_title} ({release_id})")
                art = _fetch_cover(release_id)
                if art:
                    return art

    except requests.RequestException as e:
        _logmsg(f"  MusicBrainz request error: {e}", "error")
    except (ValueError, KeyError) as e:
        _logmsg(f"  MusicBrainz parse error: {e}", "error")

    return None


def _fetch_cover(release_id):
    """Fetch front cover image from Cover Art Archive."""
    url = f"{_CAA_BASE}/release/{release_id}/front-250"
    _logmsg(f"  GET {url}")
    try:
        resp = requests.get(url, timeout=5, allow_redirects=True)
        _logmsg(f"  CAA response: {resp.status_code} ({len(resp.content)} bytes)")
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
    except requests.RequestException as e:
        _logmsg(f"  CAA request error: {e}", "error")
    return None
