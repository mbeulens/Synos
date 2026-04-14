"""YouTube Music service — search, browse playlists, extract audio."""

import json
import os

from synos.streams import CONFIG_DIR

_PREFS_FILE = os.path.join(CONFIG_DIR, "ytmusic_prefs.json")

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
    """Set the browser to use for cookie extraction (firefox, chrome, etc.)."""
    prefs = _load_prefs()
    prefs["browser"] = browser
    _save_prefs(prefs)


def is_configured():
    """Check if a browser is configured."""
    return bool(get_browser())


def search(query, limit=20):
    """Search YouTube Music for songs.

    Returns list of {title, artist, album, duration, video_id, thumbnail}.
    """
    _logmsg(f"YTMusic search: {query}", "info")

    try:
        from ytmusicapi import YTMusic
        yt = YTMusic()
        results = yt.search(query, filter="songs", limit=limit)
    except Exception as e:
        _logmsg(f"YTMusic search error: {e}", "error")
        return []

    tracks = []
    for item in results:
        if item.get("resultType") != "song":
            continue
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        album = item.get("album", {})
        thumbnail = ""
        thumbs = item.get("thumbnails", [])
        if thumbs:
            thumbnail = thumbs[-1].get("url", "")

        tracks.append({
            "title": item.get("title", ""),
            "artist": artists,
            "album": album.get("name", "") if album else "",
            "duration": item.get("duration", ""),
            "video_id": item.get("videoId", ""),
            "thumbnail": thumbnail,
        })

    _logmsg(f"YTMusic found {len(tracks)} results", "success")
    return tracks


def get_playlists():
    """Get user's YouTube Music playlists (requires browser cookies).

    Returns list of {title, playlist_id, count}.
    """
    browser = get_browser()
    if not browser:
        _logmsg("YTMusic playlists: no browser configured", "error")
        return []

    _logmsg(f"YTMusic fetching playlists (browser: {browser})", "info")

    try:
        from ytmusicapi import YTMusic
        yt = YTMusic.from_cookies(browser)
        playlists = yt.get_library_playlists(limit=50)
    except Exception as e:
        _logmsg(f"YTMusic playlists error: {e}", "error")
        return []

    result = []
    for pl in playlists:
        result.append({
            "title": pl.get("title", ""),
            "playlist_id": pl.get("playlistId", ""),
            "count": pl.get("count", 0),
        })

    _logmsg(f"YTMusic found {len(result)} playlists", "success")
    return result


def get_playlist_tracks(playlist_id):
    """Get tracks from a YouTube Music playlist.

    Returns list of {title, artist, video_id, duration, thumbnail}.
    """
    browser = get_browser()
    _logmsg(f"YTMusic playlist tracks: {playlist_id}", "info")

    try:
        from ytmusicapi import YTMusic
        if browser:
            yt = YTMusic.from_cookies(browser)
        else:
            yt = YTMusic()
        playlist = yt.get_playlist(playlist_id, limit=200)
    except Exception as e:
        _logmsg(f"YTMusic playlist error: {e}", "error")
        return []

    tracks = []
    for item in playlist.get("tracks", []):
        artists = ", ".join(a["name"] for a in item.get("artists", []) if a)
        thumbnail = ""
        thumbs = item.get("thumbnails", [])
        if thumbs:
            thumbnail = thumbs[-1].get("url", "")

        vid = item.get("videoId")
        if not vid:
            continue

        tracks.append({
            "title": item.get("title", ""),
            "artist": artists,
            "video_id": vid,
            "duration": item.get("duration", ""),
            "thumbnail": thumbnail,
        })

    _logmsg(f"YTMusic playlist has {len(tracks)} tracks", "success")
    return tracks


def extract_audio_url(video_id):
    """Extract the best audio URL from a YouTube video using yt-dlp.

    Returns {url, headers, content_type} or None.
    """
    _logmsg(f"YTMusic extracting audio: {video_id}", "info")
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
            info = ydl.extract_info(
                f"https://music.youtube.com/watch?v={video_id}",
                download=False,
            )

        url = info.get("url")
        if not url:
            # Try formats list
            formats = info.get("formats", [])
            audio_fmts = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_fmts:
                best = max(audio_fmts, key=lambda f: f.get("abr", 0) or 0)
                url = best.get("url")

        if not url:
            _logmsg("YTMusic: no audio URL found", "error")
            return None

        headers = info.get("http_headers", {})
        content_type = "audio/webm"  # YouTube typically serves webm/opus

        _logmsg(f"YTMusic audio extracted: {url[:80]}...", "success")
        return {"url": url, "headers": headers, "content_type": content_type}

    except Exception as e:
        _logmsg(f"YTMusic extract error: {e}", "error")
        return None
