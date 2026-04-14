"""YouTube Music service — search, browse playlists, extract audio."""

import json
import os
import tempfile
import threading

from synos.streams import CONFIG_DIR

_PREFS_FILE = os.path.join(CONFIG_DIR, "ytmusic_prefs.json")
_OAUTH_FILE = os.path.join(CONFIG_DIR, "ytmusic_oauth.json")
_CREDENTIALS_FILE = os.path.join(CONFIG_DIR, "ytmusic_credentials.json")
_DOWNLOAD_DIR = os.path.join(CONFIG_DIR, "ytcache")

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


def get_oauth_credentials():
    """Get OAuth client_id and client_secret from config."""
    if os.path.exists(_CREDENTIALS_FILE):
        try:
            with open(_CREDENTIALS_FILE, "r") as f:
                creds = json.load(f)
                return creds.get("client_id", ""), creds.get("client_secret", "")
        except (json.JSONDecodeError, OSError):
            pass
    return "", ""


def set_oauth_credentials(client_id, client_secret):
    """Save OAuth credentials to config."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(_CREDENTIALS_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=2)


def get_browser():
    """Get the configured browser for cookie extraction."""
    return _load_prefs().get("browser", "")


def set_browser(browser):
    """Set the browser to use for cookie extraction."""
    prefs = _load_prefs()
    prefs["browser"] = browser
    _save_prefs(prefs)


def is_configured():
    """Check if OAuth is configured."""
    return os.path.exists(_OAUTH_FILE)


def is_oauth_authenticated():
    """Check if we have a valid OAuth token."""
    return os.path.exists(_OAUTH_FILE)


def setup_oauth(callback=None):
    """Run the OAuth flow in a background thread."""
    _logmsg("YTMusic: Starting OAuth flow...", "info")
    _logmsg("A browser window will open for Google login", "info")

    def _do_oauth():
        try:
            import time
            import webbrowser
            from pathlib import Path
            from ytmusicapi.auth.oauth.credentials import OAuthCredentials
            from ytmusicapi.auth.oauth.token import RefreshingToken

            client_id, client_secret = get_oauth_credentials()
            if not client_id or not client_secret:
                _logmsg("YTMusic OAuth: No credentials configured. Set them in Settings.", "error")
                if callback:
                    callback(False)
                return

            credentials = OAuthCredentials(client_id, client_secret)
            code = credentials.get_code()
            user_code = code["user_code"]
            device_code = code["device_code"]
            verification_url = code["verification_url"]
            interval = code.get("interval", 5)
            expires_in = code.get("expires_in", 1800)

            url = f"{verification_url}?user_code={user_code}"

            _logmsg(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")
            _logmsg(f"Your code: {user_code}", "success")
            _logmsg(f"Enter this code at: {verification_url}", "info")
            _logmsg(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "info")

            webbrowser.open(url)

            _logmsg("Waiting for you to complete login in browser...", "info")
            deadline = time.time() + expires_in
            while time.time() < deadline:
                time.sleep(interval)
                try:
                    raw_token = credentials.token_from_code(device_code)
                    if isinstance(raw_token, dict) and "error" in raw_token:
                        error = raw_token["error"]
                        if error in ("authorization_pending", "slow_down"):
                            continue
                        else:
                            raise Exception(error)
                    os.makedirs(CONFIG_DIR, exist_ok=True)
                    token_keys = {"access_token", "refresh_token", "token_type", "expires_in", "expires_at", "scope"}
                    clean_token = {k: v for k, v in raw_token.items() if k in token_keys}
                    ref_token = RefreshingToken(credentials=credentials, **clean_token)
                    ref_token.update(ref_token.as_dict())
                    ref_token.local_cache = Path(_OAUTH_FILE)
                    ref_token.store_token()
                    _logmsg("YTMusic OAuth: Authentication successful!", "success")
                    if callback:
                        callback(True)
                    return
                except Exception as poll_err:
                    err_str = str(poll_err).lower()
                    if "authorization_pending" in err_str or "slow_down" in err_str:
                        continue
                    else:
                        raise

            _logmsg("YTMusic OAuth: Timed out waiting for login", "error")
            if callback:
                callback(False)

        except Exception as e:
            _logmsg(f"YTMusic OAuth error: {e}", "error")
            if callback:
                callback(False)

    threading.Thread(target=_do_oauth, daemon=True).start()


def search(query, limit=20):
    """Search YouTube Music for songs."""
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


_PLAYLISTS_FILE = os.path.join(CONFIG_DIR, "ytmusic_playlists.json")


def _load_saved_playlists():
    if os.path.exists(_PLAYLISTS_FILE):
        try:
            with open(_PLAYLISTS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_playlists(playlists):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(_PLAYLISTS_FILE, "w") as f:
        json.dump(playlists, f, indent=2)


def add_playlist(title, playlist_id):
    """Add a user playlist by title and ID."""
    playlists = _load_saved_playlists()
    # Don't add duplicates
    if not any(p["playlist_id"] == playlist_id for p in playlists):
        playlists.append({"title": title, "playlist_id": playlist_id, "count": 0})
        _save_playlists(playlists)
    return get_playlists()


def remove_playlist(index):
    """Remove a user-added playlist by index (offset past built-in ones)."""
    playlists = _load_saved_playlists()
    adj = index - 1  # offset past "Liked Music"
    if 0 <= adj < len(playlists):
        playlists.pop(adj)
        _save_playlists(playlists)
    return get_playlists()


def extract_playlist_id(url_or_id):
    """Extract playlist ID from a YouTube Music URL or raw ID."""
    import re
    # Try to extract from URL
    match = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    # Might be a raw ID
    return url_or_id.strip()


def get_playlists():
    """Get YouTube Music playlists — built-in + user-added."""
    _logmsg("YTMusic fetching playlists", "info")

    playlists = [
        {"title": "Liked Music", "playlist_id": "LM", "count": 0},
    ]
    playlists.extend(_load_saved_playlists())

    _logmsg(f"YTMusic returning {len(playlists)} playlists", "success")
    return playlists


def get_playlist_tracks(playlist_id):
    """Get tracks from a YouTube Music playlist via yt-dlp."""
    browser = get_browser()
    _logmsg(f"YTMusic playlist tracks: {playlist_id}", "info")

    try:
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "extractor_args": {"youtubetab": {"skip": ["authcheck"]}},
        }
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

        url = f"https://music.youtube.com/playlist?list={playlist_id}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(url, download=False)

        tracks = []
        for entry in result.get("entries", []):
            vid = entry.get("id")
            if not vid:
                continue
            duration = entry.get("duration")
            dur_str = ""
            if duration:
                duration = int(duration)
                dur_str = f"{duration // 60}:{duration % 60:02d}"
            tracks.append({
                "title": entry.get("title", ""),
                "artist": entry.get("uploader", ""),
                "video_id": vid,
                "duration": dur_str,
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            })

        _logmsg(f"YTMusic playlist has {len(tracks)} tracks", "success")
        return tracks

    except Exception as e:
        _logmsg(f"YTMusic playlist error: {e}", "error")
        return []


def extract_audio_url(video_id):
    """Download audio from YouTube and return local file path.

    Uses yt-dlp to download and convert to MP3.
    Returns {url: file_path, direct: True, content_type: audio/mpeg} or None.
    """
    _logmsg(f"YTMusic downloading audio: {video_id}", "info")

    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    output_path = os.path.join(_DOWNLOAD_DIR, f"{video_id}.mp3")

    # Return cached file if exists
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        _logmsg(f"YTMusic cache hit: {output_path}", "success")
        return {"url": output_path, "direct": True, "content_type": "audio/mpeg", "local_file": True}

    try:
        import yt_dlp

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "outtmpl": os.path.join(_DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

        yt_url = f"https://www.youtube.com/watch?v={video_id}"
        _logmsg(f"  Downloading: {yt_url}")

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([yt_url])

        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            _logmsg(f"YTMusic downloaded: {output_path} ({size} bytes)", "success")
            return {"url": output_path, "direct": True, "content_type": "audio/mpeg", "local_file": True}
        else:
            _logmsg(f"YTMusic: output file not found after download", "error")
            return None

    except Exception as e:
        _logmsg(f"YTMusic download error: {e}", "error")
        return None
