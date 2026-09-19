"""Recolour a suit of armour without touching the metal, the straps or the skin.

usage: tint_armor.py OUT_DIR HUE FILE.png ...        HUE in degrees, 0 = red

WHY NOT A FLAT HUE SHIFT. Rotating every pixel's hue turns the gold buckles green
and the gunmetal mint. What reads as "the armour" is the SATURATED PLATING; the rest
of the sheet is near-grey metal, dark rubber and flesh, and all of it has to survive.

So the mask is built from saturation and value, in HSV:
  - a pixel with almost no saturation is metal, rubber or dirt        -> untouched
  - a pixel that is nearly black carries the shading                  -> untouched
  - what is left is the plating, and only its HUE moves; saturation
    and value are kept exactly, so every scratch, edge wear and
    baked highlight stays where the artist put it

The mask is feathered rather than hard, so a plate's edge fades into the metal
around it instead of leaving a cut line a pixel wide.
"""
import os, sys
import numpy as np
from PIL import Image

OUT = sys.argv[1]
HUE = float(sys.argv[2]) / 360.0
FILES = sys.argv[3:]
os.makedirs(OUT, exist_ok=True)

# Below these a pixel is not plating. Feathered over the next stretch so the
# transition is a gradient and not a staircase.
S_MIN, S_FULL = 0.22, 0.38
V_MIN, V_FULL = 0.10, 0.22
# how far round the wheel from the plating's own hue still counts as plating
H_NEAR, H_FAR = 0.055, 0.115        # about 20 and 41 degrees


def rgb_to_hsv(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a[..., :3].max(-1)
    mn = a[..., :3].min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm = m & (mx == r)
    gm = m & (mx == g)
    bm = m & (mx == b)
    h[rm] = ((g[rm] - b[rm]) / d[rm]) % 6
    h[gm] = ((b[gm] - r[gm]) / d[gm]) + 2
    h[bm] = ((r[bm] - g[bm]) / d[bm]) + 4
    h = h / 6.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
    return h, s, mx


def hsv_to_rgb(h, s, v):
    i = np.floor(h * 6.0)
    f = h * 6.0 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = (i % 6).astype(int)
    out = np.zeros(h.shape + (3,), np.float32)
    for k, (a, b, c) in enumerate(((v, t, p), (q, v, p), (p, v, t),
                                   (p, q, v), (t, p, v), (v, p, q))):
        m = i == k
        out[m] = np.stack([a, b, c], -1)[m]
    return out


def ramp(x, lo, hi):
    return np.clip((x - lo) / max(hi - lo, 1e-6), 0.0, 1.0)


for f in FILES:
    im = Image.open(f).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255.0
    h, s, v = rgb_to_hsv(a)

    # WHICH HUE IS THE PLATING. Saturation and value alone matched 80-99% of these
    # sheets -- the bare forearm skin with it -- so the armour would have taken his
    # arms green. The plating is the DOMINANT SATURATED HUE, so it is found here,
    # per texture, from a saturation-weighted histogram: no per-body constant, and
    # it works the same on a red suit and a green one.
    strong = (s > 0.30) & (v > 0.15)
    if strong.sum() < 64:
        print("  %-46s no plating found, left alone" % os.path.basename(f))
        Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(os.path.join(OUT, os.path.basename(f)))
        continue
    hist, edges = np.histogram(h[strong], bins=72, range=(0.0, 1.0), weights=s[strong])
    src_hue = (edges[int(np.argmax(hist))] + edges[int(np.argmax(hist)) + 1]) / 2.0

    # distance round the colour wheel, feathered: a plate's edge fades into the
    # metal beside it instead of leaving a one-pixel cut line.
    dh = np.abs(h - src_hue)
    dh = np.minimum(dh, 1.0 - dh)
    mask = ramp(s, S_MIN, S_FULL) * ramp(v, V_MIN, V_FULL) * (1.0 - ramp(dh, H_NEAR, H_FAR))

    # only the hue moves; saturation and value are the artist's and stay
    nh = np.where(mask > 0, HUE, h)
    rgb = hsv_to_rgb(nh, s, v)
    blended = a[..., :3] * (1 - mask[..., None]) + rgb * mask[..., None]

    out = np.concatenate([blended, a[..., 3:4]], -1)
    dst = os.path.join(OUT, os.path.basename(f))
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst)
    print("  %-46s plating %5.1f%%  (its hue was %3.0f deg)"
          % (os.path.basename(f), 100.0 * (mask > 0.5).mean(), src_hue * 360.0))
