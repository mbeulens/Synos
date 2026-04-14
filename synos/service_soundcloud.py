"""SoundCloud service — search, browse playlists, extract audio via yt-dlp."""

import json
import os

from synos.streams import CONFIG_DIR

_PREFS_FILE = os.path.join(CONFIG_DIR, "soundcloud_prefs.json")

# Log callback
_log = None


def set_log_callback(callback):
    global _log
    _log = callback


def _logmsg(msg, tag=None):
    if _log:
        _log(msg, tag)


def _load_prefs():
    if os.path.exists(_PREFS_FILE):
        try:
            with open(_PREFS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_prefs(prefs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(_PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


def get_browser():
    """Get the configured browser for cookie extraction."""
    return _load_prefs().get("browser", "")


def set_browser(browser):
    """Set the browser to use for cookie extraction."""
    prefs = _load_prefs()
    prefs["browser"] = browser
    _save_prefs(prefs)


def is_configured():
    """Check if a browser is configured."""
    return bool(get_browser())


def search(query, limit=20):
    """Search SoundCloud for tracks using yt-dlp.

    Returns list of {title, artist, url, duration, track_url}.
    """
    _logmsg(f"SoundCloud search: {query}", "info")

    try:
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "default_search": "scsearch",
        }
        browser = get_browser()
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"scsearch{limit}:{query}", download=False)

        tracks = []
        for entry in result.get("entries", []):
            tracks.append({
                "title": entry.get("title", ""),
                "artist": entry.get("uploader", ""),
                "duration": _format_duration(entry.get("duration")),
                "track_url": entry.get("url", ""),
            })

        _logmsg(f"SoundCloud found {len(tracks)} results", "success")
        return tracks

    except Exception as e:
        _logmsg(f"SoundCloud search error: {e}", "error")
        return []


def get_user_playlists(profile_url=None):
    """Get user's SoundCloud playlists/sets.

    If no profile_url, tries to get from saved prefs.
    Returns list of {title, playlist_url, count}.
    """
    if not profile_url:
        prefs = _load_prefs()
        profile_url = prefs.get("profile_url", "")

    if not profile_url:
        _logmsg("SoundCloud: no profile URL configured", "error")
        return []

    _logmsg(f"SoundCloud fetching playlists: {profile_url}", "info")
    browser = get_browser()

    try:
        import yt_dlp

        # Fetch user's sets/playlists page
        sets_url = f"{profile_url.rstrip('/')}/sets"
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
        }
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(sets_url, download=False)

        playlists = []
        for entry in result.get("entries", []):
            playlists.append({
                "title": entry.get("title", ""),
                "playlist_url": entry.get("url", ""),
                "count": entry.get("playlist_count", 0),
            })

        _logmsg(f"SoundCloud found {len(playlists)} playlists", "success")
        return playlists

    except Exception as e:
        _logmsg(f"SoundCloud playlists error: {e}", "error")
        return []


def get_playlist_tracks(playlist_url):
    """Get tracks from a SoundCloud playlist/set.

    Returns list of {title, artist, duration, track_url}.
    """
    _logmsg(f"SoundCloud playlist tracks: {playlist_url}", "info")
    browser = get_browser()

    try:
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(playlist_url, download=False)

        tracks = []
        for entry in result.get("entries", []):
            title = entry.get("title", "")
            track_url = entry.get("url") or entry.get("webpage_url", "")
            # If flat extraction didn't give us a title, use the URL slug
            if not title and track_url:
                title = track_url.rstrip("/").split("/")[-1].replace("-", " ").title()
            tracks.append({
                "title": title,
                "artist": entry.get("uploader", ""),
                "duration": _format_duration(entry.get("duration")),
                "track_url": track_url,
            })

        _logmsg(f"SoundCloud playlist has {len(tracks)} tracks", "success")
        return tracks

    except Exception as e:
        _logmsg(f"SoundCloud playlist error: {e}", "error")
        return []


def set_profile_url(url):
    """Save the user's SoundCloud profile URL."""
    prefs = _load_prefs()
    prefs["profile_url"] = url
    _save_prefs(prefs)


def get_profile_url():
    """Get the saved SoundCloud profile URL."""
    return _load_prefs().get("profile_url", "")


def extract_audio_url(track_url):
    """Extract the audio stream URL from a SoundCloud track.

    Returns {url, headers, content_type} or None.
    """
    _logmsg(f"SoundCloud extracting audio: {track_url}", "info")
    browser = get_browser()

    try:
        import yt_dlp

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
        }
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(track_url, download=False)

        url = info.get("url")
        if not url:
            formats = info.get("formats", [])
            audio_fmts = [f for f in formats if f.get("acodec") != "none"]
            if audio_fmts:
                best = max(audio_fmts, key=lambda f: f.get("abr", 0) or 0)
                url = best.get("url")

        if not url:
            _logmsg("SoundCloud: no audio URL found", "error")
            return None

        headers = info.get("http_headers", {})
        content_type = "audio/mpeg"

        _logmsg(f"SoundCloud audio extracted: {url[:80]}...", "success")
        return {"url": url, "headers": headers, "content_type": content_type}

    except Exception as e:
        _logmsg(f"SoundCloud extract error: {e}", "error")
        return None


def _format_duration(seconds):
    """Format duration in seconds to M:SS."""
    if not seconds:
        return ""
    seconds = int(seconds)
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"
