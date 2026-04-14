# Changelog

## v2.0.0 — Minor release

### YouTube Music — Fully Working
- **Search** songs via ytmusicapi (no login required)
- **Liked Music** playlist built-in
- **Add playlists** manually by pasting URL or ID from YouTube Music
- **Download & convert** audio to MP3 via yt-dlp + ffmpeg, cached in `~/.config/synos/ytcache/`
- **Auto-skip** unavailable tracks (Shorts, removed videos)
- **OAuth setup** for future API access (device code flow shown in console)
- Requires `ffmpeg` and `nodejs` system packages

### SoundCloud — Fully Working
- **Search** tracks
- **My Tracks** — browse uploaded songs
- **My Playlists** — browse sets/playlists
- **Direct MP3** playback with seek slider support
- Profile URL and browser cookies configurable in Settings

### Technical Improvements
- Media proxy downloads to temp file then serves (reliable for all formats)
- Local file serving for yt-dlp downloaded MP3s
- Auto-skip to next track when extraction fails
- Detailed error logging for all extraction attempts

## v1.8.0 — Minor release

### New Features
- **Music Services** — YouTube Music and SoundCloud integration
- **Media Proxy** — Local HTTP server proxies audio streams
- **Settings page** — Configure browser for cookie auth, SoundCloud profile URL

## v1.6.0 — Minor release

### New Features
- **Keyboard Shortcuts** — Space: play/pause, F12: toggle console, Arrow Up/Down: volume +/- 2

### Improvements
- Album art smart retry increased to 5 attempts with artist variants and no-artist fallback
- Skip album art lookup for Sonos internal states (ZPSTR_BUFFERING, etc.)

## v1.5.0 — Minor release

### New Features
- **Album Art** — Fetches cover art from MusicBrainz + Cover Art Archive
- **Console Log** — Collapsible log window

## v1.2.0 — Minor release

### New Features
- **Equalizer** — Bass/treble sliders and loudness toggle
- **YouTube Search** — One-click search for current track
- **Discogs Search** — One-click search on Discogs

## v1.0.0 — Major release

### Features
- Music Library with subfolder navigation, Play All, auto-advance
- Play queue with prev/next
- Seek slider for local files
- Non-blocking UI — all playback in background threads
- VU meter with random bar patterns

### Previous features (v0.3.0)
- Three-panel layout: Rooms, Now Playing, Music Browser
- Sonos speaker discovery, stream playback, light/dark mode
- Transport controls, volume, mute, desktop launcher
