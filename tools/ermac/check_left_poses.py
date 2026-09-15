"""hand_left_poses.iqm: the RS hand skinned with Ermac frames 1298+58 (fist) and 1298+144, rendered beside the glove."""
import json, os, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "fingers"))
from hand_iqm import Hand
h = Hand(HERE + "/hand_left_poses.iqm")
nj = len(h.names)
for fr in (58, 144):
    G = h.globals(h.local_mats(h.frame_local[1298 + fr]))
    sk = np.array([G[j] @ h.base_inv[j] for j in range(nj)])
    hp = np.c_[h.pos, np.ones(len(h.pos))]
    w = h.bwt.astype(np.float64); w = w / w.sum(axis=1, keepdims=True)
    out = np.zeros((len(h.pos), 3))
    for k in range(4):
        out += w[:, k:k + 1] * np.einsum("vij,vj->vi", sk[h.bidx[:, k]], hp)[:, :3]
    with open(HERE + "/left_f%d.obj" % fr, "w") as fh:
        for v in out: fh.write("v %.5f %.5f %.5f\n" % tuple(v))
        for uv in h.uv: fh.write("vt %.5f %.5f\n" % (uv[0], 1 - uv[1]))
        for a, b, c in h.tris: fh.write("f %d/%d %d/%d %d/%d\n" % (a+1, a+1, b+1, b+1, c+1, c+1))
    sc = {"objs": [{"path": HERE + "/left_f%d.obj" % fr, "texture": "E:/DOOMWork/RS_WorldHands/models/hands/hand_basecolor.png"}],
          "shots": [{"file": HERE + "/out/left_f%d_palm.png" % fr, "cam": [10.0, 70.0, -6.0], "look": [0.0, 0.0, -8.0], "lens": 60}]}
    json.dump(sc, open(HERE + "/scene_left_f%d.json" % fr, "w"))
    subprocess.run([r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe", "-b", "--python", "../fingers/render.py", "--", HERE + "/scene_left_f%d.json" % fr], capture_output=True)
    print("frame", fr, "ok" if os.path.exists(HERE + "/out/left_f%d_palm.png" % fr) else "no render")
