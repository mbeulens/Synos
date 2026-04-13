"""Sonos network discovery and playback control."""

import threading
from gi.repository import GLib
import soco


DIDL_TEMPLATE = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
    ' xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"'
    ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
    '<item id="R:0/0/0" parentID="R:0/0" restricted="true">'
    '<dc:title>{title}</dc:title>'
    '<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
    '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
    'SA_RINCON65031_</desc>'
    '</item></DIDL-Lite>'
)


def discover_speakers(callback):
    """Discover Sonos speakers in a background thread.

    Args:
        callback: Called on the main thread with a list of SoCo speaker objects.
    """
    def _discover():
        speakers = list(soco.discover(timeout=10) or [])
        GLib.idle_add(callback, speakers)

    thread = threading.Thread(target=_discover, daemon=True)
    thread.start()


def play_stream(speaker, stream_url, title="Internet Radio"):
    """Play an internet radio stream on a Sonos speaker."""
    metadata = DIDL_TEMPLATE.format(title=title)
    sonos_uri = stream_url.replace("http://", "x-rincon-mp3radio://", 1)
    speaker.play_uri(uri=sonos_uri, meta=metadata, title=title)


def play_file(speaker, file_url, title="Audio File"):
    """Play a local audio file (via HTTP URL) on a Sonos speaker.

    Uses plain http:// so Sonos can detect duration and support seeking.
    """
    speaker.play_uri(uri=file_url, title=title)


def get_transport_state(speaker):
    """Return the current transport state string (PLAYING, PAUSED_PLAYBACK, STOPPED)."""
    info = speaker.get_current_transport_info()
    return info.get("current_transport_state", "STOPPED")
