"""Every Vanilla and Vanilla+ gun with the glove at its SOLVED seat (seats.json), through the engine chain.

Same chain as gun_grips_ingame.py, from ingame_chain.py. Each gun gets the glove in Ermac's grip for its kind of gun
(1494 + his hand.md3 frame, GRIP_FRAME below) and its seat from seats.json ("new"; guns with no new seat keep the
ini's). Renders side and under views and a montage per set.
    --only=WM_PropX[,WM_PropY]   render just these
Writes out/seats/<prop>_{side,under}.png, out/gun_seats_vanilla.png, out/gun_seats_plus.png.
"""
import json, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
sys.path.insert(0, "E:/DOOMWork/tools")
import ingame_chain as ic
from hand_iqm import Hand
from md3 import MD3Model

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
RENDER = os.path.join(os.path.dirname(HERE), "fingers", "render.py")
OUT = os.path.join(HERE, "out", "seats").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
HAND_IQM = os.path.join(HERE, "hand_ermac_poses2.iqm")
HAND_TEX = "E:/DOOMWork/RS_WorldHands/models/hands/hand_ermac.png"
ERMAC_BASE = 1494
PISTOL, SHOTGUN, SSG, CHAINGUN, ROCKET, PLASMA, BFG, SAW = 6, 30, 47, 84, 95, 106, 113, 29
GRIP_FRAME = {
    "WM_PropM4A3": PISTOL, "WM_PropPistolet": PISTOL, "WM_PropMoonlight": PISTOL, "WM_PropSunset": PISTOL,
    "WM_PropCola": PISTOL, "WM_PropTec9": PISTOL,
    "WM_PropPumpM37": SHOTGUN, "WM_PropPumpDoom": SHOTGUN, "WM_PropBullpupPump": SHOTGUN, "WM_PropSSG": SSG,
    "WM_PropChaingun": CHAINGUN, "WM_PropMachineGun": CHAINGUN, "WM_PropSMG": CHAINGUN, "WM_PropRifle": CHAINGUN, "WM_PropM16": CHAINGUN,
    "WM_PropRocketLauncher": ROCKET, "WM_PropRPG": ROCKET,
    "WM_PropPlasmaRifle": PLASMA, "WM_PropPlasmaRifleBlue": PLASMA, "WM_PropRailgun": PLASMA,
    "WM_PropFlamer": PLASMA, "WM_PropFlamethrower": PLASMA,
    "WM_PropBFG": CHAINGUN, "WM_PropBFGHeavy": CHAINGUN,   # a pistol grip behind a trigger guard: Ermac's BFG hand is open, this one wraps
    "WM_PropChainsaw": SAW, "WM_PropChainsawHeavy": SAW,
}

seats = json.load(open(os.path.join(HERE, "seats.json")))
ini = ic.read_ini()
props = ic.read_props()
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


def write_obj(path, verts, uv, faces):
    with open(path, "w") as fh:
        for v in verts:
            fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for u in uv:
            fh.write("vt %.5f %.5f\n" % (u[0], 1.0 - u[1]))
        for a, b, c in faces:
            fh.write("f %d/%d %d/%d %d/%d\n" % (a + 1, a + 1, b + 1, b + 1, c + 1, c + 1))


only = None
for a in sys.argv[1:]:
    if a.startswith("--only="):
        only = set(a.split("=", 1)[1].split(","))

hand_cache = {}
done = {"vanilla": [], "plus": []}
for prop, s in seats.items():
    if s["group"] not in done or prop not in GRIP_FRAME:
        continue
    if only and prop not in only:
        continue
    p = props[prop]
    override = dict(ofs=s["new"]) if s.get("new") else None
    pl = ic.placement(p["prefix"], ini, override)
    gm = MD3Model.load(p["md3"])
    verts, uv, faces, base = [], [], [], 0
    for sf in gm.surfaces:
        if sf.name == "casing":
            continue
        v = np.array(sf.verts[0]); verts.append(v); uv.append(np.array(sf.st))
        faces.append(np.array(sf.triangles) + base); base += len(v)
    gv = ic.engine_to_filelike(ic.to_engine(np.concatenate(verts), ic.chain(p["scale"], p["offset"], *p["base"], pl)))
    gun_obj = os.path.join(HERE, "seat_gun_%s.obj" % prop)
    write_obj(gun_obj, gv, np.concatenate(uv), np.concatenate(faces))

    hd = ic.HAND_DEF[p["hand"]]
    frame = ERMAC_BASE + GRIP_FRAME[prop]
    key = (p["hand"], frame)
    if key not in hand_cache:
        Mh = ic.chain(hd["scale"], hd["offset"], hd["ao"], hd["po"], hd["ro"], ic.placement(hd["prefix"], ini))
        hand_cache[key] = ic.engine_to_filelike(ic.to_engine(skinned(frame), Mh))
    hv = hand_cache[key]
    hobj = os.path.join(HERE, "seat_hand_%s_%d.obj" % (p["hand"], frame))
    if not os.path.exists(hobj):
        write_obj(hobj, hv, hand.uv, hand.tris)

    c = hv.mean(axis=0)
    gxy = gv[:, :2] - gv[:, :2].mean(axis=0)
    _, _, vt = np.linalg.svd(gxy, full_matrices=False)
    barrel = np.r_[vt[0], 0.0]; across = np.r_[-vt[0][1], vt[0][0], 0.0]
    shots = [{"file": OUT + "/%s_side.png" % prop, "cam": list(c + across * 75 + np.array([0, 0, 15])), "look": list(c), "lens": 45},
             {"file": OUT + "/%s_under.png" % prop, "cam": list(c - across * 35 + barrel * 25 + np.array([0, 0, -50])), "look": list(c), "lens": 45}]
    sc = {"objs": [{"path": gun_obj.replace("\\", "/"), "texture": p["skin"]}, {"path": hobj.replace("\\", "/"), "texture": HAND_TEX}], "shots": shots}
    scp = os.path.join(HERE, "scene_seat_%s.json" % prop)
    json.dump(sc, open(scp, "w"), indent=1)
    r = subprocess.run([BLENDER, "-b", "--python", RENDER, "--", scp], capture_output=True, text=True)
    ok = all(os.path.exists(x["file"]) for x in shots)
    print("%-24s %-4s %-7s seat %-24s frame %4d  %s" % (prop, p["hand"], s["group"], pl["ofs"], frame, "rendered" if ok else "RENDER FAILED " + r.stderr[-300:]), flush=True)
    done[s["group"]].append((prop, p["hand"], pl["ofs"], frame))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
for group, rows in done.items():
    if len(rows) < 2:
        continue
    fig, axes = plt.subplots(len(rows), 2, figsize=(10, 3.9 * len(rows)), dpi=60)
    for i, (prop, side, ofs, frame) in enumerate(rows):
        for j, view in enumerate(("side", "under")):
            ax = axes[i, j]; ax.set_axis_off()
            pth = OUT + "/%s_%s.png" % (prop, view)
            if os.path.exists(pth):
                ax.imshow(plt.imread(pth)[60:900, 100:1180])
            ax.set_title("%s (%s) seat %s, %s" % (prop.replace("WM_Prop", ""), side, [round(float(v), 1) for v in ofs], view), fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "out", "gun_seats_%s.png" % group))
    print("wrote out/gun_seats_%s.png" % group)
