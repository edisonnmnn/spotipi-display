"""
Renders a GIF of the disc playing -> paused (spin-down) -> playing again,
as it would look on a 64x64 LED matrix.

    python preview_disc.py                 # uses a synthetic test cover
    python preview_disc.py my_cover.jpg    # try a real album cover
"""
import sys
import numpy as np
from PIL import Image
from disc import Disc, paste
from ledsim import save_gif


def test_cover(n=640):
    y, x = np.mgrid[0:n, 0:n] / n
    img = np.zeros((n, n, 3), np.float32)
    img[..., 0] = 200 + 55 * x                 # magenta -> pink gradient
    img[..., 1] = 30 + 60 * y
    img[..., 2] = 160 - 100 * y
    stripes = ((x + y) * 8 % 1) < 0.5
    img[stripes] *= 0.55
    sun = np.hypot(x - 0.3, y - 0.3) < 0.22    # off-center blob so rotation shows
    img[sun] = (255, 210, 60)
    return img.clip(0, 255).astype(np.uint8)


def main():
    art = (np.asarray(Image.open(sys.argv[1]).convert("RGB"))
           if len(sys.argv) > 1 else test_cover())
    accent = np.array([0, 230, 255])

    disc = Disc(size=40)
    disc.set_art(art)
    disc.set_accent(accent)

    fps, frames = 20, []
    # (seconds, playing): play, pause, play
    timeline = [(3.0, True), (2.5, False), (2.0, True)]
    t_song, dur = 70.0, 200.0
    for secs, playing in timeline:
        disc.playing = playing
        for _ in range(int(secs * fps)):
            dt = 1 / fps
            disc.update(dt)
            if playing:
                t_song += dt
            frame = np.zeros((64, 64, 3), np.uint8)
            rgb, alpha = disc.render()
            paste(frame, rgb, alpha, 12, 4)

            # simple progress bar placeholder (yours to restyle)
            filled = t_song / dur * 60
            frame[58:60, 2:62] = (25, 25, 30)
            full = int(filled)
            frame[58:60, 2:2 + full] = accent
            frac = filled - full                       # sub-pixel: dim leading LED
            frame[58:60, 2 + full] = (accent * frac).astype(np.uint8)
            frames.append(frame)

    save_gif(frames, "disc_preview.gif", fps=fps, scale=6)
    print(f"wrote disc_preview.gif ({len(frames)} frames)")


if __name__ == "__main__":
    main()
