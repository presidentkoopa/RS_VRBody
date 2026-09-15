"""The RS hand's skin retoned to the Classic marine's arm skin, so hand and arm read as one person.

usage: retone_hand.py HAND_TEX MARINE_ARM_TEX OUT_PNG
Writes OUT_PNG (the retoned hand, a NEW file -- the RS hand's own texture is untouched), OUT_mask.png (white =
skin that was moved) and OUT_compare.png (hand before | after | a patch of the marine skin).

HOW. Reinhard colour transfer in CIE Lab: each skin pixel's L, a, b are moved from the hand skin's mean and
spread to the marine skin's, so the marine's tone, redness and contrast arrive and the hand's own shading and
detail stay. Only skin moves, blended by a soft mask, so nails and anything not skin-coloured keep theirs.

SKIN. Warm hue (5..45 degrees), saturation 0.12..0.7, not near black. On the marine arm texture only its big
skin patches count (the same large-patch test tint_marine.py uses), so red plate and brown metal never enter
the target statistics.
"""
import os, sys
import numpy as np
from PIL import Image, ImageFilter

HAND, ARM, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
stem = os.path.splitext(OUT)[0]


def srgb_to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab_to_srgb(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560], [0.0556434, -0.2040259, 1.0572252]])
    c = np.clip(xyz @ Mi.T, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def hsv(a):
    mx = a.max(-1); mn = a.min(-1); d = mx - mn
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0.0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    h = np.zeros_like(mx); m = d > 1e-6
    rc = m & (mx == r); gc = m & ~rc & (mx == g); bc = m & ~rc & ~gc
    h[rc] = ((g - b)[rc] / d[rc]) % 6.0; h[gc] = ((b - r)[gc] / d[gc]) + 2.0; h[bc] = ((r - g)[bc] / d[bc]) + 4.0
    return h * 60.0, s, mx


def skin_mask(a):
    h, s, v = hsv(a)
    return (h >= 5) & (h <= 45) & (s >= 0.12) & (s <= 0.7) & (v >= 0.2)


def big_patches(mask, factor=4):
    H, W = mask.shape
    im = Image.fromarray((mask * 255).astype(np.uint8)).resize((W // factor, H // factor), Image.BILINEAR)
    im = im.point(lambda x: 255 if x >= 128 else 0).filter(ImageFilter.MinFilter(9)).filter(ImageFilter.MaxFilter(9))
    return np.asarray(im.resize((W, H), Image.NEAREST)) > 0


hand = np.asarray(Image.open(HAND).convert("RGB")).astype(np.float64) / 255.0
arm = np.asarray(Image.open(ARM).convert("RGB")).astype(np.float64) / 255.0

# FIRST RUN WAS WRONG: the loose skin rule caught 61.7% of the arm texture (plate wear and brown metal are warm
# too), so the "marine skin" spread was 3.7x the hand's and the hand came out grainy and veiny; the patch shown
# was metal. The target now uses tint_marine.py's stricter skin rule (pale: saturation <= 0.5, bright) inside
# large patches only, the spread change is capped, and the patch shown is the densest skin block.
MAX_SPREAD = 1.3


def strict_skin(a):
    h, s, v = hsv(a)
    return (h >= 8) & (h <= 40) & (s >= 0.12) & (s <= 0.5) & (v >= 0.5)


arm_skin = strict_skin(arm) & big_patches(strict_skin(arm))
hand_skin = skin_mask(hand)
arm_lab = srgb_to_lab(arm[arm_skin][::7])
hand_lab_all = srgb_to_lab(hand)
hs = hand_lab_all[hand_skin][::7]
mu_h, sd_h = hs.mean(0), hs.std(0) + 1e-6
mu_a, sd_a = arm_lab.mean(0), arm_lab.std(0) + 1e-6
ratio = np.clip(sd_a / sd_h, 1.0 / MAX_SPREAD, MAX_SPREAD)
moved = (hand_lab_all - mu_h) * ratio + mu_a
print("spread ratio used (capped at %.1f): %s" % (MAX_SPREAD, ratio.round(2)))

soft = np.asarray(Image.fromarray((hand_skin * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))).astype(np.float64)[..., None] / 255.0
out = lab_to_srgb(moved) * soft + hand * (1 - soft)
Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)).save(OUT)
Image.fromarray((hand_skin * 255).astype(np.uint8)).save(stem + "_mask.png")

print("hand skin %.1f%% of pixels; marine arm skin %.1f%%" % (100 * hand_skin.mean(), 100 * arm_skin.mean()))
print("Lab mean  hand %s -> marine %s" % (mu_h.round(1), mu_a.round(1)))
print("Lab spread hand %s -> marine %s" % (sd_h.round(1), sd_a.round(1)))

S = 512
patch_idx = np.argwhere(arm_skin)
cy, cx = patch_idx[len(patch_idx) // 2]
half = arm.shape[0] // 8
patch = arm[max(0, cy - half):cy + half, max(0, cx - half):cx + half]
tiles = [Image.fromarray((hand * 255).astype(np.uint8)).resize((S, S)),
         Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).resize((S, S)),
         Image.fromarray((patch * 255).astype(np.uint8)).resize((S, S))]
cmp_im = Image.new("RGB", (3 * S, S))
for i, t in enumerate(tiles):
    cmp_im.paste(t, (i * S, 0))
cmp_im.save(stem + "_compare.png")
print("compare written")
