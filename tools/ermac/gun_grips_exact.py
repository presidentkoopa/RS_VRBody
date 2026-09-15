"""Can the fitted glove hold the guns? The four Vanilla guns that share Ermac's own mesh space.

Our Chaingun, Rocket Launcher, BFG 9000 and Heavy Chainsaw meshes sit in the same space as his originals
(same bounds), and his MODELDEF blocks put hand.md3 in that same space with the same Scale and Offset. So
his hand frame on our gun mesh is the grip he built, exactly. For each gun, two renders from one camera:
  his_<gun>.png  his hand.md3 at that frame (the reference)
  ours_<gun>.png our fitted glove, skinned with frame 1494 + that frame of hand_ermac_poses2.iqm and put
                 back into his space through the palm (gunhand_map.to_his) -- what our rig can show
and a montage (out/gun_grips_exact.png). Everything is raw md3 space; his block's Scale -1 mirrors hand and
gun together, so it does not change how the hand sits on the gun.
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
OUT = os.path.join(HERE, "out", "grips").replace("\\", "/")
os.makedirs(OUT, exist_ok=True)
W = "E:/DOOMWork/RS_VR_Weapons/models/"
HAND_TEX = "E:/DOOMWork/_old/doom-force-unleashed_devbuild/models/hand/hand_HD.png"
GUNS = [  # name, our md3, texture, his ready frame (hand.md3)
    ("Chaingun", W + "chainguns/Chaingun/chaingun_wm.md3", W + "chainguns/Chaingun/chaingun_HD.png", 84),
    ("RocketLauncher", W + "launchers/RocketLauncher/rocketlauncher_wm.md3", W + "launchers/RocketLauncher/rocketlauncher.png", 95),
    ("BFG9000", W + "bfg/BFG/bfg_wm.md3", W + "bfg/BFG/bfg9000.png", 113),
    ("HeavyChainsaw", W + "chainsaws/ChainsawHeavy/chainsaw_heavy_wm.md3", W + "chainsaws/ChainsawHeavy/chainsaw.png", 29),
]

hand = Hand(os.path.join(HERE, "hand_ermac_poses2.iqm"))
g.set_palm(hand.index["HANDPALM_joint"])
BASE = 1494
his_tris = np.array(g.gun.triangles)
his_uv = np.array(g.gun.st)

for name, gun_path, gun_tex, fr in GUNS:
    gm = MD3Model.load(gun_path)
    verts, uv, faces, base = [], [], [], 0
    for s in gm.surfaces:
        v = np.array(s.verts[0]); verts.append(v); uv.append(np.array(s.st))
        faces.append(np.array(s.triangles) + base); base += len(v)
    gun_obj = os.path.join(HERE, "grip_gun_%s.obj" % name)
    g.write_obj(gun_obj, np.concatenate(verts), np.concatenate(uv), np.concatenate(faces))

    his = np.array(g.gun.verts[fr])
    his_obj = os.path.join(HERE, "grip_his_%s.obj" % name)
    g.write_obj(his_obj, his, his_uv, his_tris)

    Pn, Rp, tp = g.to_ours(fr)
    ours_his_space = g.to_his(g.skin(hand, BASE + fr), Rp, tp)
    ours_obj = os.path.join(HERE, "grip_ours_%s.obj" % name)
    g.write_obj(ours_obj, ours_his_space, g.uvs, g.tris)
    gap = np.linalg.norm(ours_his_space[g.INV.argsort()] - his, axis=1) if False else None

    c = his.mean(axis=0)
    shots_for = lambda tag: [
        {"file": OUT + "/%s_%s_side.png" % (tag, name), "cam": [c[0] - 10, c[1] - 75, c[2] + 20], "look": list(c), "lens": 50},
        {"file": OUT + "/%s_%s_under.png" % (tag, name), "cam": [c[0] + 25, c[1] + 55, c[2] - 45], "look": list(c), "lens": 50},
    ]
    for tag, hobj in (("his", his_obj), ("ours", ours_obj)):
        sc = {"objs": [{"path": gun_obj.replace("\\", "/"), "texture": gun_tex},
                       {"path": hobj.replace("\\", "/"), "texture": HAND_TEX}],
              "shots": shots_for(tag)}
        scp = os.path.join(HERE, "scene_grip_%s_%s.json" % (tag, name))
        json.dump(sc, open(scp, "w"), indent=1)
        r = subprocess.run([BLENDER, "-b", "--python", RENDER, "--", scp], capture_output=True, text=True)
        ok = all(os.path.exists(s["file"]) for s in sc["shots"])
        print("%-15s %-4s frame %3d  %s" % (name, tag, fr, "rendered" if ok else "FAILED\n" + r.stdout[-800:] + r.stderr[-800:]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(len(GUNS), 4, figsize=(20, 4.2 * len(GUNS)), dpi=70)
for i, (name, _, _, fr) in enumerate(GUNS):
    for j, (tag, view) in enumerate((("his", "side"), ("ours", "side"), ("his", "under"), ("ours", "under"))):
        ax = axes[i, j]; ax.set_axis_off()
        p = OUT + "/%s_%s_%s.png" % (tag, name, view)
        if os.path.exists(p):
            ax.imshow(plt.imread(p)[80:880, 190:1090])
        ax.set_title("%s -- %s (frame %d), %s" % (name, "Ermac's hand" if tag == "his" else "our fitted glove", fr, view), fontsize=11)
fig.tight_layout()
fig.savefig(os.path.join(HERE, "out", "gun_grips_exact.png"))
print("wrote out/gun_grips_exact.png")
