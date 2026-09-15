import struct, sys
sys.path.insert(0, r"E:\DOOMWork\_old\RS_VRIK\tools\armcut_2026-09-14")
from measure import read_mdl
p = r"E:\DOOMWork\RS_VRBody\models\vrtorso.mdl"
d = open(p, "rb").read()
print("scale", struct.unpack_from("<3f", d, 8), "translate", struct.unpack_from("<3f", d, 20))
pts, info, _ = read_mdl(p, 0)
print(info)
zs = [q[2] for q in pts]
print("z range %.2f..%.2f" % (min(zs), max(zs)))
# per |y| band: top of the mesh and where the side is widest
for lo, hi in [(0,3),(3,6),(6,8),(8,10),(10,12),(12,14)]:
    band = [q for q in pts if lo <= abs(q[1]) < hi]
    if band:
        print("|y| %4.1f-%4.1f  n %3d  z top %.2f  z mean %.2f  x %.2f..%.2f" % (lo, hi, len(band), max(q[2] for q in band), sum(q[2] for q in band)/len(band), min(q[0] for q in band), max(q[0] for q in band)))
# the outermost points by z slice: where the shoulders stick out
for z0 in range(-4, 19, 2):
    sl = [q for q in pts if z0 <= q[2] < z0 + 2]
    if sl:
        print("z %5.1f..%5.1f  n %3d  max|y| %.2f" % (z0, z0 + 2, len(sl), max(abs(q[1]) for q in sl)))
