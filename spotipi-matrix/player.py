"""
Where "what's playing" comes from. Two sources, same interface:

    player.start()
    np_ = player.snapshot()   # NowPlaying or None, safe to call every frame

SpotifyPlayer  - real API, polled on a background thread
FakePlayer     - offline: cycles through covers in ./covers (or generated ones),
                 so you can work on transitions with no wifi and no Spotify
"""
import io
import os
import threading
import time
from dataclasses import dataclass, replace

import numpy as np
from PIL import Image

POLL_SECONDS = 2.5
ART_SIZE = 300     # Spotify serves 640/300/64; 300 is plenty and downloads fast


@dataclass(frozen=True)
class NowPlaying:
    track_id: str
    title: str
    artist: str
    art: np.ndarray          # (N, N, 3) uint8
    duration_ms: int
    progress_ms: int         # as of fetched_at
    is_playing: bool
    fetched_at: float        # time.monotonic() when progress_ms was true

    def progress_now(self):
        """Interpolated progress: no API call needed between polls."""
        p = self.progress_ms
        if self.is_playing:
            p += (time.monotonic() - self.fetched_at) * 1000
        return min(p, self.duration_ms)

    def fraction(self):
        return self.progress_now() / max(self.duration_ms, 1)


class _Base:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = None

    def snapshot(self):
        with self._lock:
            return self._state

    def _set(self, state):
        with self._lock:
            self._state = state

    def handle(self, event):   # keyboard controls, FakePlayer only
        pass


class SpotifyPlayer(_Base):
    """Credentials come from env vars that spotipy reads automatically:
        SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET,
        SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
    First run opens a login (or prints a URL on a headless Pi). The token is
    cached in .spotify_cache; copy that file to the Pi and it never asks again."""

    SCOPE = "user-read-currently-playing user-read-playback-state"

    def __init__(self, headless=False):
        super().__init__()
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            scope=self.SCOPE, cache_path=".spotify_cache", open_browser=not headless))
        self._art_cache = {}

    def start(self):
        self.sp.current_user()               # forces the login now, on the main thread
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        backoff = POLL_SECONDS
        while True:
            try:
                self._set(self._fetch())
                backoff = POLL_SECONDS
            except Exception as e:           # network blips shouldn't kill the display
                print("poll error:", e)
                backoff = min(backoff * 2, 60)
            time.sleep(backoff)

    def _fetch(self):
        t = time.monotonic()
        cur = self.sp.current_user_playing_track()
        item = cur and cur.get("item")
        if not item or item.get("type") != "track":   # nothing playing, ad, or podcast
            return None
        return NowPlaying(
            track_id=item["id"],
            title=item["name"],
            artist=", ".join(a["name"] for a in item["artists"]),
            art=self._art(item),
            duration_ms=item["duration_ms"],
            progress_ms=cur["progress_ms"] or 0,
            is_playing=cur["is_playing"],
            fetched_at=t,
        )

    def _art(self, item):
        url = min(item["album"]["images"], key=lambda im: abs((im["width"] or 0) - ART_SIZE))["url"]
        if url not in self._art_cache:
            import requests
            img = Image.open(io.BytesIO(requests.get(url, timeout=10).content)).convert("RGB")
            self._art_cache[url] = np.asarray(img)
        return self._art_cache[url]


class FakePlayer(_Base):
    """Offline stand-in. Drop .jpg/.png covers into ./covers to test with real art."""

    def __init__(self, cover_dir="covers", track_seconds=(25, 45)):
        super().__init__()
        rng = np.random.default_rng(7)
        files = sorted(f for f in os.listdir(cover_dir)
                       if f.lower().endswith((".jpg", ".jpeg", ".png"))) if os.path.isdir(cover_dir) else []
        if files:
            arts = [np.asarray(Image.open(os.path.join(cover_dir, f)).convert("RGB").resize((ART_SIZE, ART_SIZE)))
                    for f in files]
            names = [os.path.splitext(f)[0] for f in files]
        else:
            arts = [_generated_cover(rng) for _ in range(5)]
            names = [f"Test Track {i + 1}" for i in range(5)]
        self.tracks = [(f"fake{i}", n, "Fake Artist", a, int(rng.uniform(*track_seconds) * 1000))
                       for i, (n, a) in enumerate(zip(names, arts))]
        self.i = 0

    def start(self):
        self._load(0)
        threading.Thread(target=self._loop, daemon=True).start()

    def _load(self, i, playing=True):
        self.i = i % len(self.tracks)
        tid, title, artist, art, dur = self.tracks[self.i]
        self._set(NowPlaying(tid, title, artist, art, dur, 0, playing, time.monotonic()))

    def _loop(self):                       # auto-advance like a real queue
        while True:
            s = self.snapshot()
            if s and s.is_playing and s.progress_now() >= s.duration_ms:
                self._load(self.i + 1)
            time.sleep(0.2)

    def handle(self, event):
        s = self.snapshot()
        now = time.monotonic()
        if event == "next":
            self._load(self.i + 1)
        elif event == "toggle" and s:
            # freeze progress at its current value and flip the flag
            self._set(replace(s, progress_ms=int(s.progress_now()), is_playing=not s.is_playing, fetched_at=now))
        elif event == "seek" and s:
            self._set(replace(s, progress_ms=int(min(s.progress_now() + 15000, s.duration_ms - 500)), fetched_at=now))


def _generated_cover(rng, n=ART_SIZE):
    y, x = np.mgrid[0:n, 0:n] / n
    c1, c2, c3 = rng.integers(0, 256, (3, 3))
    img = c1 * (1 - y)[..., None] + c2 * y[..., None]
    blob = np.hypot(x - rng.uniform(0.2, 0.8), y - rng.uniform(0.2, 0.8)) < rng.uniform(0.12, 0.3)
    img[blob] = c3
    img[((x * rng.integers(3, 12)) % 1) < 0.15] *= 0.4
    return img.clip(0, 255).astype(np.uint8)
