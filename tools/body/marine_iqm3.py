"""Read-only summary of IQM files: meshes, joints (bind positions), anims, bounds."""
import struct, sys, os


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by, aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw, aw*bw - ax*bx - ay*by - az*bz)


def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2*(y*vz - z*vy); ty = 2*(z*vx - x*vz); tz = 2*(x*vy - y*vx)
    return (vx + w*tx + (y*tz - z*ty), vy + w*ty + (z*tx - x*tz), vz + w*tz + (x*ty - y*tx))


def read_iqm(path):
    data = open(path, "rb").read()
    assert data[:16] == b"INTERQUAKEMODEL\0"
    hdr = struct.unpack_from("<27I", data, 16)
    (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj,
     njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = hdr

    def text(o):
        end = data.index(b"\0", otext + o)
        return data[otext + o:end].decode("latin-1")

    print("==== %s  v%d  verts %d  tris %d  meshes %d  joints %d  anims %d  frames %d"
          % (os.path.basename(path), ver, nvert, ntri, nmesh, njoint, nanim, nframe))
    for i in range(nmesh):
        name, mat, fv, nv, ft, nt = struct.unpack_from("<6I", data, omesh + i * 24)
        print("  mesh %d %-24s mat %-30s verts %6d tris %6d" % (i, text(name), text(mat), nv, nt))

    joints = []
    for i in range(njoint):
        v = struct.unpack_from("<Ii3f4f3f", data, ojoint + i * 48)
        name, parent = text(v[0]), v[1]
        t, r, s = v[2:5], v[5:9], v[9:12]
        if parent >= 0:
            pn, pp, pt, pr, ps = joints[parent]
            rt = qrot(pr, (t[0]*ps[0], t[1]*ps[1], t[2]*ps[2]))
            wt = (pt[0] + rt[0], pt[1] + rt[1], pt[2] + rt[2])
            wr = qmul(pr, r)
            ws = (s[0]*ps[0], s[1]*ps[1], s[2]*ps[2])
        else:
            wt, wr, ws = t, r, s
        joints.append((name, parent, wt, wr, ws))
    for i, (n, p, wt, wr, ws) in enumerate(joints):
        print("  joint %3d %-32s parent %3d  pos (%8.3f %8.3f %8.3f)" % (i, n, p, wt[0], wt[1], wt[2]))

    for i in range(nanim):
        name, first, num, rate, fl = struct.unpack_from("<IIIfI", data, oanim + i * 20)
        print("  anim %-24s first %d frames %d rate %.1f" % (text(name), first, num, rate))

    for a in range(nva):
        typ, fl2, fmt, size, off = struct.unpack_from("<5I", data, ova + a * 20)
        if typ == 0 and fmt == 7 and size == 3:
            xs = struct.unpack_from("<%df" % (nvert * 3), data, off)
            X, Y, Z = xs[0::3], xs[1::3], xs[2::3]
            print("  bounds x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f"
                  % (min(X), max(X), min(Y), max(Y), min(Z), max(Z)))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        read_iqm(p)
