"""Play queue — manages a list of tracks with current position."""


class PlayQueue:
    """Ordered list of tracks with prev/next navigation.

    Each item is a dict with at least: {name, url, title}
    """

    def __init__(self):
        self._items = []
        self._index = -1

    @property
    def items(self):
        return list(self._items)

    @property
    def index(self):
        return self._index

    @property
    def current(self):
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return None

    @property
    def has_next(self):
        return self._index < len(self._items) - 1

    @property
    def has_prev(self):
        return self._index > 0

    def clear(self):
        self._items = []
        self._index = -1

    def set_queue(self, items, start_index=0):
        """Replace the queue with a new list of items."""
        self._items = list(items)
        self._index = start_index if items else -1

    def next(self):
        """Advance to next track. Returns the track or None."""
        if self.has_next:
            self._index += 1
            return self.current
        return None

    def prev(self):
        """Go to previous track. Returns the track or None."""
        if self.has_prev:
            self._index -= 1
            return self.current
        return None
