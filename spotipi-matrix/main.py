"""
    python main.py --fake                   # offline: generated/local covers, keyboard controls
    python main.py                          # real Spotify (needs SPOTIPY_* env vars)
    python main.py --sim                    # force the window even on the Pi
    python main.py --layout framed          # start in a specific layout (default: full)

Layouts live in layouts.py (L toggles them in the simulator).

The YOUR-TURN functions below are the parts Edison is writing himself:
the dissolve transition and the k-means accent color.
"""
import argparse
import time

import numpy as np

from display import open_display
from layouts import LAYOUTS
from player import FakePlayer, SpotifyPlayer

FPS = 60
TRANSITION_SECONDS = 0.9


def pick_accent(art):
    """TODO: Placeholder: always cyan."""
    return np.array([0, 230, 255], np.uint8)


def transition(old, new, t, rng):
    """TODO: old/new: (64,64,3) uint8 frames, t: 0 -> 1.
    Return the frame to show. Placeholder: hard cut at the halfway point."""
    return old if t < 0.5 else new


def draw_idle(frame, t):
    """Nothing playing. Placeholder: a slow breathing dot. Clock + pixel rain later."""
    v = int(40 + 40 * np.sin(t * 1.5))
    frame[31:33, 31:33] = (0, v, v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="offline player, no Spotify")
    ap.add_argument("--sim", action="store_true", help="force the simulator window")
    ap.add_argument("--layout", choices=[L.name for L in LAYOUTS], default=LAYOUTS[0].name)
    ap.add_argument("--headless-login", action="store_true", help="print login URL instead of opening a browser")
    args = ap.parse_args()

    disp = open_display(force_sim=args.sim)
    player = FakePlayer() if args.fake else SpotifyPlayer(headless=args.headless_login)
    player.start()

    layouts = [L() for L in LAYOUTS]
    li = [L.name for L in layouts].index(args.layout)
    rng = np.random.default_rng()
    cur_id, accent = None, pick_accent(None)
    prev_frame = np.zeros((64, 64, 3), np.uint8)
    trans_start = trans_from = None

    last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            dt, last = now - last, now

            for ev in disp.events():
                if ev == "quit":
                    return
                if ev == "layout":
                    li = (li + 1) % len(layouts)
                    print("layout:", layouts[li].name)
                player.handle(ev)

            np_ = player.snapshot()                       # one consistent snapshot per frame
            frame = np.zeros((64, 64, 3), np.uint8)
            playing = np_ is not None and np_.is_playing
            for lay in layouts:                           # keep every disc spinning so a switch is seamless
                lay.update(dt, playing)

            if np_ is None:
                draw_idle(frame, now)
            else:
                if np_.track_id != cur_id:                # track changed: per-track work happens here, once
                    cur_id = np_.track_id
                    accent = pick_accent(np_.art)
                    for lay in layouts:
                        lay.prepare(np_.art, accent)
                    trans_start, trans_from = now, prev_frame.copy()
                layouts[li].draw(frame, np_, accent)

            if trans_start is not None:
                t = (now - trans_start) / TRANSITION_SECONDS
                if t >= 1:
                    trans_start = None
                else:
                    frame = transition(trans_from, frame, t, rng)

            disp.show(frame)
            prev_frame = frame
            time.sleep(max(0, 1 / FPS - (time.monotonic() - now)))
    finally:
        disp.close()


if __name__ == "__main__":
    main()
