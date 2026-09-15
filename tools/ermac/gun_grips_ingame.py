"""The glove on each Vanilla gun WHERE THE GAME PUTS THEM: both through the engine's follow-hand chain.

Both the hand (RS_HandWorldMain/Off) and the gun prop (WM_Prop*) follow the same controller frame, so the
controller transform and the 0.01 unit scale are shared and dropped. What remains, per model, is
models.cpp FSpriteModelFrame::ObjectToWorldMatrix steps 3-5 (VSMatrix post-multiplies, so in written order):
    S(xs, zs, ys) . T((xo+px)/xs, (zo+pz)/zs, (yo+py)/ys) . Ry(-yaw) Rz(pitch) Rx(-roll) . Ry(-ao) Rz(po) Rx(-ro)
applied to the model-space vertex, which both the MD3 and the IQM loader take as file (x, z, y).
MODELDEF gives Scale / Offset / Angle-Pitch-RollOffset; the placement sets are the OWNER'S doomxr.ini
values (gun seats wm_*, hand seats rs_hw_main / rs_hw_off). No actor Scale on either class. NOAUTOREVERSE
on both, so no mirror from the controller.

For each gun: the glove at frame 8 (what a held gun shows today, RPOSE_GRIP) and at Ermac's grip frame for
that kind of gun (1494 + his hand.md3 frame). Rendered back in file-like space (the y/z swap undone) so the
camera code matches the other scripts. --only NAME renders one gun.
Writes out/grips_ingame/<gun>_<pose>_<view>.png and out/gun_grips_ingame.png.
"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
sys.path.insert(0, "E:/DOOMWork/tools")
from hand_iqm import Hand
from md3 import MD3Model

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
RENDER = os.path.join(os.path.dirname(HERE), "fingers", "render.py")
OUT = os.path.join(HERE, "out", "grips_ingame").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
INI = os.path.join(os.environ["USERPROFILE"], "Documents", "My Games", "DoomXR", "doomxr.ini")
W = "E:/DOOMWork/RS_VR_Weapons/models/"
HAND_IQM = os.path.join(HERE, "hand_ermac_poses2.iqm")
HAND_TEX = "E:/DOOMWork/RS_WorldHands/models/hands/hand_ermac.png"
ERMAC_BASE = 1494
TODAY_FRAME = 8

# name, hand, md3, texture, Scale (x y z), Offset (x y z), placement prefix, Ermac grip frame (hand.md3)
GUNS = [
    ("M4A3", "main", W + "pistols/m4a3.md3", W + "pistols/m4a3.png", (-0.82, 0.82, 0.82), (0.013, -28.103, -8.435), "wm_main", 6),
    ("Pistolet", "off", W + "pistols/pistolet.md3", W + "pistols/WPN-9mm.png", (1.35, 1.35, 1.35), (0.148, -30.839, -4.177), "wm_off", 6),
    ("M37A2", "main", W + "shotguns/AE_Shotgun/m37a2.md3", W + "shotguns/AE_Shotgun/m37a2.png", (-1.1, 1.1, 1.1), (-0.257, -49.130, -5.625), "wm_pumpm37", 30),
    ("DoomShotgun", "off", W + "shotguns/Shotgun/shotgun.md3", W + "shotguns/Shotgun/WPN-GUNS-k1.png", (1.35, 1.35, 1.35), (0.042, -41.745, -4.028), "wm_pumpdoom", 30),
    ("SuperShotgun", "main", W + "shotguns/SuperShotgun/ssg.md3", W + "shotguns/SuperShotgun/WPN-GUNS-k1.png", (1.35, 1.35, 1.35), (0.0, -36.344, -2.995), "wm_ssg", 47),
    ("BullpupPump", "off", W + "shotguns/BullpupPump/bullpuppump_wm.md3", W + "shotguns/BullpupPump/ssg.png", (-1.1, 1.1, 1.1), (0.0, -45.392, -5.227), "wm_bullpuppump", 30),
    ("Chaingun", "main", W + "chainguns/Chaingun/chaingun_wm.md3", W + "chainguns/Chaingun/chaingun_HD.png", (-1.0, 1.0, 1.0), (0.0, -24.0, -10.0), "wm_chaingun", 84),
    ("MachineGun", "off", W + "chainguns/MachineGun/machinegun_wm.md3", W + "chainguns/MachineGun/Machinegun.png", (-1.0, 1.0, 1.0), (-0.203, -52.594, -4.188), "wm_machinegun", 84),
    ("RocketLauncher", "main", W + "launchers/RocketLauncher/rocketlauncher_wm.md3", W + "launchers/RocketLauncher/rocketlauncher.png", (-1.0, 1.0, 1.0), (0.0, -24.0, -10.0), "wm_rocketlauncher", 95),
    ("RPG", "off", W + "launchers/RPG/rpg_wm.md3", W + "launchers/RPG/rpg.png", (-1.0, 1.0, 1.0), (3.250, -14.172, 8.828), "wm_rpg", 95),
    ("PlasmaRifle", "main", W + "plasma/PlasmaRifle/plasmarifle_wm.md3", W + "plasma/PlasmaRifle/PlasmaRifle.png", (-1.0, 1.0, 1.0), (0.469, -60.688, -1.266), "wm_plasmarifle", 106),
    ("PlasmaRifleBlue", "off", W + "plasma/PlasmaRifle/plasmarifle_wm.md3", W + "plasma/PlasmaRifle/PlasmaRifleBlue.png", (-1.0, 1.0, 1.0), (0.469, -60.688, -1.266), "wm_plasmarifleblue", 106),
    ("BFG9000", "main", W + "bfg/BFG/bfg_wm.md3", W + "bfg/BFG/bfg9000.png", (-1.0, 1.0, 1.0), (0.0, -24.0, -10.0), "wm_bfg", 113),
    ("BFGHeavy", "off", W + "bfg/BFGHeavy/bfgheavy_wm.md3", W + "bfg/BFGHeavy/bfg.png", (-1.0, 1.0, 1.0), (0.078, -54.500, 1.016), "wm_bfgheavy", 113),
    ("Chainsaw", "main", W + "chainsaws/Chainsaw/chainsaw_wm.md3", W + "chainsaws/Chainsaw/chainsaw.png", (1.35, 1.35, 1.35), (-2.468, -45.120, -15.378), "wm_chainsaw", 29),
    ("HeavyChainsaw", "off", W + "chainsaws/ChainsawHeavy/chainsaw_heavy_wm.md3", W + "chainsaws/ChainsawHeavy/chainsaw.png", (-1.0, 1.0, 1.0), (0.0, -24.0, -10.0), "wm_chainsawheavy", 29),
]
HAND_DEF = {  # RS_WorldHands MODELDEF RS_HandWorldMain / Off
    "main": dict(scale=(-1.0, 1.0, 1.0), offset=(0.0, 0.1, -0.05), ao=0.0, po=90.0, ro=-90.0, prefix="rs_hw_main"),
    "off": dict(scale=(1.0, 1.0, 1.0), offset=(0.0, 0.1, -0.05), ao=0.0, po=90.0, ro=-90.0, prefix="rs_hw_off"),
}


def read_ini():
    vals = {}
    for line in open(INI, encoding="latin-1"):
        if "=" in line and (line.startswith("wm_") or line.startswith("rs_hw_")):
            k, v = line.strip().split("=", 1)
            try:
                vals.setdefault(k, float(v))
            except ValueError:
                pass
    return vals


INIV = read_ini()


def placement(prefix):
    g = lambda s, d: INIV.get(prefix + s, d)
    return dict(ofs=(g("_ofs_x", 0.0), g("_ofs_y", 0.0), g("_ofs_z", 0.0)),
                yaw=g("_yaw", 0.0), pitch=g("_pitch", 0.0), roll=g("_roll", 0.0),
                scale=max(g("_scale", 1.0), 1e-6) if g("_scale", 1.0) > 0 else 1.0,
                axis=tuple(g(s, 1.0) if g(s, 1.0) > 0 else 1.0 for s in ("_scale_x", "_scale_y", "_scale_z")))


def rot(deg, axis):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    x, y, z = axis
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s, 0],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s, 0],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c), 0],
                     [0, 0, 0, 1]])


def chain(scale, offset, ao, po, ro, pl):
    xs, ys, zs = scale
    xo, yo, zo = offset
    px, py, pz = pl["ofs"]
    S = np.diag([xs * pl["scale"] * pl["axis"][0], zs * pl["scale"] * pl["axis"][2], ys * pl["scale"] * pl["axis"][1], 1.0])
    T = np.eye(4); T[:3, 3] = [(xo + px) / xs, (zo + pz) / zs, (yo + py) / ys]
    M = S @ T
    M = M @ rot(-pl["yaw"], (0, 1, 0)) @ rot(pl["pitch"], (0, 0, 1)) @ rot(-pl["roll"], (1, 0, 0))
    M = M @ rot(-ao, (0, 1, 0)) @ rot(po, (0, 0, 1)) @ rot(-ro, (1, 0, 0))
    return M


def apply(M, file_verts):
    e = np.c_[file_verts[:, 0], file_verts[:, 2], file_verts[:, 1], np.ones(len(file_verts))]  # loader: (x, z, y)
    w = e @ M.T
    return w[:, [0, 2, 1]]          # back to file-like axes for Blender (z up); same swap for hand and gun


def write_obj(path, verts, uv, faces):
    with open(path, "w") as fh:
        for v in verts:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for u in uv:
            fh.write("vt %.5f %.5f\n" % (u[0], 1.0 - u[1]))
        for a, b, c in faces:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))


hand = Hand(HAND_IQM)
nj = len(hand.names)


def skinned(frame):
    G = hand.globals(hand.local_mats(hand.frame_local[frame]))
    sk = np.array([G[j] @ hand.base_inv[j] for j in range(nj)])
    hp = np.c_[hand.pos, np.ones(len(hand.pos))]
    w = hand.bwt / np.maximum(hand.bwt.sum(axis=1, keepdims=True), 1e-9)
    out = np.zeros((len(hand.pos), 3))
    for k in range(4):
        out += w[:, k:k + 1] * np.einsum("vij,vj->vi", sk[hand.bidx[:, k]], hp)[:, :3]
    return out


only = None
for a in sys.argv[1:]:
    if a.startswith("--only="):
        only = a.split("=", 1)[1]

done = []
for name, side, path, tex, scale, offset, prefix, efr in GUNS:
    if only and name != only:
        continue
    gm = MD3Model.load(path)
    verts, uv, faces, base = [], [], [], 0
    for s in gm.surfaces:
        if s.name == "casing":
            continue
        v = np.array(s.verts[0]); verts.append(v); uv.append(np.array(s.st))
        faces.append(np.array(s.triangles) + base); base += len(v)
    gv = apply(chain(scale, offset, 0.0, 0.0, 0.0, placement(prefix)), np.concatenate(verts))
    gun_obj = os.path.join(HERE, "ingame_gun_%s.obj" % name)
    write_obj(gun_obj, gv, np.concatenate(uv), np.concatenate(faces))

    hd = HAND_DEF[side]
    Mh = chain(hd["scale"], hd["offset"], hd["ao"], hd["po"], hd["ro"], placement(hd["prefix"]))
    for tag, frame in (("today", TODAY_FRAME), ("ermac", ERMAC_BASE + efr)):
        hv = apply(Mh, skinned(frame))
        hobj = os.path.join(HERE, "ingame_hand_%s_%s.obj" % (name, tag))
        write_obj(hobj, hv, hand.uv, hand.tris)
        c = hv.mean(axis=0)
        # barrel direction = the gun's longest horizontal extent; side camera across it
        gxy = gv[:, :2] - gv[:, :2].mean(axis=0)
        _, _, vt = np.linalg.svd(gxy, full_matrices=False)
        barrel = np.r_[vt[0], 0.0]; across = np.r_[-vt[0][1], vt[0][0], 0.0]
        shots = [{"file": OUT + "/%s_%s_side.png" % (name, tag), "cam": list(c + across * 75 + np.array([0, 0, 15])), "look": list(c), "lens": 45},
                 {"file": OUT + "/%s_%s_under.png" % (name, tag), "cam": list(c - across * 35 + barrel * 25 + np.array([0, 0, -50])), "look": list(c), "lens": 45}]
        sc = {"objs": [{"path": gun_obj.replace("\\", "/"), "texture": tex}, {"path": hobj.replace("\\", "/"), "texture": HAND_TEX}], "shots": shots}
        scp = os.path.join(HERE, "scene_ingame_%s_%s.json" % (name, tag))
        json.dump(sc, open(scp, "w"), indent=1)
        r = subprocess.run([BLENDER, "-b", "--python", RENDER, "--", scp], capture_output=True, text=True)
        ok = all(os.path.exists(s_["file"]) for s_ in shots)
        print("%-15s %-4s %-5s frame %4d  %s" % (name, side, tag, frame, "rendered" if ok else "RENDER FAILED " + r.stderr[-300:]))
    done.append((name, side, efr))

if len(done) > 1:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(done), 4, figsize=(20, 4.2 * len(done)), dpi=60)
    for i, (name, side, efr) in enumerate(done):
        for j, (tag, view) in enumerate((("today", "side"), ("ermac", "side"), ("today", "under"), ("ermac", "under"))):
            ax = axes[i, j]; ax.set_axis_off()
            p = OUT + "/%s_%s_%s.png" % (name, tag, view)
            if os.path.exists(p):
                ax.imshow(plt.imread(p)[80:880, 190:1090])
            label = "today's grip (frame 8)" if tag == "today" else "Ermac's grip (frame %d)" % (ERMAC_BASE + efr)
            ax.set_title("%s (%s hand) -- %s, %s" % (name, side, label, view), fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "out", "gun_grips_ingame.png"))
    print("wrote out/gun_grips_ingame.png")
