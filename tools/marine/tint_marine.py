"""The Classic marine's armour recoloured: its plating is RED in the source, so red IS the breath look, and green /
blue are made from it. Only the red plating turns. Skin, the neck patch, grey metal, leather and the gold
buckles keep their colour.

usage: tint_marine.py SRC.png OUT_DIR NAME
Writes NAME_green.png, NAME_blue.png, NAME_red.png (a copy of the source) and NAME_mask.png (white = tinted).

THE PLATING MASK. Red hue (<= 14 or >= 340 degrees) at saturation >= 0.45 is plating for sure. The pale
orange highlights painted on the plating (hue up to ~28) overlap skin in colour, so they count only when they
sit next to sure plating: the sure mask is grown by a few pixels and a highlight must fall inside it. Skin
areas are large and away from plating, so they stay out.

THE HUE. Green and blue take the Quake torso skins' own hue (vrtorso_green / vrtorso_blue), as tint_strong.py
does for the Slayer gauntlets, so the whole body reads as one armour colour. Saturation and brightness are
kept, so the paint wear and shading survive; a small lift (LIFT) keeps a dark green from going muddy.
"""
import sys, os, colorsys
import numpy as np
from PIL import Image, ImageFilter

SRC, OUT, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
LIFT = 1.15
GROW = 6
os.makedirs(OUT, exist_ok=True)
M = "E:/DOOMWork/RS_VRBody/models/"


def torso_hue(path):
    a = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3)[::53].astype(float) / 255
    hsv = np.array([colorsys.rgb_to_hsv(*p) for p in a]); hsv = hsv[hsv[:, 1] > 0.15]
    return (np.angle(np.mean(np.exp(2j * np.pi * hsv[:, 0]))) / (2 * np.pi)) % 1.0


img = Image.open(SRC).convert("RGB")
a = np.asarray(img).astype(np.float32) / 255.0
r, g, b = a[..., 0], a[..., 1], a[..., 2]
mx = a.max(-1); mn = a.min(-1); d = mx - mn; v = mx
s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
h = np.zeros_like(mx); m = d > 1e-6
rc = m & (mx == r); gc = m & ~rc & (mx == g); bc = m & ~rc & ~gc
h[rc] = ((g - b)[rc] / d[rc]) % 6.0; h[gc] = ((b - r)[gc] / d[gc]) + 2.0; h[bc] = ((r - g)[bc] / d[bc]) + 4.0
hd = h / 6.0 * 360.0

def morph(mask, size, op):
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(op(size))) > 0


# THIRD PASS. Sheet 1: lime, green specks on skin, orange wear left on the plate. Sheet 2 (closing the red into
# an area) left the plate full of orange holes. So the logic is turned round: find the SKIN, not the plate.
#   - skin is large pale warm patches (hue 8..40, saturation 0.12..0.5, bright). A big opening on a quarter-size
#     mask keeps only the large patches, then grows them a little: that is the SKIN REGION, and it swallows the
#     red blemishes painted on the skin;
#   - everything warm (red through orange, saturation >= 0.18) OUTSIDE the skin region is plate or paint wear on
#     it, and turns. Grey metal (low saturation) and gold buckles (hue above 45) are not warm and stay.
def morph_small(mask, size, op, factor=4):
    H, W = mask.shape
    small = Image.fromarray((mask * 255).astype(np.uint8)).resize((W // factor, H // factor), Image.BILINEAR)
    small = small.point(lambda x: 255 if x >= 128 else 0).filter(op(size))
    return np.asarray(small.resize((W, H), Image.NEAREST)) > 0


# Sheet 3: the plate came out clean, but the brown/grey gauntlet metal and the gold buckles turned too (warm
# hue), and a thin red line was left along every skin edge (the grown skin region covered the plate's rim). So:
#   - wear counts only NEAR red plate (red grown ~60 px), and gold (hue above 38) is never warm;
#   - red itself is plate unless it sits in the skin CORE (the region shrunk back past its growth), so the rim
#     turns and the red blemishes painted deep in the skin stay.
skin_like = (hd >= 8) & (hd <= 40) & (s >= 0.12) & (s <= 0.5) & (v >= 0.5)
skin_region = morph_small(morph_small(skin_like, 9, ImageFilter.MinFilter), 15, ImageFilter.MaxFilter)
skin_core = morph_small(skin_region, 23, ImageFilter.MinFilter)
sure = ((hd <= 14) | (hd >= 340)) & (s >= 0.45) & (v > 0.08)
near_red = morph_small(sure & ~skin_region, 15, ImageFilter.MaxFilter)
warm = ((hd <= 38) | (hd >= 330)) & (s >= 0.18) & (v > 0.06)
plating = (sure & ~skin_core) | (warm & ~skin_region & near_red)
highlight = plating & ~sure
say = "%s: plating %.1f%% (red %.1f%%, wear %.1f%%), skin region %.1f%%" % (NAME, 100 * plating.mean(), 100 * (plating & sure).mean(), 100 * highlight.mean(), 100 * skin_region.mean())


def hsv2rgb(h, s, v):
    i = np.floor(h * 6.0).astype(np.int32) % 6
    f = h * 6.0 - np.floor(h * 6.0)
    p = v * (1 - s); q = v * (1 - f * s); t = v * (1 - (1 - f) * s)
    return np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]), np.choose(i, [p, p, t, v, v, q])], -1)


def torso_sat(path):
    """Median saturation and value of the Quake torso skin's coloured pixels: the armour's own strength."""
    q = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3)[::17].astype(float) / 255
    qmx, qmn = q.max(1), q.min(1)
    qs = np.where(qmx > 1e-6, (qmx - qmn) / np.maximum(qmx, 1e-6), 0)
    sel = qs > 0.15
    # value at the 75th percentile: the Quake skin is mostly deep shadow with bright plates, and its median (0.22)
    # made the marine's plates far darker than the torso reads (sheet 3)
    return float(np.median(qs[sel])), float(np.percentile(qmx[sel], 75))


LIFT = 1.25                                            # tint_strong.py's lift for the Slayer gauntlets (dim rooms)
plate_s = float(np.median(s[plating & sure])) if (plating & sure).any() else 0.8
plate_v = float(np.median(v[plating & sure])) if (plating & sure).any() else 0.7
for name, path in (("green", M + "vrtorso_green.png"), ("blue", M + "vrtorso_blue.png")):
    hue = torso_hue(path)
    ts, tv = torso_sat(path)
    ks = ts / plate_s                                  # this texture's plate strength to the Quake torso's
    kv = min(1.0, tv / plate_v * LIFT)                 # and its brightness, lifted like the gauntlets
    say += "\n  %s: hue %.0f deg; torso sat %.2f value %.2f; plate sat %.2f value %.2f -> sat x%.2f value x%.2f" % (
        name, hue * 360, ts, tv, plate_s, plate_v, ks, kv)
    out = np.where(plating[..., None], hsv2rgb(np.full_like(h, hue), np.clip(s * ks, 0, 1), np.clip(v * kv, 0, 1)), a)
    Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, "%s_green.png" % NAME if name == "green" else "%s_blue.png" % NAME))
img.save(os.path.join(OUT, "%s_red.png" % NAME))
Image.fromarray((plating * 255).astype(np.uint8)).save(os.path.join(OUT, "%s_mask.png" % NAME))
print(say)
