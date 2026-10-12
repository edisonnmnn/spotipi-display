# spotify-matrix

See `CLAUDE.md` for the full design context.

Now-playing display for a 64x64 HUB75 LED matrix on a Raspberry Pi 5.
Develops entirely on a laptop; the same code drives the real panel on the Pi.

## Laptop

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install numpy pillow pygame spotipy requests

python main.py --fake          # offline, no Spotify needed
```

Keys: `SPACE` play/pause · `N` next · `RIGHT` +15s · `L` layout (full / framed) · `Q` quit
Sim-only: `B` brightness · `D` diffuser · `G` panel seam · `S` screenshot · `R` record GIF (saved to `captures/`)

Put real album covers (`.jpg`/`.png`) in `covers/` and `--fake` cycles through them.

## Real Spotify (laptop first, easiest)

1. developer.spotify.com/dashboard → Create app → Web API.
   Redirect URI: `http://127.0.0.1:8888/callback` (must be 127.0.0.1, not localhost).
2. ```bash
   export SPOTIPY_CLIENT_ID=...
   export SPOTIPY_CLIENT_SECRET=...
   export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
   python main.py
   ```
3. A browser opens, you log in, and a token is saved in `.spotify_cache`.
   Copy that file to the Pi later and it won't need to log in again.
   (Keep it and your secret out of git.)

## Pi 5

```bash
pip install numpy pillow spotipy requests Adafruit-Blinka-Raspberry-Pi5-Piomatter
python main.py            # auto-detects PioMatter and uses the panel
```
Hardware: two 64x32 panels (3mm pitch) stacked into 64x64, chained with the
ribbon cable, both powered from the Bonnet's terminal block. No soldering.
Needs the PIO udev rule from Adafruit's guide. Panel settings are at the top
of `display.py`. If it says "Failed to open PIO device", check power.

## Files

| file | what |
|---|---|
| `main.py` | render loop + the YOUR-TURN functions (accent, transition) |
| `layouts.py` | the two layouts: `full` and `framed` |
| `display.py` | `SimDisplay` (pygame) / `MatrixDisplay` (PioMatter), same interface |
| `player.py` | `SpotifyPlayer` (polling thread) / `FakePlayer` (offline) |
| `disc.py` | spinning vinyl |
| `ledsim.py`, `preview_disc.py` | render frames to an LED-look GIF |

Note: real LEDs aren't a monitor. Dim colors crush toward black and the panel
is much brighter, so expect to retune colors once the hardware arrives.
