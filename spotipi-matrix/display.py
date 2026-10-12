"""
One interface, two backends:

    disp = open_display()          # picks the real matrix on the Pi, a window anywhere else
    disp.show(frame)               # frame: (64, 64, 3) uint8
    for ev in disp.events(): ...   # 'quit', 'toggle', 'next', 'seek', 'layout' (sim keys for now;
                                   # buttons/Arduino on the Pi later emit the same events)

Your render code never knows which one it's talking to, so everything you
write on your laptop runs unchanged on the Pi.
"""
import numpy as np

W = H = 64
N_ADDR_LINES = 4      # two stacked 64x32 panels
SERPENTINE = True     # try False if the halves come out wrong


class SimDisplay:
    """pygame window that mimics the LED panel.

    Player keys:  SPACE play/pause · N next track · RIGHT seek +15s · L layout · Q/ESC quit
    Sim keys:     B brightness · D diffuser on/off · G panel seam on/off
                  S screenshot (PNG) · R start/stop recording (GIF)

    How it fakes LEDs: each logical pixel becomes a scale x scale block, multiplied
    by a precomputed round 'dot' mask (bright core, dark gap, faint bleed). The
    diffuser mode blurs the result, which is roughly what smoked acrylic does.
    """

    def __init__(self, scale=10, title="matrix sim"):
        import pygame
        self.pg = pygame
        pygame.display.init()          # display only; skips audio init
        self.scale = scale
        self.screen = pygame.display.set_mode((W * scale, H * scale))
        self.title = title
        self.brightness = 1.0
        self.diffuser = False
        self.seam = True               # hardware is two 64x32 panels: gap after row 31
        self.recording = None          # list of raw frames while recording
        self._last_frame = np.zeros((H, W, 3), np.uint8)
        self._fps_t, self._fps_n = 0.0, 0

        # precompute the dot mask once: round LEDs, dark gaps, slight bleed
        c = (scale - 1) / 2.0
        y, x = np.mgrid[0:scale, 0:scale]
        d = np.hypot(x - c, y - c) / scale
        dot = np.maximum(np.clip((0.42 - d) / 0.06, 0, 1), np.exp(-(d / 0.35) ** 2) * 0.18)
        # The per-frame work is done by pygame in C (scale + multiply-blend), because
        # doing a 640x640 float multiply in numpy every frame was too slow for 60fps.
        # Masks are built once here in numpy and turned into surfaces.
        size = (W * scale, H * scale)
        sharp = np.tile(dot, (H, W))                            # 1 = LED core, ~0 = gap
        soft = 0.8 + 0.2 * sharp                                # diffuser: texture mostly gone
        self._mask_sharp = self._gray_surface(sharp)
        self._mask_soft = self._gray_surface(soft)
        self._unlit = self._gray_surface((1 - sharp) * 6 / 255)   # unlit LEDs aren't pure black
        self._size = size

    def _gray_surface(self, a):
        """(H*s, W*s) array in 0..1 -> RGB surface (surfarray is x-major, hence .T)."""
        g = (np.clip(a, 0, 1) * 255).astype(np.uint8).T
        return self.pg.surfarray.make_surface(np.stack([g, g, g], -1))

    def _compose(self, frame):
        pg = self.pg
        base = pg.surfarray.make_surface(np.ascontiguousarray(frame.transpose(1, 0, 2)))
        if self.diffuser:   # acrylic smears light between neighbours ~ smooth upscale
            surf = pg.transform.smoothscale(base, self._size)
            surf.blit(self._mask_soft, (0, 0), special_flags=pg.BLEND_RGB_MULT)
        else:               # nearest upscale, then punch round LEDs out of each block
            surf = pg.transform.scale(base, self._size)
            surf.blit(self._mask_sharp, (0, 0), special_flags=pg.BLEND_RGB_MULT)
        surf.blit(self._unlit, (0, 0), special_flags=pg.BLEND_RGB_ADD)
        if self.brightness < 1:
            b = int(255 * self.brightness)
            surf.fill((b, b, b), special_flags=pg.BLEND_RGB_MULT)
        if self.seam:       # thin dark line between the two 64x32 panels
            y = (H // 2) * self.scale
            surf.fill((40, 40, 40), pg.Rect(0, y - 1, self._size[0], 2), special_flags=pg.BLEND_RGB_MULT)
        return surf

    def render(self, frame):
        """Logical (64,64,3) frame -> image of what the panel would look like (H*s, W*s, 3)."""
        return self.pg.surfarray.array3d(self._compose(frame)).transpose(1, 0, 2)

    def show(self, frame):
        import time
        self._last_frame = frame
        if self.recording is not None:
            self.recording.append(frame.copy())
        self.screen.blit(self._compose(frame), (0, 0))
        self.pg.display.flip()

        self._fps_n += 1                                         # fps + status in the title bar
        now = time.monotonic()
        if now - self._fps_t >= 0.5:
            fps = self._fps_n / (now - self._fps_t) if self._fps_t else 0
            flags = " ".join(f for f, on in [("REC", self.recording is not None),
                                             ("diffuser", self.diffuser), ("seam", self.seam)] if on)
            self.pg.display.set_caption(f"{self.title}  {fps:4.0f} fps  {flags}")
            self._fps_t, self._fps_n = now, 0

    def events(self):
        pg, out = self.pg, []
        for e in pg.event.get():
            if e.type == pg.QUIT:
                out.append("quit")
            elif e.type == pg.KEYDOWN:
                out.append({pg.K_ESCAPE: "quit", pg.K_q: "quit", pg.K_SPACE: "toggle",
                            pg.K_n: "next", pg.K_RIGHT: "seek", pg.K_l: "layout"}.get(e.key))
                self._sim_key(e.key)
        return [o for o in out if o]

    def _sim_key(self, key):
        """Keys that only affect the simulator itself, never the app."""
        import os
        import time
        from PIL import Image
        pg = self.pg
        if key == pg.K_b:
            self.brightness = {1.0: 0.5, 0.5: 0.2, 0.2: 1.0}[self.brightness]
        elif key == pg.K_d:
            self.diffuser = not self.diffuser
        elif key == pg.K_g:
            self.seam = not self.seam
        elif key == pg.K_s:
            os.makedirs("captures", exist_ok=True)
            path = time.strftime("captures/shot-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}.png"
            Image.fromarray(self.render(self._last_frame)).save(path)
            print("saved", path)
        elif key == pg.K_r:
            if self.recording is None:
                self.recording = []
            else:
                from ledsim import save_gif
                os.makedirs("captures", exist_ok=True)
                path = time.strftime("captures/rec-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}.gif"
                save_gif(self.recording[::2], path, fps=30)       # every 2nd frame keeps GIFs small
                print("saved", path, f"({len(self.recording)} frames)")
                self.recording = None

    def close(self):
        self.pg.quit()


class MatrixDisplay:
    """The real 64x64 panel via PioMatter (Pi 5 + Adafruit RGB Matrix Bonnet)."""

    def __init__(self, brightness=0.6):
        import adafruit_blinka_raspberry_pi5_piomatter as piomatter
        # Two stacked 64x32 panels = 64x64 with 4 address lines (no solder jumper).
        # If the bottom half shows up flipped or swapped, toggle SERPENTINE.
        # (A single 64x64 panel would instead need n_addr_lines=5 + the E jumper.)
        geometry = piomatter.Geometry(width=W, height=H, n_addr_lines=N_ADDR_LINES,
                                      serpentine=SERPENTINE,
                                      rotation=piomatter.Orientation.Normal)
        self.fb = np.zeros((H, W, 3), np.uint8)
        self.matrix = piomatter.PioMatter(colorspace=piomatter.Colorspace.RGB888Packed,
                                          pinout=piomatter.Pinout.AdafruitMatrixBonnet,
                                          framebuffer=self.fb, geometry=geometry)
        self.matrix.brightness = brightness

    def show(self, frame):
        self.fb[:] = frame
        self.matrix.show()

    def events(self):
        return []          # later: buttons / Arduino serial go here

    def close(self):
        self.fb[:] = 0
        self.matrix.show()


def open_display(force_sim=False):
    if not force_sim:
        try:
            return MatrixDisplay()
        except ImportError:
            pass
    return SimDisplay()
