"""The RS hand's wrist stub shaped to the marine arm it meets, one hand IQM per hand and per arm pairing.

usage: stub_reshape.py IQM_DIR OUT_DIR [--flare-max 0.35] [--margin 0.05]
IQM_DIR holds the cut arms and wrist_socket.json (anatomical pairing) / wrist_socket_engine_pairing.json.

WHICH ARM MEETS WHICH HAND (wrist_socket.py):
  anatomical (rs_body_arm_swap 1): the _rt arm meets the file hand as it is -> the OFF hand block (Scale +1);
                                   the _lf arm meets it mirrored -> the MAIN hand block (Scale -1)
  engine     (rs_body_arm_swap 0): the _rt arm reaches the MAIN hand (mirrored), the _lf arm the OFF hand
wrist_socket.py already measures every arm in the hand's FILE space for its pairing, so the reshape works on the
file vertices directly and the engine's mirror does the rest.

THE SHAPE, per stub vertex (bind z above the wrist crease, z 2.0), around the stub's own section centre:
  - at and past the arm's cut (z >= z_cut): the stub's radius becomes the arm's inner radius at that angle less
    MARGIN -- widened (capped at FLARE_MAX, so a big gauntlet stays a cuff that overhangs the wrist instead of the
    wrist ballooning out to fill it) or pulled in wherever it would poke through;
  - from the crease to the cut: blended in by smoothstep, so the hand's own wrist is untouched at the crease;
  - deeper inside the arm (z_cut + 1.5 on): only pulled in where it would poke through.
The arm is placed with its socket move (the landing point offset), exactly as the engine will draw it.
Topology, UVs, weights, joints and every frame are the hand's own: only positions (and those vertices' normals)
change, written in place into a copy of hand_left_poses.iqm.
"""
import json, os, struct, sys
import numpy as np

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
_args = [a for a in sys.argv[1:] if not a.startswith("--")]
IQM_DIR, OUT = _args[0], _args[1]
FLARE_MAX = float(sys.argv[sys.argv.index("--flare-max") + 1]) if "--flare-max" in sys.argv else 0.35
# The marine's RIGHT arm (file _rt) is a bare forearm: a real wrist tapers into it, so the RS wrist may widen
# further to meet it. The LEFT is a gauntlet whose opening should overhang the wrist like a cuff -- capped low.
FLARE_BARE = float(sys.argv[sys.argv.index("--flare-bare") + 1]) if "--flare-bare" in sys.argv else 0.7
FLARE_BY_SIDE = {"R": FLARE_BARE, "L": FLARE_MAX}
MARGIN = float(sys.argv[sys.argv.index("--margin") + 1]) if "--margin" in sys.argv else 0.05
os.makedirs(OUT, exist_ok=True)
K, LAND_Z, CREASE_Z, DEEP = 0.34, 1.47, 2.0, 1.5
TWIST = {"R": (0.1929, 0.6177, -0.7624), "L": (-0.1929, 0.6177, -0.7624)}
ANG = np.radians(np.arange(0, 360, 5))
HAND_IQM = "E:/DOOMWork/RS_WorldHands/models/hands/hand_left_poses.iqm"
hand = Hand(HAND_IQM)
HP, HT = hand.pos.copy(), hand.tris.astype(int)
PAIRINGS = {"anatomical": ("wrist_socket.json", {"R": "off", "L": "main"}, {"R": 1.0, "L": -1.0}),
            "engine": ("wrist_socket_engine_pairing.json", {"R": "main", "L": "off"}, {"R": -1.0, "L": 1.0})}


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
    P = ((a.pos - h) @ Rw) / K @ S + np.array([0.0, 0.0, LAND_Z])
    return P + np.array([dx, dy, 0.0]), a.tris.astype(int)


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


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def measure(P_hand, AP, AT, zs):
    rows = []
    for z in zs:
        hs, as_ = slice_segments(P_hand, HT, z), slice_segments(AP, AT, z)
        if len(hs) == 0:
            continue
        c = hs.reshape(-1, 2).mean(0)
        g = ray_radii(as_, c, np.min) - ray_radii(hs, c, np.max)
        if np.all(np.isnan(g)):
            continue
        rows.append((z, float(np.nanmin(g) * K), float(np.nanmean(g) * K), float(np.nanmax(g) * K)))
    return rows


def write_positions(src_path, dst_path, P):
    d = bytearray(open(src_path, "rb").read())
    h = struct.unpack_from("<27I", d, 16)
    nva, nvert, ova, ntri, otri = h[7], h[8], h[9], h[10], h[11]
    tris = np.frombuffer(bytes(d), dtype="<u4", count=ntri * 3, offset=otri).reshape(-1, 3).astype(int)
    n = np.zeros_like(P); a, b, c = P[tris[:, 0]], P[tris[:, 1]], P[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    for i in range(nva):
        typ, fl, fmt, size, off = struct.unpack_from("<5I", d, ova + i * 20)
        if typ == 0:
            d[off:off + nvert * 12] = P.astype("<f4").tobytes()
        elif typ == 2:
            old = np.frombuffer(bytes(d), dtype="<f4", count=nvert * 3, offset=off).reshape(-1, 3).astype(float)
            moved = np.linalg.norm(P - HP, axis=1) > 1e-6
            keep_side = np.sign((n * old).sum(1))              # keep the authored normals' outward sense
            new = np.where(moved[:, None], n * np.where(keep_side == 0, 1, keep_side)[:, None], old)
            d[off:off + nvert * 12] = new.astype("<f4").tobytes()
    open(dst_path, "wb").write(bytes(d))


report = []
for pairing, (json_name, reaches, mirrors) in PAIRINGS.items():
    jp = os.path.join(IQM_DIR, json_name)
    if not os.path.exists(jp):
        report.append("%s: %s missing, skipped" % (pairing, json_name))
        continue
    sock = json.load(open(jp))
    for side in ("R", "L"):
        z_cut = float(sock[side]["z_cut"])
        dx, dy, _ = sock[side]["socket_file"]
        AP, AT = arm_in_hand_space(side, mirrors[side], dx, dy)
        # the arm's inner radius around the stub's own centre, on a grid of slices and angles
        # The grid starts AT the cut. The first run started 0.05 before it, where the arm is not yet a closed
        # ring, took that slice as the target, found almost every angle empty and moved nothing.
        zgrid = np.round(np.concatenate([np.arange(CREASE_Z, z_cut, 0.25), np.arange(z_cut + 0.02, 10.6, 0.25)]), 3)
        cen = {}; arm_r = {}
        for z in zgrid:
            hs = slice_segments(HP, HT, z)
            c = hs.reshape(-1, 2).mean(0) if len(hs) else np.zeros(2)
            cen[z] = c
            arm_r[z] = ray_radii(slice_segments(AP, AT, z), c, np.min)
        # THE TARGET RING: the first slice at or past the cut where every ray hits the arm
        closed = [z for z in zgrid if z >= z_cut and np.all(~np.isnan(arm_r[z]))]
        if not closed:
            report.append("%s pairing, %s arm: no closed ring past z %.2f -- skipped" % (pairing, side, z_cut))
            continue
        z_ring = closed[0]
        P = HP.copy()
        stub = np.where(HP[:, 2] > CREASE_Z)[0]
        for v in stub:
            z = HP[v, 2]
            zg = zgrid[np.argmin(np.abs(zgrid - min(max(z, zgrid[0]), zgrid[-1])))]
            c = cen[zg]
            rel = HP[v, :2] - c
            r = float(np.linalg.norm(rel))
            if r < 1e-6:
                continue
            th = np.arctan2(rel[1], rel[0]) % (2 * np.pi)
            k = int(round(th / np.radians(5))) % len(ANG)
            ring_r = arm_r[z_ring][k]
            here_r = arm_r[zg][k]
            new_r = r
            if z < z_cut:
                if not np.isnan(ring_r):
                    target = min(ring_r - MARGIN / K, r + FLARE_BY_SIDE[side] / K)
                    new_r = r + smoothstep((z - CREASE_Z) / max(z_cut - CREASE_Z, 1e-6)) * (target - r)
            else:
                lim = here_r - MARGIN / K if not np.isnan(here_r) else np.inf
                if z < z_cut + DEEP and not np.isnan(ring_r):
                    target = min(ring_r - MARGIN / K, r + FLARE_BY_SIDE[side] / K)
                    fade = 1.0 - smoothstep((z - z_cut) / DEEP)
                    new_r = r + fade * (target - r)
                new_r = min(new_r, lim)
            P[v, :2] = c + rel * (new_r / r)
        which = reaches[side]
        name = "hand_marine_%s_%s.iqm" % (which, pairing)
        write_positions(HAND_IQM, os.path.join(OUT, name), P)
        moved = np.linalg.norm(P - HP, axis=1)
        before = measure(HP, AP, AT, np.arange(z_cut, 10.01, 1.0))
        after = measure(P, AP, AT, np.arange(z_cut, 10.01, 1.0))
        report.append("%s pairing, %s arm -> %s hand (%s): cut z %.2f, socket (%.2f, %.2f); %d stub vertices moved, most %.2f map"
                      % (pairing, side, which, name, z_cut, dx, dy, int((moved > 1e-6).sum()), moved.max() * K))
        for (z, a0, m0, x0), (_, a1, m1, x1) in zip(before, after):
            report.append("   z %.2f  gap min %.2f -> %.2f   mean %.2f -> %.2f   max %.2f -> %.2f (map units)" % (z, a0, a1, m0, m1, x0, x1))
open(os.path.join(OUT, "stub_reshape_report.txt"), "w").write("\n".join(report) + "\n")
print("\n".join(report))
