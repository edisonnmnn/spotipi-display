"""
Two switchable layouts. Press L in the simulator to toggle, or pick one with
`python main.py --layout full|framed`.

Each layout owns its own disc (they're different sizes) and does its expensive
work once per track in `prepare()`, so `draw()` stays cheap enough for 60fps.

    FullLayout    cover fills all 64x64; disc + progress bar float over a dark
                  scrim at the bottom so they stay readable on bright covers
    FramedLayout  44x44 cover; disc + bar underneath, aligned to the cover's
                  left and right edges
"""
import numpy as np
from PIL import Image

from disc import Disc, paste


def shrink(art, size):
    """Cover (any size) -> (size, size, 3) uint8. Once per track, never per frame."""
    return np.asarray(Image.fromarray(art).resize((size, size), Image.LANCZOS))


def progress_bar(frame, x, y, w, h, frac, accent):
    """Track + fill, with the leading LED dimmed by the fractional part so the
    bar creeps smoothly instead of jumping a whole LED at a time."""
    filled = frac * w
    full = int(filled)
    frame[y:y + h, x:x + w] = (25, 25, 30)
    frame[y:y + h, x:x + full] = accent
    if full < w:
        frame[y:y + h, x + full] = (accent * (filled - full)).astype(np.uint8)


class _Layout:
    name = ""
    DISC_SIZE = 16

    def __init__(self):
        self.disc = Disc(size=self.DISC_SIZE, label_r=0.5)

    def prepare(self, art, accent):
        """New track: per-track precompute."""
        self.disc.set_art(art)
        self.disc.set_accent(accent)

    def update(self, dt, playing):
        self.disc.playing = playing
        self.disc.update(dt)


class FullLayout(_Layout):
    name = "full"
    DISC_SIZE = 16
    DISC_X, DISC_Y = 3, 46
    BAR_X, BAR_Y, BAR_W, BAR_H = 22, 57, 39, 2
    SCRIM_START, SCRIM_LEN, SCRIM_MAX = 40, 14, 0.8   # fade begins at row 40, 80% dark by row 54

    def __init__(self):
        super().__init__()
        rows = np.arange(64)
        ramp = np.clip((rows - self.SCRIM_START) / self.SCRIM_LEN, 0, 1) * self.SCRIM_MAX
        self.scrim = (1 - ramp)[:, None, None].astype(np.float32)    # (64,1,1) broadcasts over x and rgb
        self.bg = np.zeros((64, 64, 3), np.uint8)

    def prepare(self, art, accent):
        super().prepare(art, accent)
        # bake the scrim into the background once per track
        self.bg = (shrink(art, 64).astype(np.float32) * self.scrim).astype(np.uint8)

    def draw(self, frame, np_, accent):
        frame[:] = self.bg
        rgb, alpha = self.disc.render()
        paste(frame, rgb, alpha, self.DISC_X, self.DISC_Y)
        progress_bar(frame, self.BAR_X, self.BAR_Y, self.BAR_W, self.BAR_H, np_.fraction(), accent)


class FramedLayout(_Layout):
    name = "framed"
    ART_X, ART_Y, ART_SIZE = 10, 1, 44                  # cover spans x 10..53
    DISC_SIZE = 12
    DISC_X, DISC_Y = 10, 48                             # flush with the cover's left edge
    BAR_X, BAR_W, BAR_H = 25, 29, 2                     # ends at x=53, flush with the right edge
    BAR_Y = DISC_Y + DISC_SIZE // 2 - BAR_H // 2        # vertically centered on the disc

    def __init__(self):
        super().__init__()
        self.art = np.zeros((self.ART_SIZE, self.ART_SIZE, 3), np.uint8)

    def prepare(self, art, accent):
        super().prepare(art, accent)
        self.art = shrink(art, self.ART_SIZE)

    def draw(self, frame, np_, accent):
        s = self.ART_SIZE
        frame[self.ART_Y:self.ART_Y + s, self.ART_X:self.ART_X + s] = self.art
        rgb, alpha = self.disc.render()
        paste(frame, rgb, alpha, self.DISC_X, self.DISC_Y)
        progress_bar(frame, self.BAR_X, self.BAR_Y, self.BAR_W, self.BAR_H, np_.fraction(), accent)


LAYOUTS = [FullLayout, FramedLayout]
