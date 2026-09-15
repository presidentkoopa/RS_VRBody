"""Frame-0 shape of pistolet.md3 per surface: bounds, and the receiver's slices along x (barrel) and z (up)."""
import sys
sys.path.insert(0, r"E:/DOOMWork/tools")
from md3 import MD3Model

m = MD3Model.load("E:/DOOMWork/RS_VR_Weapons/models/pistols/pistolet.md3")
for s in m.surfaces:
    vs = s.verts[0]
    xs = [v[0] for v in vs]; ys = [v[1] for v in vs]; zs = [v[2] for v in vs]
    print("%-8s x %7.2f..%7.2f  y %6.2f..%6.2f  z %7.2f..%7.2f" % (s.name, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))

rec = [v for s in m.surfaces if s.name in ("rec", "rec.001") for v in s.verts[0]]
print("receiver z slices (x range, y range) -- the grip is the tall part hanging below the slide:")
zmin = min(v[2] for v in rec); zmax = max(v[2] for v in rec)
step = (zmax - zmin) / 12.0
z = zmin
while z < zmax - 1e-6:
    sl = [v for v in rec if z <= v[2] < z + step]
    if sl:
        print("  z %7.2f..%7.2f  n %3d  x %7.2f..%7.2f  y %6.2f..%6.2f" % (z, z + step, len(sl), min(v[0] for v in sl), max(v[0] for v in sl), min(v[1] for v in sl), max(v[1] for v in sl)))
    z += step
