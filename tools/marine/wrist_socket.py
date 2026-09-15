"""The marine wrist SOCKET: one landing offset per arm that seats the RS hand's stub inside the marine forearm, and
where a clean flat cut of the arm should go. Engine placement at a straight wrist, as wrist_contours.py.

1. CLOSURE. Where along the hand's z the arm's ring is a whole tube (every 5-degree ray hits it) -- scanned every
   0.05 model units. The clean cut goes at the first z from which it stays whole.
2. SOCKET. One fixed (dx, dy) added to the landing point (moving the arm's wrist joint that far in the hand's file
   space) chosen to MAXIMISE THE SMALLEST GAP over every closed slice from the cut to the stub's end -- so the stub
   pokes out nowhere -- not the average of per-slice centres (those drift ~12 degrees: the forearm mesh runs off its
   own joint line). Grid search, then refined.
3. What that leaves: gap min / mean / max per slice, which the stub reshape has to close.

Prints the socket in file order AND in the order the engine's pointCVar takes it (renderer: x, z, y), model units.
Writes wrist_socket.json.
"""
import json, os, sys
import numpy as np

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
IQM_DIR = _args[0] if _args else os.path.join(HERE, "iqm")     # which cut of the arms to measure
# WHICH HAND EACH ARM MEETS, relative to the file geometry (both go through the same IQM load mirror, so only the
# hand's MODELDEF Scale and the rig's pairing matter). Default: the _rt arm meets the file hand as it is -- the
# anatomical pairing, what rs_body_arm_swap 1 gives. --engine-pairing: rs_body_arm_swap 0 (the owner's ini,
# 2026-09-15): the _rt arm (RSLOT_ARM_R) reaches the MAIN hand, drawn at Scale -1, so it meets the file hand
# MIRRORED, and the _lf arm the off hand as it is. Which one looks right is an on-screen check (IK plan 3e).
ENGINE_PAIRING = "--engine-pairing" in sys.argv
K, LAND_Z = 0.34, 1.47
STUB_END = 10.4
TWIST = {"R": (0.1929, 0.6177, -0.7624), "L": (-0.1929, 0.6177, -0.7624)}
ANG = np.radians(np.arange(0, 360, 5))
hand = Hand("E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm")
HP, HT = hand.pos.copy(), hand.tris.astype(int)


def arm_in_hand_space(side):
    a = Hand(os.path.join(IQM_DIR, "marine_arm_%s.iqm" % ("rt" if side == "R" else "lf")))
    h = a.base_global[a.index["bip_hand_" + side]][:3, 3]
    e = a.base_global[a.index["bip_lowerArm_" + side]][:3, 3]
    d = (h - e) / np.linalg.norm(h - e)
    tr = np.array(TWIST[side]); tw = np.array([tr[0], tr[2], tr[1]])
    x = tw - (tw @ d) * d; x /= np.linalg.norm(x)
    mirror = 1.0 if side == "R" else -1.0
    if ENGINE_PAIRING:
        mirror = -mirror
    c0 = mirror * x; c2 = -d; c1 = np.cross(c2, c0)
    Rw = np.stack([c0, c1, c2], 1)
    S = np.diag([mirror, 1.0, 1.0])
    return ((a.pos - h) @ Rw) / K @ S + np.array([0.0, 0.0, LAND_Z]), a.tris.astype(int)


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
    """Per ray from c: the nearest (pick=min) or farthest (pick=max) crossing, NaN when it hits nothing."""
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


report = {}
for side in ("R", "L"):
    AP, AT = arm_in_hand_space(side)
    # ---- 1. closure scan
    zs = np.round(np.arange(2.0, STUB_END + 1e-6, 0.05), 2)
    stub = {float(z): slice_segments(HP, HT, z) for z in zs}
    arm = {float(z): slice_segments(AP, AT, z) for z in zs}
    closed = []
    for z in zs:
        hs, as_ = stub[float(z)], arm[float(z)]
        c = hs.reshape(-1, 2).mean(0)
        closed.append(bool(np.all(~np.isnan(ray_radii(as_, c, np.min)))))
    closed = np.array(closed)
    # first z from which every slice to the stub's end is closed
    z_cut = None
    for i in range(len(zs)):
        if closed[i:].all():
            z_cut = float(zs[i]); break
    print("side %s: arm ring whole from hand z %.2f (%.2f map units behind the landing point)" % (side, z_cut, (z_cut - LAND_Z) * K))

    # ---- 2. socket search over the closed slices, every 0.25 in z
    zfit = [float(z) for z in zs if z >= z_cut and abs((z * 4) - round(z * 4)) < 1e-6]
    def evaluate(dx, dy):
        gaps = []
        for z in zfit:
            hs = stub[z] + np.array([dx, dy])[None, None, :] * 0     # the hand stays; the arm moves by (dx, dy)
            as_ = arm[z] + np.array([dx, dy])[None, None, :]
            c = hs.reshape(-1, 2).mean(0)
            g = ray_radii(as_, c, np.min) - ray_radii(hs, c, np.max)
            gaps.append(g)
        G = np.array(gaps)
        return float(np.nanmin(G)), G
    best = (-1e9, 0.0, 0.0)
    for dx in np.arange(-3.0, 3.01, 0.25):
        for dy in np.arange(-4.0, 2.01, 0.25):
            m, _ = evaluate(dx, dy)
            if m > best[0]:
                best = (m, float(dx), float(dy))
    for step in (0.1, 0.05, 0.02):
        m0, bx, by = best
        for dx in np.arange(bx - 2 * step, bx + 2.01 * step, step):
            for dy in np.arange(by - 2 * step, by + 2.01 * step, step):
                m, _ = evaluate(dx, dy)
                if m > best[0]:
                    best = (m, float(dx), float(dy))
    m, dx, dy = best
    _, G = evaluate(dx, dy)
    m0, G0 = evaluate(0.0, 0.0)
    print("   today (no socket offset): smallest gap %.2f map (negative = stub pokes out), mean %.2f" % (m0 * K, np.nanmean(G0) * K))
    print("   socket move of the arm: dx %.2f dy %.2f model units (%.2f, %.2f map)" % (dx, dy, dx * K, dy * K))
    print("   with it: smallest gap %.2f map, mean %.2f, largest %.2f" % (m * K, np.nanmean(G) * K, np.nanmax(G) * K))
    for z, g in zip(zfit, G):
        if abs(z * 2 - round(z * 2)) < 1e-6:
            print("     z %5.2f  gap min %.2f mean %.2f max %.2f map" % (z, np.nanmin(g) * K, np.nanmean(g) * K, np.nanmax(g) * K))
    # The arm moves by (dx, dy) when the landing POINT moves by (dx, dy): the point is where its wrist joint goes.
    # pointCVar offsets are in the target's model space as the renderer takes it: (x, z, y) of the file.
    report[side] = dict(z_cut=z_cut, cut_behind_landing_map=(z_cut - LAND_Z) * K,
                        socket_file=[round(dx, 3), round(dy, 3), 0.0], socket_renderer_ofs_xyz=[round(dx, 3), 0.0, round(dy, 3)],
                        gap_min_map=m * K, gap_mean_map=float(np.nanmean(G) * K), gap_max_map=float(np.nanmax(G) * K),
                        today_gap_min_map=m0 * K, today_gap_mean_map=float(np.nanmean(G0) * K),
                        gap_by_slice_map=[[z, float(np.nanmin(g) * K), float(np.nanmean(g) * K), float(np.nanmax(g) * K)] for z, g in zip(zfit, G)])
    print("   engine point offset (renderer x, y, z = file x, z, y): ofs_x %.3f ofs_y 0 ofs_z %.3f" % (dx, dy))
out_json = os.path.join(IQM_DIR, "wrist_socket_engine_pairing.json" if ENGINE_PAIRING else "wrist_socket.json")
json.dump(report, open(out_json, "w"), indent=1)
print("written", out_json)
