"""Read-only shape measurements for Quake .mdl and .iqm files.

usage:
  measure.py FILE [--frame N] [--meshes 3,9] [--axis x|y|z] [--slices N]
             [--along JOINT_A JOINT_B] [--top-band FRAC]

Prints raw model-space numbers only; no unit conversion is applied here.
"""
import struct, sys, math, argparse

def read_mdl(path, frame_index):
    d = open(path, 'rb').read()
    ident, ver = struct.unpack_from('<4si', d, 0)
    assert ident == b'IDPO', ident
    scale = struct.unpack_from('<3f', d, 8)
    trans = struct.unpack_from('<3f', d, 20)
    nskins, sw, sh, nverts, ntris, nframes = struct.unpack_from('<6i', d, 48)
    o = 84
    for _ in range(nskins):
        g, = struct.unpack_from('<i', d, o); o += 4
        if g == 0:
            o += sw * sh
        else:
            nb, = struct.unpack_from('<i', d, o); o += 4
            o += 4 * nb + nb * sw * sh
    o += nverts * 12 + ntris * 16
    frames = []
    for _ in range(nframes):
        t, = struct.unpack_from('<i', d, o); o += 4
        if t == 0:
            name = d[o + 8:o + 24].split(b'\0')[0].decode('latin-1')
            o += 24
            vb = d[o:o + nverts * 4]; o += nverts * 4
            frames.append((name, vb))
        else:
            nb, = struct.unpack_from('<i', d, o); o += 4 + 8 + 4 * nb
            for _ in range(nb):
                name = d[o + 8:o + 24].split(b'\0')[0].decode('latin-1')
                o += 24
                vb = d[o:o + nverts * 4]; o += nverts * 4
                frames.append((name, vb))
    name, vb = frames[frame_index]
    pts = []
    for i in range(nverts):
        x, y, z, _n = vb[i * 4:i * 4 + 4]
        pts.append((scale[0] * x + trans[0], scale[1] * y + trans[1], scale[2] * z + trans[2]))
    info = f'MDL v{ver} verts {nverts} tris {ntris} frames {len(frames)} (using {frame_index} "{name}")'
    return pts, info, None

def qmul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by, aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw, aw*bw - ax*bx - ay*by - az*bz)

def qrot(q, v):
    x, y, z, w = q; vx, vy, vz = v
    tx = 2*(y*vz - z*vy); ty = 2*(z*vx - x*vz); tz = 2*(x*vy - y*vx)
    return (vx + w*tx + (y*tz - z*ty), vy + w*ty + (z*tx - x*tz), vz + w*tz + (x*ty - y*tx))

def read_iqm(path, mesh_filter):
    d = open(path, 'rb').read()
    assert d[:16] == b'INTERQUAKEMODEL\0'
    H = struct.unpack_from('<27I', d, 16)
    (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj,
     njoint, ojoint, npose, opose, nanim, oanim, nframe, nfch, oframe, obounds, ncom, ocom, next_, oext) = H
    def text(o):
        e = d.index(b'\0', otext + o); return d[otext + o:e].decode('latin-1')
    joints = []
    for i in range(njoint):
        v = struct.unpack_from('<Ii3f4f3f', d, ojoint + i * 48)
        joints.append((text(v[0]), v[1], v[2:5], v[5:9], v[9:12]))
    world = []
    for name, parent, t, r, s in joints:
        if parent < 0:
            world.append((t, r, s))
        else:
            pt, pr, ps = world[parent]
            lt = tuple(a*b for a, b in zip(t, ps))
            world.append((tuple(a + b for a, b in zip(pt, qrot(pr, lt))), qmul(pr, r), tuple(a*b for a, b in zip(ps, s))))
    jpos = {joints[i][0]: world[i][0] for i in range(njoint)}
    meshes = [struct.unpack_from('<6I', d, omesh + i * 24) for i in range(nmesh)]
    pos_ofs = None
    for i in range(nva):
        t, fl, fmt, size, o = struct.unpack_from('<5I', d, ova + i * 20)
        if t == 0:
            assert fmt == 7 and size == 3
            pos_ofs = o
    pts = []
    for mi, (n, m, fv, nv, ft, nt) in enumerate(meshes):
        if mesh_filter and mi not in mesh_filter:
            continue
        for v in range(fv, fv + nv):
            pts.append(struct.unpack_from('<3f', d, pos_ofs + v * 12))
    names = ', '.join(f'[{i}] {text(m[0])}' for i, m in enumerate(meshes))
    info = f'IQM v{ver} verts {nvert} joints {njoint} meshes {nmesh} ({names}); measured verts {len(pts)}'
    return pts, info, jpos

def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--frame', type=int, default=0)
    ap.add_argument('--meshes', default='')
    ap.add_argument('--axis', default='')
    ap.add_argument('--slices', type=int, default=16)
    ap.add_argument('--along', nargs=2)
    ap.add_argument('--top-band', type=float, default=0.0)
    ap.add_argument('--joints', default='')
    a = ap.parse_args()
    mf = {int(x) for x in a.meshes.split(',') if x}
    if a.file.lower().endswith('.mdl'):
        pts, info, jpos = read_mdl(a.file, a.frame)
    else:
        pts, info, jpos = read_iqm(a.file, mf)
    print(info)
    mins = [min(p[i] for p in pts) for i in range(3)]
    maxs = [max(p[i] for p in pts) for i in range(3)]
    print('bounds x [%.3f, %.3f]  y [%.3f, %.3f]  z [%.3f, %.3f]' % (mins[0], maxs[0], mins[1], maxs[1], mins[2], maxs[2]))
    print('size   x %.3f  y %.3f  z %.3f' % tuple(maxs[i] - mins[i] for i in range(3)))

    if jpos and a.joints:
        for jn in a.joints.split(','):
            p = jpos.get(jn)
            print(f'joint {jn}: ' + ('(%.3f, %.3f, %.3f)' % p if p else 'NOT FOUND'))

    if a.axis:
        ax = 'xyz'.index(a.axis)
        lat = [i for i in range(3) if i != ax]
        lo, hi = mins[ax], maxs[ax]
        step = (hi - lo) / a.slices
        print(f'\nPROFILE along {a.axis}: slice range, verts, centroid, lateral {"xyz"[lat[0]]} [min,max], {"xyz"[lat[1]]} [min,max]')
        for s in range(a.slices):
            s0, s1 = lo + s * step, lo + (s + 1) * step
            sl = [p for p in pts if s0 <= p[ax] <= s1]
            if not sl:
                print('  %8.3f..%8.3f  0' % (s0, s1)); continue
            c = [sum(p[i] for p in sl) / len(sl) for i in range(3)]
            print('  %8.3f..%8.3f  %6d  (%.2f, %.2f, %.2f)  %s[%.2f, %.2f]  %s[%.2f, %.2f]' % (
                s0, s1, len(sl), c[0], c[1], c[2],
                'xyz'[lat[0]], min(p[lat[0]] for p in sl), max(p[lat[0]] for p in sl),
                'xyz'[lat[1]], min(p[lat[1]] for p in sl), max(p[lat[1]] for p in sl)))

    if a.along:
        A, B = jpos[a.along[0]], jpos[a.along[1]]
        u = sub(B, A); L = norm(u); u = tuple(x / L for x in u)
        print(f'\nALONG {a.along[0]} -> {a.along[1]}  length {L:.3f}: t band, verts, mean radius, max radius')
        bands = a.slices
        for s in range(-2, bands + 3):
            t0, t1 = s / bands, (s + 1) / bands
            rs = []
            for p in pts:
                w = sub(p, A); t = dot(w, u) / L
                if t0 <= t < t1:
                    perp = sub(w, tuple(x * dot(w, u) for x in u))
                    rs.append(norm(perp))
            if rs:
                print('  t %5.2f..%5.2f  %6d  mean %.3f  max %.3f' % (t0, t1, len(rs), sum(rs) / len(rs), max(rs)))

    if a.top_band > 0:
        zlo = maxs[2] - (maxs[2] - mins[2]) * a.top_band
        band = [p for p in pts if p[2] >= zlo]
        print(f'\nTOP BAND z >= {zlo:.3f}: {len(band)} verts')
        for i, nm in ((0, 'x'), (1, 'y')):
            lo = min(band, key=lambda p: p[i]); hi = max(band, key=lambda p: p[i])
            print(f'  extreme -{nm}: (%.2f, %.2f, %.2f)   extreme +{nm}: (%.2f, %.2f, %.2f)' % (lo + hi))
        # outer shoulder clusters: widest 10% of the band on each side of y
        ys = sorted(p[1] for p in band)
        cut = max(1, len(ys) // 10)
        for side, sel in (('+y', [p for p in band if p[1] >= ys[-cut]]), ('-y', [p for p in band if p[1] <= ys[cut - 1]])):
            c = [sum(p[i] for p in sel) / len(sel) for i in range(3)]
            print(f'  outer 10%% {side}: {len(sel)} verts, centroid (%.2f, %.2f, %.2f)' % tuple(c))

main()
