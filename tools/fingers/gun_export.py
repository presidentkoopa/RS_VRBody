"""Pistolet frame 0 at its MODELDEF Scale 1.35: an OBJ to render and a triangle array to measure against.

Gun space = md3 model space times 1.35: x along the barrel, y across, z up.
The baked brass ("casing") is left out, as the card hides it.
"""
import os, sys
import numpy as np
sys.path.insert(0, "E:/DOOMWork/tools")
from md3 import MD3Model

SCALE = 1.35
OUT = os.path.dirname(os.path.abspath(__file__))

m = MD3Model.load("E:/DOOMWork/RS_VR_Weapons/models/pistols/pistolet.md3")
lines = ["mtllib pistolet.mtl", "usemtl pistolet"]
tris_all = []
parts = {}
vbase = 1
for s in m.surfaces:
    if s.name == "casing":
        continue
    vs = np.array(s.verts[0]) * SCALE
    for v in vs:
        lines.append("v %.5f %.5f %.5f" % tuple(v))
    for st in s.st:
        lines.append("vt %.5f %.5f" % (st[0], 1.0 - st[1]))
    for a, b, c in s.triangles:
        lines.append("f %d/%d %d/%d %d/%d" % (a + vbase, a + vbase, b + vbase, b + vbase, c + vbase, c + vbase))
    tri = vs[np.array(s.triangles)]
    tris_all.append(tri)
    parts[s.name] = tri
    vbase += len(vs)

with open(os.path.join(OUT, "pistolet.obj"), "w") as fh:
    fh.write("\n".join(lines) + "\n")
with open(os.path.join(OUT, "pistolet.mtl"), "w") as fh:
    fh.write("newmtl pistolet\nmap_Kd E:/DOOMWork/RS_VR_Weapons/models/pistols/WPN-9mm.png\n")
np.savez(os.path.join(OUT, "pistolet_tris.npz"), all=np.concatenate(tris_all), **parts)
allt = np.concatenate(tris_all)
print("pistolet: %d triangles, bounds %s .. %s (gun space, x barrel, z up)"
      % (len(allt), allt.reshape(-1, 3).min(axis=0).round(2), allt.reshape(-1, 3).max(axis=0).round(2)))
for n, t in parts.items():
    print("  %-8s %4d tris  %s .. %s" % (n, len(t), t.reshape(-1, 3).min(axis=0).round(2), t.reshape(-1, 3).max(axis=0).round(2)))
