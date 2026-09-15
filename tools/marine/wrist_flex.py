"""Does the wrist seam hold when the wrist BENDS? The reshaped marine hand against its cut arm, posed as the engine poses it.

usage: wrist_flex.py IQM_DIR STUB_DIR [--pairing anatomical|engine]

THE ENGINE'S BEND (actor.zs SetModelReachTarget / SetModelReachTargetJoint, body_rig.zs for the RS hand):
  - the hand stays on the controller; the arm's wrist joint stays on the hand point file (0, 0, 1.47) plus the
    socket; the FOREARM's direction turns. Measured in the arm's frame, that is the whole hand turning by -a about
    the landing point;
  - Root_joint (the stub) is aimed back along the forearm: turned by +a (capped at 70 degrees, aim weight 1) about
    the pivot (0,0,0) with keepChildren, so HANDPALM and the fingers keep their place. Each vertex follows by its
    own skin weights: Root_joint's share takes the stub's turn, the rest stays with the palm.
Bends: flexion/extension about the hand's x (index-side axis), deviation about its y (palm axis).
For each bend: the gap between the arm's inner surface and the stub, per 5-degree ray around the stub's centre, on
slices square to the ARM (the arm is static here), from the cut to the stub's end. Negative = the stub pokes out.
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
IQM_DIR, STUB_DIR = _args[0], _args[1]
PAIRING = sys.argv[sys.argv.index("--pairing") + 1] if "--pairing" in sys.argv else "anatomical"
# THE AIM PIVOT. body_rig.zs today: SetModelReachTargetJoint(0, 'Root_joint', (0,0,0), 70) -- the stub turns about
# the hand's ORIGIN while the arm turns about its wrist joint on the landing point, ~3 hand units away once the
# socket moves it. First bend test: the stub pushed out ~0.3-0.4 map units at 40 degrees. "--pivot landing"
# turns it about the landing point itself (socket included), which the native's pivot argument already allows.
PIVOT_AT_LANDING = "--pivot" in sys.argv and sys.argv[sys.argv.index("--pivot") + 1] == "landing"
K, LAND_Z, AIM_MAX = 0.34, 1.47, 70.0
TWIST = {"R": (0.1929, 0.6177, -0.7624), "L": (-0.1929, 0.6177, -0.7624)}
ANG = np.radians(np.arange(0, 360, 5))
CFG = {"anatomical": ("wrist_socket.json", {"R": "off", "L": "main"}, {"R": 1.0, "L": -1.0}),
       "engine": ("wrist_socket_engine_pairing.json", {"R": "main", "L": "off"}, {"R": -1.0, "L": 1.0})}
json_name, reaches, mirrors = CFG[PAIRING]
sock = json.load(open(os.path.join(IQM_DIR, json_name)))


def rot(axis, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def arm_in_hand_space(side, mirror, dx, dy):
    a = Hand(os.path.join(IQM_DIR, "marine_arm_%s.iqm" % ("rt" if side == "R" else "lf")))
    h = a.base_global[a.index["bip_hand_" + side]][:3, 3]
    e = a.base_global[a.index["bip_lowerArm_" + side]][:3, 3]
    d = (h - e) / np.linalg.norm(h - e)
    tr = np.array(TWIST[side]); tw = np.array([tr[0], tr[2], tr[1]])
    x = tw - (tw @ d) * d; x /= np.linalg.norm(x)
    c0 = mirror * x; c2 = -d; c1 = np.cross(c2, c0)
    Rw = np.stack([c0, c1, c2], 1)
    S = np.diag([mirror, 1.0, 1.0])
    return ((a.pos - h) @ Rw) / K @ S + np.array([dx, dy, LAND_Z]), a.tris.astype(int)


def slice_segments(P, T, z0):
    z = P[T][:, :, 2] - z0
    by_tri = {}
    for k in range(3):
        i, j = k, (k + 1) % 3
        cross = (z[:, i] * z[:, j]) < 0
        tt = z[cross, i] / (z[cross, i] - z[cross, j])
        pts = P[T[cross, i]] + (P[T[cross, j]] - P[T[cross, i]]) * tt[:, None]
        for t_, p_ in zip(np.where(cross)[0], pts[:, :2]):
            by_tri.setdefault(t_, []).append(p_)
    return np.array([v[:2] for v in by_tri.values() if len(v) >= 2])


def ray_radii(segs, c, pick):
    out = np.full(len(ANG), np.nan)
    if len(segs) == 0:
        return out
    A, B = segs[:, 0] - c, segs[:, 1] - c
    E = B - A
    for n, th in enumerate(ANG):
        u = np.array([np.cos(th), np.sin(th)])
        den = u[0] * E[:, 1] - u[1] * E[:, 0]
        ok = np.abs(den) > 1e-9
        s = np.where(ok, (A[:, 0] * E[:, 1] - A[:, 1] * E[:, 0]) / np.where(ok, den, 1), -1)
        w = np.where(ok, (A[:, 0] * u[1] - A[:, 1] * u[0]) / np.where(ok, den, 1), -1)
        hit = ok & (s > 0) & (w >= 0) & (w <= 1)
        if hit.any():
            out[n] = pick(s[hit])
    return out


BENDS = [("straight", (1, 0, 0), 0.0), ("flex +40", (1, 0, 0), 40.0), ("flex -40", (1, 0, 0), -40.0),
         ("deviate +20", (0, 1, 0), 20.0), ("deviate -20", (0, 1, 0), -20.0)]
L = np.array([0.0, 0.0, LAND_Z])
for side in ("R", "L"):
    z_cut = float(sock[side]["z_cut"]); dx, dy, _ = sock[side]["socket_file"]
    AP, AT = arm_in_hand_space(side, mirrors[side], dx, dy)
    hand = Hand(os.path.join(STUB_DIR, "hand_marine_%s_%s.iqm" % (reaches[side], PAIRING)))
    P0, T = hand.pos.copy(), hand.tris.astype(int)
    root = hand.index["Root_joint"]
    w_root = np.array([hand.bwt[v][hand.bidx[v] == root].sum() for v in range(len(P0))])
    tw_all = np.maximum(hand.bwt.sum(1), 1e-9)
    w_root = w_root / tw_all
    print("%s arm -> %s hand (%s pairing), cut z %.2f, socket (%.2f, %.2f), stub aim pivot %s"
          % (side, reaches[side], PAIRING, z_cut, dx, dy, "at the landing point" if PIVOT_AT_LANDING else "at the hand origin (today)"))
    for name, axis, a in BENDS:
        Rp = rot(axis, -a)                                    # the palm, in the arm's frame
        aim = float(np.clip(a, -AIM_MAX, AIM_MAX))
        Rs = rot(axis, aim)                                   # the stub turned back along the forearm
        pv = np.array([dx, dy, LAND_Z]) if PIVOT_AT_LANDING else np.zeros(3)
        palm = (P0 - L) @ Rp.T + L
        stub = (((P0 - pv) @ Rs.T + pv) - L) @ Rp.T + L
        P = palm * (1 - w_root)[:, None] + stub * w_root[:, None]
        gmin, gmean, gmax, worst_z = np.inf, [], -np.inf, None
        for z in np.arange(z_cut + 0.05, 10.3, 0.5):
            hs, as_ = slice_segments(P, T, z), slice_segments(AP, AT, z)
            if len(hs) == 0 or len(as_) == 0:
                continue
            c = hs.reshape(-1, 2).mean(0)
            g = ray_radii(as_, c, np.min) - ray_radii(hs, c, np.max)
            if np.all(np.isnan(g)):
                continue
            if np.nanmin(g) < gmin:
                gmin, worst_z = float(np.nanmin(g)), float(z)
            gmean.append(float(np.nanmean(g))); gmax = max(gmax, float(np.nanmax(g)))
        # the seam itself: the first slice past the cut
        hs, as_ = slice_segments(P, T, z_cut + 0.05), slice_segments(AP, AT, z_cut + 0.05)
        c = hs.reshape(-1, 2).mean(0)
        gs = ray_radii(as_, c, np.min) - ray_radii(hs, c, np.max)
        print("   %-12s seam gap mean %.2f max %.2f | along the forearm: smallest %.2f (z %.1f), mean %.2f, largest %.2f   (map units; <0 pokes out)"
              % (name, np.nanmean(gs) * K, np.nanmax(gs) * K, gmin * K, worst_z if worst_z is not None else -1, np.mean(gmean) * K, gmax * K))
