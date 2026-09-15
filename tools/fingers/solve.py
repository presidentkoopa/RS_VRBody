"""Finger-contact mockup: the RS hand on the Pistolet's grip, fingers closing until they touch.

Gun space (md3 x 1.35): x barrel, y across, z up. The hand's file axes map onto the grip:
  hand +X (index side)  -> the grip's up axis
  hand +Y (palm faces)  -> +y (palm on the grip's -y panel)
  hand +Z (toward wrist)-> X cross Y (toward the back of the gun)
Three hands are written: OPEN (frame 0), BAKED (frame 8, index resting on the trigger -- what the
game draws today) and CONTACT (each finger curled from frame 0 toward the fist, frame 3, a knuckle
locking the moment the segment it moves touches the gun, the joints past it curling on).
"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hand_iqm import Hand, FINGERS, trs

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
HAND_TEX = "E:/DOOMWork/RS_WorldHands/models/hands/hand_basecolor.png"
GUN_TEX = "E:/DOOMWork/RS_VR_Weapons/models/pistols/WPN-9mm.png"

FINGER_RADIUS = 1.05      # hand units; the fingers are ~2.4 wide at the knuckles
SKIN = 0.15               # stop this far off the surface
STEPS = 60
TIP_EXTRA = 0.8           # the fingertip reaches a little past its last joint
PALM_GAP = 0.15           # palm this far off the grip panel
KNUCKLE_PAST_FRONT = 1.2  # the knuckle line sits this far in front of the front strap
INDEX_BELOW_TOP = 3.1     # the index knuckle this far below the top of the grip: just under the trigger guard

# HAND SIZE against the gun, for "how much of the wrongness is just scale". 1.0 is the game today
# (rs_hw_off_scale 1 with the Pistolet at MODELDEF 1.35). Gun-set distances (INDEX_BELOW_TOP) stay put;
# hand-set ones (finger thickness, palm surface, knuckle line) scale with the hand.
HAND_SCALE = 1.0
for _a in sys.argv:
    if _a.startswith("--hand-scale="):
        HAND_SCALE = float(_a.split("=", 1)[1])


# ---------------------------------------------------------------- geometry
def closest_on_tris(p, a, b, c):
    """Distance from each point p (P x 3) to the nearest of triangles (a, b, c) (T x 3 each)."""
    P = p[:, None, :]
    ab, ac, ap = b - a, c - a, P - a
    d1 = np.einsum("tk,ptk->pt", ab, ap); d2 = np.einsum("tk,ptk->pt", ac, ap)
    bp = P - b
    d3 = np.einsum("tk,ptk->pt", ab, bp); d4 = np.einsum("tk,ptk->pt", ac, bp)
    cp = P - c
    d5 = np.einsum("tk,ptk->pt", ab, cp); d6 = np.einsum("tk,ptk->pt", ac, cp)
    va = d3 * d6 - d5 * d4; vb = d5 * d2 - d1 * d6; vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom = np.where(np.abs(denom) < 1e-12, 1e-12, denom)
    v = vb / denom; w = vc / denom
    q = a + v[..., None] * ab + w[..., None] * ac                       # interior
    # region fallbacks
    m = (d1 <= 0) & (d2 <= 0); q = np.where(m[..., None], a, q)
    m = (d3 >= 0) & (d4 <= d3); q = np.where(m[..., None], b, q)
    m = (d6 >= 0) & (d5 <= d6); q = np.where(m[..., None], c, q)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    t_ab = d1 / np.where(np.abs(d1 - d3) < 1e-12, 1e-12, d1 - d3)
    q = np.where(m[..., None], a + t_ab[..., None] * ab, q)
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    t_ac = d2 / np.where(np.abs(d2 - d6) < 1e-12, 1e-12, d2 - d6)
    q = np.where(m[..., None], a + t_ac[..., None] * ac, q)
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    t_bc = (d4 - d3) / np.where(np.abs((d4 - d3) + (d5 - d6)) < 1e-12, 1e-12, (d4 - d3) + (d5 - d6))
    q = np.where(m[..., None], b + t_bc[..., None] * (c - b), q)
    return np.linalg.norm(P - q, axis=2).min(axis=1)


def slerp(q0, q1, t):
    q0 = q0 / np.linalg.norm(q0); q1 = q1 / np.linalg.norm(q1)
    d = float(np.dot(q0, q1))
    if d < 0: q1, d = -q1, -d
    if d > 0.9995:
        r = q0 + t * (q1 - q0); return r / np.linalg.norm(r)
    th = np.arccos(d)
    return (np.sin((1 - t) * th) * q0 + np.sin(t * th) * q1) / np.sin(th)


# ---------------------------------------------------------------- data
hand = Hand()
gun = np.load(os.path.join(HERE, "pistolet_tris.npz"))
tri = gun["all"]
A, B, C = tri[:, 0], tri[:, 1], tri[:, 2]
fit = np.load(os.path.join(HERE, "grip_fit.npz"))
u2, f2 = fit["up"], fit["forward"]              # (x, z) pairs
up = np.array([u2[0], 0.0, u2[1]]); fwd = np.array([f2[0], 0.0, f2[1]])
centre = np.array([fit["centre"][0], 0.0, fit["centre"][1]])

open_local = hand.frame_local[0]
fist_local = hand.frame_local[3]
baked_local = hand.frame_local[8]

# ---------------------------------------------------------------- placement
X = up
Y = np.array([0.0, 1.0, 0.0])
Z = np.cross(X, Y)
R = np.column_stack([X, Y, Z])                   # hand axes -> gun axes

g_open = hand.globals(hand.local_mats(open_local))
jp = lambda g, name: g[hand.index[name]][:3, 3]
open_skin = hand.skin(g_open)

# Palm surface height in hand Y: the open palm's vertices between wrist and knuckles, near the middle.
# The middle of the palm only, and a percentile rather than the highest vertex: the highest one in a
# wider box was a thumb or finger vertex (+3.59), which held the whole hand 3.5 units off the grip.
palm_region = open_skin[(open_skin[:, 2] < -3.0) & (open_skin[:, 2] > -8.0) & (np.abs(open_skin[:, 0]) < 2.5)
                        & (open_skin[:, 1] > 0.0)]
palm_surface_y = float(np.percentile(palm_region[:, 1], 60))

grip_front = float(fit["centre"] @ f2) + 0  # placeholder, replaced below
# front strap and top along the fitted axes, from the grip vertices' extent recorded in grip_fit
grip_top_along = float(fit["hi"])
# front edge: the largest forward extent over the grip's middle, measured directly here
g_rec = np.concatenate([gun["rec"].reshape(-1, 3), gun["mag"].reshape(-1, 3)])
sel = (g_rec[:, 0] < float(fit["trig_back"])) & (g_rec[:, 2] < float(fit["slide_bottom"]) - 0.5)
gv = g_rec[sel]
rel = gv - centre
along = rel @ up; across = rel @ fwd
mid = (along > float(fit["lo"]) + 2.0) & (along < grip_top_along - 2.0)
front_edge = across[mid].max()
ymin = float(fit["ymin"])

knuckle_index = jp(g_open, "INDEX_BASE_joint")
knuckle_mid = np.mean([jp(g_open, FINGERS[k][0]) for k in ("index", "middle", "ring", "pinky")], axis=0)

# Solve for the palm joint's gun-space position T: hand point h lands at R @ h + T.
#  along the grip: the index knuckle INDEX_BELOW_TOP under the top
#  across (forward): the knuckle line KNUCKLE_PAST_FRONT in front of the front strap
#  y: the palm surface PALM_GAP off the -y panel
T = centre.copy()
T += up * ((grip_top_along - INDEX_BELOW_TOP) - (R @ (HAND_SCALE * knuckle_index)) @ up)
T += fwd * ((front_edge + KNUCKLE_PAST_FRONT * HAND_SCALE) - (R @ (HAND_SCALE * knuckle_mid)) @ fwd)
T[1] = (ymin - PALM_GAP) - HAND_SCALE * palm_surface_y
M = np.eye(4); M[:3, :3] = R; M[:3, 3] = T
print("palm surface y %.2f  front edge %.2f  grip top %.2f  palm joint at gun %s" % (palm_surface_y, front_edge, grip_top_along, T.round(2)))


def to_gun(pts):
    return (HAND_SCALE * pts) @ R.T + T


# ---------------------------------------------------------------- solve
def pose_locals(t_by_joint):
    locs = []
    for j, (t0, q0, s0) in enumerate(open_local):
        name = hand.names[j]
        if name in t_by_joint:
            t1, q1, s1 = fist_local[j]
            k = t_by_joint[name]
            locs.append((t0 + k * (t1 - t0), slerp(q0, q1, k), s0 + k * (s1 - s0)))
        else:
            locs.append((t0, q0, s0))
    return locs


def segment_points(g, chain):
    pts = [jp(g, n) for n in chain]
    tip = pts[3] + (pts[3] - pts[2]) / max(1e-6, np.linalg.norm(pts[3] - pts[2])) * TIP_EXTRA
    segs = [(pts[0], pts[1]), (pts[1], pts[2]), (pts[2], tip)]
    out = []
    for a, b in segs:
        out.append(np.array([a + (b - a) * s for s in np.linspace(0.15, 1.0, 5)]))
    return out


def segment_gaps(tvals, chain):
    g = hand.globals(hand.local_mats(pose_locals(tvals)))
    return [float(closest_on_tris(to_gun(s), A, B, C).min()) for s in segment_points(g, chain)]


def solve():
    """Joint by joint, base first, a small step at a time. A step is kept unless it brings some
    segment closer than contact (radius + skin) -- or, for a segment already that close, closer
    than it already was. So a fingertip resting on the surface lets the knuckles behind it keep
    closing, and a finger placed touching can still close without pressing in."""
    t = {n: 0.0 for chain in FINGERS.values() for n in chain[:3]}
    contact = FINGER_RADIUS * HAND_SCALE + SKIN
    report = {}
    for fname, chain in FINGERS.items():
        movers = chain[:3]
        if fname == "thumb":
            # THE THUMB STARTS INSIDE THE GUN: the open frame points it into the slide, so closing
            # can only press it in. Search the other way -- from fully closed out past open -- and
            # keep the first pose where nothing is within contact: the thumb resting against the gun.
            best, best_worst = None, -1e9
            for k in np.linspace(1.0, -0.6, 81):
                trial = dict(t)
                for n in movers:
                    trial[n] = float(k)
                g_ = segment_gaps(trial, chain)
                if min(g_) >= contact:
                    best = trial
                    break
                if min(g_) > best_worst:
                    best_worst, best = min(g_), trial
            t = best
            gaps = segment_gaps(t, chain)
            report[fname] = ([round(t[n], 2) for n in movers], ["scan"] * 3, [round(d, 2) for d in gaps])
            continue
        blocked_by = [None, None, None]
        gaps = segment_gaps(t, chain)
        for _ in range(STEPS * 3):
            moved = False
            for i, n in enumerate(movers):
                if t[n] >= 1.0:
                    continue
                trial = dict(t)
                trial[n] = min(1.0, t[n] + 1.0 / STEPS)
                new = segment_gaps(trial, chain)
                bad = [k for k in range(3) if new[k] < contact and new[k] < gaps[k] - 1e-6]
                if bad:
                    blocked_by[i] = "seg%d" % bad[0]
                    continue
                t, gaps, moved = trial, new, True
            if not moved:
                break
        report[fname] = ([round(t[n], 2) for n in movers], blocked_by, [round(d, 2) for d in gaps])
    return t, report


t_contact, report = solve()
for k, (ts, touched, dmin) in report.items():
    print("  %-6s closed base/mid/top %s  stopped by %s  gap to gun per segment %s (radius %.2f)"
          % (k, ts, touched, dmin, FINGER_RADIUS))

# How far into the gun the open placement already is (palm and fingers before any curl).
open_d = closest_on_tris(to_gun(open_skin), A, B, C)
print("open hand: nearest vertex to the gun %.2f, vertices within 0.3: %d" % (open_d.min(), int((open_d < 0.3).sum())))
near = open_skin[open_d < 0.3]
if len(near):
    print("  those vertices in hand space: x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f"
          % (near[:, 0].min(), near[:, 0].max(), near[:, 1].min(), near[:, 1].max(), near[:, 2].min(), near[:, 2].max()))
    thumb = int(((near[:, 0] > 3.0) & (near[:, 2] > -14.0) & (near[:, 2] < -2.0)).sum())
    wrist = int((near[:, 2] > 0.0).sum())
    fingers = int((near[:, 2] < -10.0).sum())
    print("  thumb-ish %d  wrist (z>0) %d  fingers (z<-10) %d  palm/other %d" % (thumb, wrist, fingers, len(near) - thumb - wrist - fingers))


# ---------------------------------------------------------------- write
def write_obj(path, verts):
    lines = []
    for v in verts:
        lines.append("v %.5f %.5f %.5f" % tuple(v))
    for uv in hand.uv:
        lines.append("vt %.5f %.5f" % (uv[0], 1.0 - uv[1]))
    for a, b, c in hand.tris:
        lines.append("f %d/%d %d/%d %d/%d" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


out = os.path.join(HERE, "out" if HAND_SCALE == 1.0 else "out_s%03d" % round(HAND_SCALE * 100))
os.makedirs(out, exist_ok=True)
variants = {
    "open": hand.skin(g_open),
    "baked": hand.skin(hand.globals(hand.local_mats(baked_local))),
    "contact": hand.skin(hand.globals(hand.local_mats(pose_locals(t_contact)))),
}
look = (centre + np.array([2.0, 0.0, 1.0])).tolist()
shots_for = lambda tag: [
    {"file": os.path.join(out, tag + "_left.png"), "cam": (centre + np.array([-8.0, -34.0, 6.0])).tolist(), "look": look, "lens": 50},
    {"file": os.path.join(out, tag + "_right.png"), "cam": (centre + np.array([6.0, 34.0, 4.0])).tolist(), "look": look, "lens": 50},
    {"file": os.path.join(out, tag + "_front.png"), "cam": (centre + np.array([34.0, -10.0, 8.0])).tolist(), "look": look, "lens": 50},
]
for tag, verts in variants.items():
    obj = os.path.join(out, "hand_%s.obj" % tag)
    write_obj(obj, to_gun(verts))
    scene = {"objs": [{"path": os.path.join(HERE, "pistolet.obj"), "texture": GUN_TEX},
                      {"path": obj, "texture": HAND_TEX}],
             "shots": shots_for(tag)}
    sp = os.path.join(out, "scene_%s.json" % tag)
    json.dump(scene, open(sp, "w"), indent=1)
    if "--render" in sys.argv:
        r = subprocess.run([BLENDER, "-b", "--python", os.path.join(HERE, "render.py"), "--", sp],
                           capture_output=True, text=True)
        print(tag, "render:", "ok" if "DONE" in r.stdout else ("FAILED\n" + r.stdout[-1500:] + r.stderr[-1500:]))
print("wrote", out)
