"""Album art fetcher via MusicBrainz + Cover Art Archive.

All lookups are blocking — call from a background thread.
Results are cached in memory to avoid redundant requests.
"""

import requests

# MusicBrainz requires a User-Agent
_HEADERS = {
    "User-Agent": "Synos/1.4 (https://github.com/mbeulens/Synos)",
    "Accept": "application/json",
}

_MB_BASE = "https://musicbrainz.org/ws/2"
_CAA_BASE = "https://coverartarchive.org"

# In-memory cache: (artist, title) -> image bytes or None
_cache = {}


def fetch_album_art(artist, title):
    """Fetch album art for a given artist + title.

    Returns image bytes (JPEG/PNG) or None if not found.
    This is a blocking call — run in a background thread.
    """
    if not title:
        return None

    key = (artist.lower().strip(), title.lower().strip())
    if key in _cache:
        return _cache[key]

    image_data = _lookup(artist, title)
    _cache[key] = image_data
    return image_data


def _lookup(artist, title):
    """Query MusicBrainz for release, then fetch cover from CAA."""
    # Build search query
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

        # Try each recording's releases for cover art
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
