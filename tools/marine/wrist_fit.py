"""Where the marine arm meets the RS hand IN THE ENGINE, at a straight wrist, measured in the hand's own file space.

The engine (actor.zs SetModelReach*, body_rig.zs placeArm for the RS hand):
  - the arm's END JOINT (bip_hand_*) lands on the hand's point (0, 1.47, 0) renderer = file (0, 0, 1.47), plus the
    live rs_arm_sock_rs_ofs cvars (0 today);
  - fingerDir (0,-1,0) renderer = file -z: the elbow swivels so the forearm lines up with the hand, so at a straight
    wrist the forearm direction (lowerArm -> hand) is the hand's -z;
  - the twist rolls the arm's twistRef onto the hand's twistRef (1,0,0) renderer = file +x (the index side);
  - Root_joint (the stub) is aimed along the forearm, which at a straight wrist changes nothing.
The hand is drawn at K_HAND map units per model unit (0.34, compose_mockup.py) and the engine draws hand_left.iqm's
file geometry as the LEFT hand, so the RIGHT arm meets its mirror (x -> -x); the marine arm IQMs are in map units.

For each side this puts the arm's cut ring and forearm into hand file space and compares them with the RS hand's
stub, slice by slice along z: centre offset, width/height, and the worst place the stub pokes OUT through the
forearm (radius of stub minus radius of the arm tube at the same angle). Writes wrist_fit.png and wrist_fit.json.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, "E:/DOOMWork/RS_VRBody/tools/fingers")
from hand_iqm import Hand

HERE = os.path.dirname(os.path.abspath(__file__))
K = 0.34
LAND_Z = 1.47
TWIST = {"R": (0.1929, 0.6177, -0.7624), "L": (-0.1929, 0.6177, -0.7624)}      # renderer order (x, z, y)
hand = Hand("E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm")
HP = hand.pos.copy()


def arm_to_hand_space(side):
    a = Hand(os.path.join(HERE, "iqm", "marine_arm_%s.iqm" % ("rt" if side == "R" else "lf")))
    h = a.base_global[a.index["bip_hand_" + side]][:3, 3]
    e = a.base_global[a.index["bip_lowerArm_" + side]][:3, 3]
    d = (h - e) / np.linalg.norm(h - e)
    tr = np.array(TWIST[side]); tw = np.array([tr[0], tr[2], tr[1]])                  # renderer -> file
    x = tw - (tw @ d) * d; x /= np.linalg.norm(x)
    # The hand as DRAWN is  world = h + K * Rw @ S @ (q - land),  S = diag(mirror, 1, 1) its MODELDEF mirror, Rw a
    # proper rotation. In the arm's file frame the RIGHT arm meets the file geometry as it is and the LEFT arm its
    # mirror (compose_mockup.py, whose sides the owner checked). The engine turns DRAWN directions, mirror included:
    #   drawn fingers  Rw @ S @ (0,0,-1) = d        ->  Rw column 2 = -d
    #   drawn index    Rw @ S @ (1,0,0)  = x        ->  Rw column 0 = mirror * x
    mirror = 1.0 if side == "R" else -1.0
    c0 = mirror * x; c2 = -d; c1 = np.cross(c2, c0)
    Rw = np.stack([c0, c1, c2], 1)
    assert abs(np.linalg.det(Rw) - 1.0) < 1e-6
    S = np.diag([mirror, 1.0, 1.0])
    def to_hand(P):
        return ((P - h) @ Rw) / K @ S + np.array([0.0, 0.0, LAND_Z])     # S @ Rw^T (P - h) / K + land
    t = a.tris.astype(int)
    edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), 1)
    u, cnt = np.unique(edges, axis=0, return_counts=True)
    bnd = np.unique(u[cnt == 1])
    near = ((a.pos[bnd] - h) @ d) > -3.0
    return to_hand(a.pos), to_hand(a.pos[bnd[near]])


def polar(P, c):
    r = P[:, :2] - c
    return np.degrees(np.arctan2(r[:, 1], r[:, 0])) % 360, np.linalg.norm(r, axis=1)


report = {}
fig, axs = plt.subplots(2, 4, figsize=(20, 10))
for row, side in enumerate(("R", "L")):
    A, ring = arm_to_hand_space(side)
    zlo, zhi = ring[:, 2].min(), ring[:, 2].max()
    # the stub's axis: its cross-section centres along z (bind), fitted as a line
    zs = np.arange(2.0, 10.6, 0.5)
    cents = np.array([HP[(HP[:, 2] > z0) & (HP[:, 2] < z0 + 0.5)][:, :2].mean(0) for z0 in zs])
    slices = []
    worst = (-1e9, None)
    for z0 in np.arange(max(2.0, zlo - 0.5), 10.5, 0.5):
        hs = HP[(HP[:, 2] > z0) & (HP[:, 2] < z0 + 0.5)]
        as_ = A[(A[:, 2] > z0) & (A[:, 2] < z0 + 0.5)]
        if len(hs) < 6 or len(as_) < 6:
            continue
        ch, ca = hs[:, :2].mean(0), as_[:, :2].mean(0)
        # poke-through: per 20-degree sector around the ARM tube centre, stub max radius vs arm min radius
        th_h, r_h = polar(hs, ca); th_a, r_a = polar(as_, ca)
        pokes = []
        for s0 in range(0, 360, 20):
            mh = (th_h >= s0) & (th_h < s0 + 20); ma = (th_a >= s0) & (th_a < s0 + 20)
            if mh.any() and ma.any():
                pokes.append(r_h[mh].max() - r_a[ma].min())
        poke = max(pokes) if pokes else float("nan")
        if pokes and poke > worst[0]:
            worst = (poke, float(z0))
        slices.append(dict(z=float(z0), stub_centre=ch.round(2).tolist(), arm_centre=ca.round(2).tolist(),
                           offset=float(np.linalg.norm(ca - ch)),
                           stub_wh=(np.ptp(hs[:, :2], 0)).round(2).tolist(), arm_wh=(np.ptp(as_[:, :2], 0)).round(2).tolist(),
                           poke=float(poke)))
    rc = ring[:, :2].mean(0)
    hs = HP[(HP[:, 2] > zlo) & (HP[:, 2] < zhi)]
    report[side] = dict(cut_ring_z=[float(zlo), float(zhi)], cut_ring_centre=rc.round(2).tolist(),
                        cut_ring_wh=np.ptp(ring[:, :2], 0).round(2).tolist(),
                        stub_centre_at_cut=hs[:, :2].mean(0).round(2).tolist(), stub_wh_at_cut=np.ptp(hs[:, :2], 0).round(2).tolist(),
                        worst_poke=[float(worst[0]), worst[1]], slices=slices)
    print("side %s: cut ring z %.2f..%.2f (hand model units; the stub runs z 2..10.6, crease at 2)" % (side, zlo, zhi))
    print("   ring centre %s wh %s | stub centre %s wh %s at the same z" % (rc.round(2), np.ptp(ring[:, :2], 0).round(2), hs[:, :2].mean(0).round(2), np.ptp(hs[:, :2], 0).round(2)))
    print("   worst poke-through of the stub past the arm surface: %.2f model units (%.2f map) at z %s" % (worst[0], worst[0] * K, worst[1]))
    for sl in slices[::3]:
        print("   z %.1f  offset %.2f  stub wh %s  arm wh %s  poke %.2f" % (sl["z"], sl["offset"], sl["stub_wh"], sl["arm_wh"], sl["poke"]))
    # pictures: hand-space side views (x-z, y-z) and the cut-plane cross-section
    for col, (i, j, nm) in enumerate(((0, 2, "x (index side) / z"), (1, 2, "y (palm/back) / z"))):
        ax = axs[row, col]
        ax.scatter(HP[:, i], HP[:, j], s=1, c="tab:orange", label="RS hand")
        ax.scatter(A[:, i], A[:, j], s=1, c="tab:blue", alpha=0.35, label="marine arm")
        ax.scatter(ring[:, i], ring[:, j], s=4, c="k", label="arm cut edge")
        ax.set_xlim(-12, 12); ax.set_ylim(-10, 16); ax.set_aspect("equal"); ax.set_title("%s arm: %s" % (side, nm)); ax.legend(fontsize=7, markerscale=4)
    ax = axs[row, 2]
    ax.scatter(hs[:, 0], hs[:, 1], s=4, c="tab:orange", label="stub at the cut z")
    ax.scatter(ring[:, 0], ring[:, 1], s=8, c="k", label="arm cut edge")
    ax.set_aspect("equal"); ax.set_title("%s: cross-section at the cut (x / y)" % side); ax.legend(fontsize=7)
    ax = axs[row, 3]
    zz = [s["z"] for s in slices]
    ax.plot(zz, [s["poke"] * K for s in slices], "r-o", label="stub pokes out (map units, >0 shows)")
    ax.plot(zz, [s["offset"] * K for s in slices], "b-o", label="centre offset (map units)")
    ax.axhline(0, color="k", lw=0.5); ax.set_xlabel("hand z (model units)"); ax.legend(fontsize=7); ax.set_title("%s: along the forearm" % side)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "wrist_fit.png"), dpi=70)
json.dump(report, open(os.path.join(HERE, "wrist_fit.json"), "w"), indent=1)
print("wrist_fit.png / .json written")
