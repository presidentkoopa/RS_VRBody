"""Can the fitted glove hold the OTHER Vanilla guns? The RS_VR_Weapons models that are not Ermac's meshes.

For each of our guns, Ermac's nearest gun (and his ready grip frame on it) is lined up onto ours:
  - both guns at their MODELDEF size (his blocks are Scale 1; ours |Scale|), frame 0, all surfaces;
  - a similarity ICP (scale, turn, move) of his gun onto ours, tried from a few starting turns, best kept;
  - his grip frame, and our fitted glove at 1494 + that frame, are carried across by the turn and move,
    their centre by the full similarity -- the hand keeps its own size, only its seat follows the scale.
The ICP gap (mean distance between the two gun surfaces afterwards, map-model units) and the scale are
printed and written on each image: a big gap or a scale far from 1 says the guns are not alike and the
grip is only a starting point. Everything in right-hand, unmirrored space (guns are near symmetric).

Renders: out/grips_transfer/ours_<gun>_{side,under}.png, montage out/gun_grips_transfer.png.
"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
sys.path.insert(0, HERE)
import gunhand_map as g
from hand_iqm import Hand
from md3 import MD3Model

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
RENDER = os.path.join(os.path.dirname(HERE), "fingers", "render.py")
OUT = os.path.join(HERE, "out", "grips_transfer").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
W = "E:/DOOMWork/RS_VR_Weapons/models/"
E = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/"
HAND_TEX = E + "hand/hand_HD.png"
REF = {  # his gun, his ready grip frame
    "pistol": (E + "pistol/berreta.md3", 6),
    "shotgun": (E + "shotgun/shotgun.md3", 30),
    "ssg": (E + "ssg/ssg.md3", 47),
    "chaingun": (E + "chaingun/chaingun.md3", 84),
    "rocket": (E + "rocketlauncher/rocketlauncher.md3", 95),
    "plasma": (E + "plasmarifle/plasma_rifle.md3", 106),
    "bfg": (E + "bfg9000/bfg9000.md3", 113),
    "chainsaw": (E + "chainsaw/chainsaw.md3", 29),
}
GUNS = [  # name, md3, texture, |MODELDEF Scale|, reference
    ("M4A3", W + "pistols/m4a3.md3", W + "pistols/m4a3.png", 0.82, "pistol"),
    ("Pistolet", W + "pistols/pistolet.md3", W + "pistols/WPN-9mm.png", 1.35, "pistol"),
    ("M37A2", W + "shotguns/AE_Shotgun/m37a2.md3", W + "shotguns/AE_Shotgun/m37a2.png", 1.1, "shotgun"),
    ("DoomShotgun", W + "shotguns/Shotgun/shotgun.md3", W + "shotguns/Shotgun/WPN-GUNS-k1.png", 1.35, "shotgun"),
    ("SuperShotgun", W + "shotguns/SuperShotgun/ssg.md3", W + "shotguns/SuperShotgun/WPN-GUNS-k1.png", 1.35, "ssg"),
    ("BullpupPump", W + "shotguns/BullpupPump/bullpuppump_wm.md3", W + "shotguns/BullpupPump/ssg.png", 1.1, "shotgun"),
    ("MachineGun", W + "chainguns/MachineGun/machinegun_wm.md3", W + "chainguns/MachineGun/Machinegun.png", 1.0, "chaingun"),
    ("RPG", W + "launchers/RPG/rpg_wm.md3", W + "launchers/RPG/rpg.png", 1.0, "rocket"),
    ("PlasmaRifle", W + "plasma/PlasmaRifle/plasmarifle_wm.md3", W + "plasma/PlasmaRifle/PlasmaRifle.png", 1.0, "plasma"),
    ("BFGHeavy", W + "bfg/BFGHeavy/bfgheavy_wm.md3", W + "bfg/BFGHeavy/bfg.png", 1.0, "bfg"),
    ("Chainsaw", W + "chainsaws/Chainsaw/chainsaw_wm.md3", W + "chainsaws/Chainsaw/chainsaw.png", 1.35, "chainsaw"),
]
SKIP_SURF = ("casing",)
rng = np.random.default_rng(1)


def gun_mesh(path, scale):
    m = MD3Model.load(path)
    verts, uv, faces, base = [], [], [], 0
    for s in m.surfaces:
        if s.name in SKIP_SURF:
            continue
        v = np.array(s.verts[0]) * scale
        verts.append(v); uv.append(np.array(s.st)); faces.append(np.array(s.triangles) + base); base += len(v)
    return np.concatenate(verts), np.concatenate(uv), np.concatenate(faces)


def surface_samples(v, f, n=2500):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    pick = rng.choice(len(f), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    return (1 - s)[:, None] * a[pick] + (s * (1 - r2))[:, None] * b[pick] + (s * r2)[:, None] * c[pick]


def nn(A, B):
    idx = np.empty(len(A), dtype=int); d = np.empty(len(A))
    for i in range(0, len(A), 700):
        dd = ((A[i:i + 700, None, :] - B[None, :, :]) ** 2).sum(2)
        j = dd.argmin(1); idx[i:i + 700] = j; d[i:i + 700] = np.sqrt(dd[np.arange(len(j)), j])
    return idx, d


def sim_icp(src, dst, R0, iters=40):
    s, R = 1.0, R0.copy()
    t = dst.mean(0) - (src @ R.T).mean(0)
    for _ in range(iters):
        cur = s * src @ R.T + t
        i1, d1 = nn(cur, dst); i2, d2 = nn(dst, cur)
        A = np.vstack([src, src[i2]]); B = np.vstack([dst[i1], dst])
        keep = np.concatenate([d1, d2]) < np.percentile(np.concatenate([d1, d2]), 85)
        A, B = A[keep], B[keep]
        ca, cb = A.mean(0), B.mean(0)
        X, Y = A - ca, B - cb
        U, S, Vt = np.linalg.svd(Y.T @ X)
        D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
        R = U @ D @ Vt
        s = (S * np.diag(D)).sum() / (X ** 2).sum()
        t = cb - s * (R @ ca)
    cur = s * src @ R.T + t
    _, d1 = nn(cur, dst); _, d2 = nn(dst, cur)
    return (d1.mean() + d2.mean()) / 2, s, R, t


def rotz(deg):
    a = np.radians(deg); c, s_ = np.cos(a), np.sin(a)
    return np.array([[c, -s_, 0], [s_, c, 0], [0, 0, 1]])


hand = Hand(os.path.join(HERE, "hand_ermac_poses2.iqm"))
g.set_palm(hand.index["HANDPALM_joint"])
results = []
for name, path, tex, sc, ref in GUNS:
    ov, ouv, of = gun_mesh(path, sc)
    his_path, fr = REF[ref]
    hv, _, hf = gun_mesh(his_path, 1.0)
    dst = surface_samples(ov, of); src = surface_samples(hv, hf)
    best = None
    for start in (rotz(0), rotz(180)):
        r = sim_icp(src, dst, start)
        if best is None or r[0] < best[0]:
            best = r
    gap, s, R, t = best
    _, Rp, tp = g.to_ours(fr)
    glove = g.to_his(g.skin(hand, 1494 + fr), Rp, tp)
    c = glove.mean(0)
    glove_on = (glove - c) @ R.T + (s * (R @ c) + t)

    gun_obj = os.path.join(HERE, "xfer_gun_%s.obj" % name)
    g.write_obj(gun_obj, ov, ouv, of)
    hand_obj = os.path.join(HERE, "xfer_glove_%s.obj" % name)
    g.write_obj(hand_obj, glove_on, g.uvs, g.tris)
    hc = glove_on.mean(0)
    sc_json = {"objs": [{"path": gun_obj.replace("\\", "/"), "texture": tex},
                        {"path": hand_obj.replace("\\", "/"), "texture": HAND_TEX}],
               "shots": [{"file": OUT + "/ours_%s_side.png" % name, "cam": [hc[0] - 10, hc[1] - 75, hc[2] + 20], "look": list(hc), "lens": 45},
                         {"file": OUT + "/ours_%s_under.png" % name, "cam": [hc[0] + 25, hc[1] + 55, hc[2] - 45], "look": list(hc), "lens": 45}]}
    scp = os.path.join(HERE, "scene_xfer_%s.json" % name)
    json.dump(sc_json, open(scp, "w"), indent=1)
    rr = subprocess.run([BLENDER, "-b", "--python", RENDER, "--", scp], capture_output=True, text=True)
    ok = all(os.path.exists(x["file"]) for x in sc_json["shots"])
    results.append((name, ref, fr, gap, s))
    print("%-13s <- his %-8s frame %3d  ICP gap %.2f  scale %.2f  %s" % (name, ref, fr, gap, s, "rendered" if ok else "RENDER FAILED " + rr.stderr[-300:]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(len(GUNS), 2, figsize=(11, 4.2 * len(GUNS)), dpi=70)
for i, (name, ref, fr, gap, s) in enumerate(results):
    for j, view in enumerate(("side", "under")):
        ax = axes[i, j]; ax.set_axis_off()
        p = OUT + "/ours_%s_%s.png" % (name, view)
        if os.path.exists(p):
            ax.imshow(plt.imread(p)[80:880, 190:1090])
        ax.set_title("%s -- glove from his %s grip (frame %d), %s\nguns line up to %.2f units, his gun scaled %.2f" % (name, ref, fr, view, gap, s), fontsize=10)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "out", "gun_grips_transfer.png"))
print("wrote out/gun_grips_transfer.png")
