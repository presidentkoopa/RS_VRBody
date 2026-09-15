import struct
p = r"E:\DOOMWork\RS_VRBody\models\vrtorso.mdl"
d = open(p, "rb").read()
assert d[:4] == b"IDPO"
scale = struct.unpack_from("<3f", d, 8); trans = struct.unpack_from("<3f", d, 20)
nskins, sw, sh, nverts, ntris, nframes = struct.unpack_from("<6i", d, 48)
o = 84
for _ in range(nskins):
    g, = struct.unpack_from("<i", d, o); o += 4
    if g == 0: o += sw * sh
    else:
        nb, = struct.unpack_from("<i", d, o); o += 4; o += 4 * nb + nb * sw * sh
o += nverts * 12 + ntris * 16
t, = struct.unpack_from("<i", d, o); o += 4
assert t == 0
o += 24
vb = d[o:o + nverts * 4]
pts = [(scale[0]*vb[i*4] + trans[0], scale[1]*vb[i*4+1] + trans[1], scale[2]*vb[i*4+2] + trans[2]) for i in range(nverts)]
print("scale", scale, "translate", trans, "verts", nverts, "frames", nframes)
print("x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % (min(q[0] for q in pts), max(q[0] for q in pts), min(q[1] for q in pts), max(q[1] for q in pts), min(q[2] for q in pts), max(q[2] for q in pts)))
for lo, hi in [(0,3),(3,6),(6,8),(8,10),(10,12),(12,14)]:
    band = [q for q in pts if lo <= abs(q[1]) < hi]
    if band:
        print("|y| %4.1f-%4.1f  n %3d  z top %6.2f  z mean %6.2f  x %.2f..%.2f" % (lo, hi, len(band), max(q[2] for q in band), sum(q[2] for q in band)/len(band), min(q[0] for q in band), max(q[0] for q in band)))
for z0 in range(-4, 19, 2):
    sl = [q for q in pts if z0 <= q[2] < z0 + 2]
    if sl:
        print("z %5.1f..%5.1f  n %3d  max|y| %6.2f" % (z0, z0 + 2, len(sl), max(abs(q[1]) for q in sl)))
# the shoulder cap: outer third of the width, top 25% of its height
outer = [q for q in pts if abs(q[1]) >= 7.0]
if outer:
    top = max(q[2] for q in outer)
    cap = [q for q in outer if q[2] >= top - 4.0]
    for side in (1, -1):
        c = [q for q in cap if q[1] * side > 0]
        if c:
            n = len(c)
            print("cap side %+d  n %d  centroid (%.2f, %.2f, %.2f)  top %.2f" % (side, n, sum(q[0] for q in c)/n, sum(q[1] for q in c)/n, sum(q[2] for q in c)/n, max(q[2] for q in c)))
