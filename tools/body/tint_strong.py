"""Gauntlet armour tints that read like the torso: every METAL pixel takes the torso's hue at a strong saturation,
not only the near-grey ones, with a small brightness lift on what it tints so the colour carries in a dim room.
Skin, leather and the red status lights are protected, as before.
usage: tint_strong.py SRC.png OUT_DIR NAME SAT LIFT"""
import sys, os, colorsys
import numpy as np
from PIL import Image
SRC, OUT, NAME, SAT, LIFT = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
os.makedirs(OUT, exist_ok=True)
def torso_hue(path):
    a = np.asarray(Image.open(path).convert('RGB')).reshape(-1, 3)[::53].astype(float) / 255
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in a]); hsv = hsv[hsv[:, 1] > 0.15]
    return (np.angle(np.mean(np.exp(2j * np.pi * hsv[:, 0]))) / (2 * np.pi)) % 1.0
M = "E:/DOOMWork/RS_VRBody/models/"
TINTS = {'green': torso_hue(M + "vrtorso_green.png"), 'blue': torso_hue(M + "vrtorso_blue.png"), 'red': torso_hue(M + "vrtorso_red.png")}
a = np.asarray(Image.open(SRC).convert('RGB')).astype(np.float32) / 255.0
r, g, b = a[..., 0], a[..., 1], a[..., 2]
mx = a.max(-1); mn = a.min(-1); d = mx - mn; v = mx
s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
h = np.zeros_like(mx); m = d > 1e-6
rc = m & (mx == r); gc = m & ~rc & (mx == g); bc = m & ~rc & ~gc
h[rc] = ((g - b)[rc] / d[rc]) % 6.0; h[gc] = ((b - r)[gc] / d[gc]) + 2.0; h[bc] = ((r - g)[bc] / d[bc]) + 4.0
hd = h / 6.0 * 360.0
skin_leather = (hd >= 8) & (hd <= 50) & (s > 0.22)
red_lights = ((hd < 12) | (hd > 340)) & (s > 0.55) & (v > 0.35)
protect = skin_leather | red_lights
metal = ~protect & (v > 0.04)
def hsv2rgb(h, s, v):
    i = np.floor(h * 6.0).astype(np.int32) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s)
    return np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]), np.choose(i, [p, p, t, v, v, q])], -1)
for name, hue in TINTS.items():
    nh = np.where(metal, hue, h / 6.0)
    ns = np.where(metal, np.maximum(s, SAT), s)
    nv = np.where(metal, np.clip(v * LIFT, 0, 1), v)
    out = np.where(metal[..., None], hsv2rgb(nh, ns, nv), a)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "%s_%s.png" % (NAME, name)))
print("wrote %s: metal %.0f%% of pixels, protected %.0f%%" % (NAME, 100 * metal.mean(), 100 * protect.mean()))
