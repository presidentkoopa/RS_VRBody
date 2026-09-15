"""Exact cross-sections where the marine arm meets the RS hand, in the hand's file space (engine placement at a straight
wrist, as wrist_fit.py -- whose vertex slices were too sparse on the low-poly forearm to trust).

Every triangle of both meshes is cut by planes z = const; around the STUB's own centre at that z, a ray every 5 degrees
finds the arm's nearest surface and the stub's farthest. Per slice:
  gap   = arm radius - stub radius   (> 0: open seam that far; < 0: the stub pokes OUT through the arm)
  cover = the share of rays that hit the arm (1.0 = a closed tube; less = the ragged cut or past its edge)
Writes wrist_contours.png (contours per slice, both sides) and wrist_contours.json.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
K, LAND_Z = 0.34, 1.47
TWIST = {"R": (0.1929, 0.6177, -0.7624), "L": (-0.1929, 0.6177, -0.7624)}
ZS = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0]
ANG = np.radians(np.arange(0, 360, 5))
hand = Hand("E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm")
HP, HT = hand.pos.copy(), hand.tris.astype(int)


def arm_in_hand_space(side):
    """Same placement as wrist_fit.py (engine: end joint on file z 1.47, fingers along the forearm, drawn index on twistRef)."""
    a = Hand(os.path.join(HERE, "iqm", "marine_arm_%s.iqm" % ("rt" if side == "R" else "lf")))
    h = a.base_global[a.index["bip_hand_" + side]][:3, 3]
    e = a.base_global[a.index["bip_lowerArm_" + side]][:3, 3]
    d = (h - e) / np.linalg.norm(h - e)
    tr = np.array(TWIST[side]); tw = np.array([tr[0], tr[2], tr[1]])
    x = tw - (tw @ d) * d; x /= np.linalg.norm(x)
    mirror = 1.0 if side == "R" else -1.0
    c0 = mirror * x; c2 = -d; c1 = np.cross(c2, c0)
    Rw = np.stack([c0, c1, c2], 1)
    S = np.diag([mirror, 1.0, 1.0])
    P = ((a.pos - h) @ Rw) / K @ S + np.array([0.0, 0.0, LAND_Z])
    return P, a.tris.astype(int)


def slice_segments(P, T, z0):
    z = P[T][:, :, 2] - z0                                   # T x 3
    segs = []
    for k in range(3):
        i, j = k, (k + 1) % 3
        cross = (z[:, i] * z[:, j]) < 0
        tt = z[cross, i] / (z[cross, i] - z[cross, j])
        pts = P[T[cross, i]] + (P[T[cross, j]] - P[T[cross, i]]) * tt[:, None]
        segs.append((np.where(cross)[0], pts[:, :2]))
    # pair the two crossings of each triangle
    by_tri = {}
    for idx, pts in segs:
        for t_, p_ in zip(idx, pts):
            by_tri.setdefault(t_, []).append(p_)
    return np.array([v[:2] for v in by_tri.values() if len(v) >= 2])      # N x 2 x 2


def ray_hits(segs, c, ang):
    """Distances along each ray from c to every segment it crosses (list per ray)."""
    if len(segs) == 0:
        return [np.array([]) for _ in ang]
    A, B = segs[:, 0] - c, segs[:, 1] - c
    E = B - A
    out = []
    for th in ang:
        u = np.array([np.cos(th), np.sin(th)])
        den = u[0] * E[:, 1] - u[1] * E[:, 0]
        ok = np.abs(den) > 1e-9
        s = np.where(ok, (A[:, 0] * E[:, 1] - A[:, 1] * E[:, 0]) / np.where(ok, den, 1), -1)     # along the ray
        w = np.where(ok, (A[:, 0] * u[1] - A[:, 1] * u[0]) / np.where(ok, den, 1), -1)          # along the segment
        hit = ok & (s > 0) & (w >= 0) & (w <= 1)
        out.append(s[hit])
    return out


report = {}
fig, axs = plt.subplots(2, len(ZS), figsize=(3 * len(ZS), 6.4))
for row, side in enumerate(("R", "L")):
    AP, AT = arm_in_hand_space(side)
    rows = []
    for col, z0 in enumerate(ZS):
        hs, as_ = slice_segments(HP, HT, z0), slice_segments(AP, AT, z0)
        c = hs.reshape(-1, 2).mean(0) if len(hs) else np.zeros(2)
        hh, ah = ray_hits(hs, c, ANG), ray_hits(as_, c, ANG)
        stub_r = np.array([x.max() if len(x) else np.nan for x in hh])
        arm_r = np.array([x.min() if len(x) else np.nan for x in ah])
        gap = arm_r - stub_r
        cover = float(np.mean([len(x) > 0 for x in ah]))
        g = gap[~np.isnan(gap)]
        # CENTRING (first run: small mean gap but the stub through one wall and a wide gap on the other -- off-centre,
        # not undersized). On a closed ring: the arm ring's own centre (segment-length-weighted), the offset from the
        # stub's centre, and the gap left if the stub were moved onto it.
        centred = {}
        if cover >= 0.99 and len(as_) and len(hs):
            L = np.linalg.norm(as_[:, 1] - as_[:, 0], axis=1)
            ca = ((as_[:, 0] + as_[:, 1]) / 2 * L[:, None]).sum(0) / L.sum()
            hh2, ah2 = ray_hits(hs + (ca - c), ca, ANG), ray_hits(as_, ca, ANG)
            s2 = np.array([x.max() if len(x) else np.nan for x in hh2]); a2 = np.array([x.min() if len(x) else np.nan for x in ah2])
            g2 = (a2 - s2)[~np.isnan(a2 - s2)]
            centred = dict(arm_centre=ca.round(2).tolist(), offset=(ca - c).round(2).tolist(),
                           gap_min=float(g2.min()), gap_mean=float(g2.mean()), gap_max=float(g2.max()))
            ax_ = axs[row, col]
            ax_.plot([ca[0]], [ca[1]], "bx")
        rows.append(dict(z=z0, cover=round(cover, 2), stub_centre=c.round(2).tolist(),
                         gap_min=float(g.min()) if len(g) else None, gap_max=float(g.max()) if len(g) else None,
                         gap_mean=float(g.mean()) if len(g) else None, centred=centred,
                         gap_by_angle=[None if np.isnan(v) else round(float(v), 2) for v in gap]))
        ax = axs[row, col]
        for sg in as_: ax.plot(sg[:, 0], sg[:, 1], "-", color="tab:blue", lw=1)
        for sg in hs: ax.plot(sg[:, 0], sg[:, 1], "-", color="tab:orange", lw=1)
        ax.plot([c[0]], [c[1]], "k+")
        ax.set_aspect("equal"); ax.set_xlim(-9, 9); ax.set_ylim(-7, 11)
        ax.set_title("%s z %.1f  cover %.0f%%\ngap %s..%s map" % (side, z0, 100 * cover,
                     "%.2f" % (g.min() * K) if len(g) else "-", "%.2f" % (g.max() * K) if len(g) else "-"), fontsize=8)
        ax.set_xticks([]); ax.set_yticks([])
    report[side] = rows
    print("side %s  (hand model units; x0.34 for map units; blue arm, orange stub)" % side)
    for r_ in rows:
        cz = r_["centred"]
        print("  z %4.1f  arm ring closed %3.0f%%  gap min %6s  mean %6s  max %6s (map)%s" % (
            r_["z"], 100 * r_["cover"],
            "%.2f" % (r_["gap_min"] * K) if r_["gap_min"] is not None else "-",
            "%.2f" % (r_["gap_mean"] * K) if r_["gap_mean"] is not None else "-",
            "%.2f" % (r_["gap_max"] * K) if r_["gap_max"] is not None else "-",
            "   | centred: offset %s model, gap min %.2f mean %.2f max %.2f map" % (cz["offset"], cz["gap_min"] * K, cz["gap_mean"] * K, cz["gap_max"] * K) if cz else ""))
    offs = np.array([r_["centred"]["offset"] for r_ in rows if r_["centred"]])
    if len(offs):
        print("  mean centring offset over the closed slices: x %.2f y %.2f model units (%.2f, %.2f map); spread %.2f" % (
            offs[:, 0].mean(), offs[:, 1].mean(), offs[:, 0].mean() * K, offs[:, 1].mean() * K, float(np.linalg.norm(offs - offs.mean(0), axis=1).max())))
        report[side + "_mean_offset_model"] = offs.mean(0).round(3).tolist()
fig.suptitle("Marine arm (blue) around the RS hand stub (orange), hand file space x/y per z slice -- engine placement, straight wrist", fontsize=10)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "wrist_contours.png"), dpi=75)
json.dump(report, open(os.path.join(HERE, "wrist_contours.json"), "w"), indent=1)
print("written")
