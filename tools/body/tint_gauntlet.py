"""Armour tints for the Slayer gauntlet textures (idea 7), the same spirit as RS_VRBody's torso recolours.

usage: tint_gauntlet.py SRC.png OUT_DIR NAME

Brightness (HSV value) is always kept, so wear, grime and panel lines survive.
  - Skin and leather (orange/brown hues, saturated) are left alone.
  - The red status lights (saturated red, bright) are left alone.
  - Pixels that are ALREADY green (the left gauntlet's plates) get their hue replaced.
  - Grey/black metal gets a soft colourise (target hue at ARMOUR_SAT saturation), faded in by how
    grey the pixel is, so near-neutral steel takes the tint and anything already coloured does not.
Writes NAME_green.png / NAME_blue.png / NAME_red.png at full resolution, plus NAME_preview.png:
original + the three tints side by side at 512 px.
"""
import sys, os
import numpy as np
from PIL import Image

SRC, OUT, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
TINTS = {'green': 110.0 / 360, 'blue': 215.0 / 360, 'red': 0.0}
ARMOUR_SAT = 0.45

img = Image.open(SRC).convert('RGB')
a = np.asarray(img).astype(np.float32) / 255.0
r, g, b = a[..., 0], a[..., 1], a[..., 2]
mx = a.max(-1); mn = a.min(-1); d = mx - mn
v = mx
s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
h = np.zeros_like(mx)
m = d > 1e-6
rc = m & (mx == r); gc = m & ~rc & (mx == g); bc = m & ~rc & ~gc
h[rc] = ((g - b)[rc] / d[rc]) % 6.0
h[gc] = ((b - r)[gc] / d[gc]) + 2.0
h[bc] = ((r - g)[bc] / d[bc]) + 4.0
h = h / 6.0
hd = h * 360.0

skin_leather = (hd >= 8) & (hd <= 50) & (s > 0.22)
red_lights = ((hd < 12) | (hd > 340)) & (s > 0.55) & (v > 0.35)
already_green = (hd >= 65) & (hd <= 170) & (s > 0.18)
greyness = np.clip((0.30 - s) / 0.30, 0.0, 1.0) * (v > 0.06)          # 1 = fully neutral metal
protect = skin_leather | red_lights

def hsv2rgb(h, s, v):
    i = np.floor(h * 6.0).astype(np.int32) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s)
    rr = np.choose(i, [v, q, p, p, t, v]); gg = np.choose(i, [t, v, v, q, p, p]); bb = np.choose(i, [p, p, t, v, v, q])
    return np.stack([rr, gg, bb], -1)

previews = [img.resize((512, 512))]
for name, hue in TINTS.items():
    nh = np.where(already_green, hue, np.where(greyness > 0, hue, h))
    ns = np.where(already_green, np.clip(s * 1.2, 0, 1), np.where(greyness > 0, s + (ARMOUR_SAT - s) * greyness, s))
    out = hsv2rgb(nh, ns, v)
    out = np.where(protect[..., None], a, out)
    o = Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))
    o.save(os.path.join(OUT, f'{NAME}_{name}.png'))
    previews.append(o.resize((512, 512)))
strip = Image.new('RGB', (512 * len(previews), 512))
for i, p in enumerate(previews): strip.paste(p, (512 * i, 0))
strip.save(os.path.join(OUT, f'{NAME}_preview.png'))
print('protected %.1f%%  already-green %.1f%%  metal(greyness>0) %.1f%%' % (
    100 * protect.mean(), 100 * already_green.mean(), 100 * (greyness > 0).mean()))
