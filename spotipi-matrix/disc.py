"""
Spinning vinyl disc for a 64x64 LED matrix.

Usage:
    disc = Disc(size=32)
    disc.set_art(album_art_rgb)        # any HxWx3 uint8 array (Spotify gives 640x640)
    disc.set_accent((0, 255, 200))     # optional, e.g. your k-means color
    ...
    # every frame:
    disc.playing = state.is_playing
    disc.update(dt)
    rgb, alpha = disc.render()         # (size,size,3) uint8, (size,size) float 0..1
    paste(framebuffer, rgb, alpha, x, y)

How it works:
  * Everything is drawn per-pixel in polar coords (r, theta) with numpy,
    at `ss`x supersampling, then box-averaged down. That averaging is what
    keeps the circle edge and rotating label from shimmering at low res.
  * The groove sheen is STATIONARY (light reflecting off a real record
    doesn't rotate with it). Only the label and a rim marker rotate,
    so your eye reads "spinning" from those.
  * Spin-up/spin-down is an exponential approach to target speed, with a
    slower time constant for spin-down so pausing feels like a turntable.
"""
import numpy as np


class Disc:
    def __init__(self, size=32, ss=4, rpm=20.0, spin_up=0.35, spin_down=1.2,
                 label_r=0.42):
        self.size, self.ss = size, ss
        self.w_max = rpm * 2 * np.pi / 60.0      # rad/s
        self.spin_up, self.spin_down = spin_up, spin_down
        self.label_r = label_r

        n = size * ss
        c = (n - 1) / 2.0
        y, x = np.mgrid[0:n, 0:n].astype(np.float32)
        self.dx = (x - c) / (n / 2.0)            # -1..1
        self.dy = (y - c) / (n / 2.0)
        self.r = np.hypot(self.dx, self.dy)
        self.theta = np.arctan2(self.dy, self.dx)

        self.playing = False
        self.omega = 0.0
        self.phi = 0.0
        self.accent = np.array([0, 230, 255], np.float32)
        self.art = np.full((8, 8, 3), 80, np.float32)

        self._static = self._build_static()

    # ---------- setup ----------
    def set_art(self, art_rgb):
        self.art = np.asarray(art_rgb, np.float32)

    def set_accent(self, rgb):
        self.accent = np.asarray(rgb, np.float32)
        self._static = self._build_static()

    def _build_static(self):
        """Parts that never rotate: vinyl body, grooves, sheen, rim."""
        r, th = self.r, self.theta
        body = np.zeros(r.shape + (3,), np.float32)
        base = np.array([14, 14, 20], np.float32)
        body[:] = base

        groove_zone = (r > self.label_r + 0.04) & (r < 0.96)
        # concentric grooves: faint ring modulation
        rings = 0.5 + 0.5 * np.cos(r * 90.0)
        body += (groove_zone * rings * 10.0)[..., None]

        # stationary specular sheen, two opposite lobes like a real record
        glint_angle = -np.pi / 4
        d = np.angle(np.exp(1j * (th - glint_angle)))          # wrap to -pi..pi
        lobe = np.exp(-(d / 0.35) ** 2) + np.exp(-((np.abs(d) - np.pi) / 0.35) ** 2)
        sheen = groove_zone * lobe * (0.4 + 0.6 * r)
        body += sheen[..., None] * (0.35 * self.accent + 25.0)

        # rim
        rim = (r >= 0.93) & (r <= 1.0)
        body[rim] = base + 30.0
        return body

    # ---------- per frame ----------
    def update(self, dt):
        target = self.w_max if self.playing else 0.0
        tau = self.spin_up if target > self.omega else self.spin_down
        self.omega += (target - self.omega) * (1.0 - np.exp(-dt / tau))
        if abs(self.omega) < 1e-3 and not self.playing:
            self.omega = 0.0
        self.phi = (self.phi + self.omega * dt) % (2 * np.pi)

    def render(self):
        r = self.r
        img = self._static.copy()

        # rotating label: rotate sample coords by -phi, sample album art
        lab = r < self.label_r
        cp, sp = np.cos(-self.phi), np.sin(-self.phi)
        u = (self.dx * cp - self.dy * sp) / self.label_r      # -1..1 inside label
        v = (self.dx * sp + self.dy * cp) / self.label_r
        h, w = self.art.shape[:2]
        # sample the middle ~70% of the cover, label crops like a real one
        ax = np.clip(((u * 0.7 + 1) / 2 * (w - 1)).astype(np.int32), 0, w - 1)
        ay = np.clip(((v * 0.7 + 1) / 2 * (h - 1)).astype(np.int32), 0, h - 1)
        img[lab] = self.art[ay[lab], ax[lab]]

        # label ring in accent color
        ring = (r >= self.label_r - 0.03) & (r < self.label_r + 0.01)
        img[ring] = self.accent * 0.8

        # rotating marker on the rim so rotation reads even on a blurry label
        mth = np.arctan2(v, u)                                 # rotated angle
        d = np.angle(np.exp(1j * mth))
        marker = (np.abs(d) < 0.18) & (r > 0.80) & (r < 0.92)
        img[marker] = self.accent

        # spindle hole
        img[r < 0.06] = 0.0

        # downsample (box filter) -> anti-aliased
        s, n = self.ss, self.size
        img = img.reshape(n, s, n, s, 3).mean(axis=(1, 3))
        alpha = (r <= 1.0).astype(np.float32).reshape(n, s, n, s).mean(axis=(1, 3))
        return np.clip(img, 0, 255).astype(np.uint8), alpha


def paste(frame, rgb, alpha, x, y):
    """Alpha-blend rgb onto frame (HxWx3 uint8) at top-left (x, y)."""
    h, w = alpha.shape
    dst = frame[y:y + h, x:x + w].astype(np.float32)
    a = alpha[..., None]
    frame[y:y + h, x:x + w] = (rgb * a + dst * (1 - a)).astype(np.uint8)
