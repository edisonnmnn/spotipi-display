"""
LED matrix simulator: preview a 64x64 frame on your laptop as if it were
on the panel (round dots, dark gaps, slight glow). Use it to develop the
dissolve transition before the hardware arrives.

    from ledsim import led_upscale, save_gif
    big = led_upscale(frame)              # (64*scale, 64*scale, 3) uint8
    save_gif([frame1, frame2, ...], "out.gif", fps=30)

On the Pi you skip this and copy frames into the PioMatter framebuffer.
"""
import numpy as np
from PIL import Image


def _dot_mask(scale, radius=0.42):
    c = (scale - 1) / 2.0
    y, x = np.mgrid[0:scale, 0:scale]
    d = np.hypot(x - c, y - c) / scale
    core = np.clip((radius - d) / 0.06, 0, 1)        # soft-edged dot
    glow = np.exp(-(d / 0.35) ** 2) * 0.18            # faint bleed into gap
    return np.maximum(core, glow).astype(np.float32)


def led_upscale(frame, scale=10):
    """frame: (H, W, 3) uint8 -> (H*scale, W*scale, 3) uint8 LED-looking image."""
    f = frame.astype(np.float32)
    big = np.repeat(np.repeat(f, scale, axis=0), scale, axis=1)
    h, w = frame.shape[:2]
    mask = np.tile(_dot_mask(scale), (h, w))[..., None]
    off = np.array([10, 10, 12], np.float32)          # unlit LED isn't pure black
    out = big * mask + off * (1 - mask) * 0.6
    return np.clip(out, 0, 255).astype(np.uint8)


def save_gif(frames, path, fps=30, scale=8):
    imgs = [Image.fromarray(led_upscale(f, scale)) for f in frames]
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=int(1000 / fps), loop=0, optimize=False)
