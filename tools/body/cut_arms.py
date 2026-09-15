"""Cut an arms-only IQM out of a skinned IQM, byte-level, no Blender round trip.

usage: cut_arms.py SRC.iqm OUT.iqm --side rt|lf|both
         [--upper arm_upper] [--hand arm_hand] [--exclude shoulderarmor_result]
         [--keep-hand]

What it keeps
  Every triangle, from any mesh, whose three vertices are all DOMINATED (largest blend
  weight) by a joint inside the subtree of <upper>_<side>, minus the subtree of
  <hand>_<side> (unless --keep-hand) and minus any joint whose name starts with an
  --exclude prefix. Vertices no kept triangle uses are dropped; empty meshes are dropped.

What it does NOT touch
  Joints, poses, anims, frames, bounds, text, comments: copied byte for byte, so the
  bind pose and every pose frame are identical to the source. Joint indices in the
  kept vertices therefore stay valid. Adjacency is recomputed for the new triangles.

Why not Blender: the IQM importer brings mesh objects in with a rotation the armature
modifier cancels (export_slayer.py:118-125); a round trip re-bakes the bind pose and
the 1298-frame clip. A byte-level cut cannot change either.
"""
import struct, sys, argparse, collections

HDR = ['version', 'filesize', 'flags', 'num_text', 'ofs_text', 'num_meshes', 'ofs_meshes',
       'num_vertexarrays', 'num_vertexes', 'ofs_vertexarrays', 'num_triangles', 'ofs_triangles',
       'ofs_adjacency', 'num_joints', 'ofs_joints', 'num_poses', 'ofs_poses', 'num_anims', 'ofs_anims',
       'num_frames', 'num_framechannels', 'ofs_frames', 'ofs_bounds', 'num_comment', 'ofs_comment',
       'num_extensions', 'ofs_extensions']
FMT_BYTES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 2, 7: 4, 8: 8}
FMT_CHAR = {0: 'b', 1: 'B', 2: 'h', 3: 'H', 4: 'i', 5: 'I', 7: 'f', 8: 'd'}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('out')
    ap.add_argument('--side', choices=['rt', 'lf', 'both'], required=True)
    ap.add_argument('--upper', default='arm_upper')
    ap.add_argument('--hand', default='arm_hand')
    ap.add_argument('--exclude', action='append', default=None)
    ap.add_argument('--keep-hand', action='store_true')
    ap.add_argument('--hand-weight-max', type=float, default=1.01,
                    help='also drop vertices whose total weight on the hand subtree is at or above this '
                         '(removes thin slivers left at the cuff by triangles only partly skinned to the hand)')
    a = ap.parse_args()
    excludes = a.exclude if a.exclude is not None else ['shoulderarmor_result']

    d = open(a.src, 'rb').read()
    assert d[:16] == b'INTERQUAKEMODEL\0', 'not an IQM'
    h = dict(zip(HDR, struct.unpack_from('<27I', d, 16)))
    assert h['version'] == 2
    if h['num_extensions']:
        sys.exit('source has extensions; their internal offsets would break -- refusing')

    text = d[h['ofs_text']:h['ofs_text'] + h['num_text']]
    def name(o): return text[o:text.index(b'\0', o)].decode('latin-1')

    # joints (names + parents only; the joint block itself is copied raw)
    jname, jparent = [], []
    for i in range(h['num_joints']):
        n, p = struct.unpack_from('<Ii', d, h['ofs_joints'] + i * 48)
        jname.append(name(n)); jparent.append(p)
    children = collections.defaultdict(list)
    for i, p in enumerate(jparent): children[p].append(i)
    def subtree(root):
        out, st = set(), [root]
        while st:
            j = st.pop(); out.add(j); st.extend(children[j])
        return out
    index = {n: i for i, n in enumerate(jname)}

    sides = ['rt', 'lf'] if a.side == 'both' else [a.side]
    keep_joints = set()
    for s in sides:
        up = index.get(f'{a.upper}_{s}')
        if up is None: sys.exit(f'joint {a.upper}_{s} not found')
        sub = subtree(up)
        if not a.keep_hand:
            hd = index.get(f'{a.hand}_{s}')
            if hd is None: sys.exit(f'joint {a.hand}_{s} not found')
            sub -= subtree(hd)
        keep_joints |= sub
    keep_joints = {j for j in keep_joints if not any(jname[j].startswith(x) for x in excludes)}

    # vertex arrays
    arrays = []
    for i in range(h['num_vertexarrays']):
        t, fl, fmt, size, ofs = struct.unpack_from('<5I', d, h['ofs_vertexarrays'] + i * 20)
        arrays.append(dict(type=t, flags=fl, format=fmt, size=size, ofs=ofs, stride=size * FMT_BYTES[fmt]))
    by_type = {ar['type']: ar for ar in arrays}
    bi, bw = by_type[4], by_type[5]
    nv = h['num_vertexes']

    def dominant(v):
        idx = struct.unpack_from('<' + FMT_CHAR[bi['format']] * bi['size'], d, bi['ofs'] + v * bi['stride'])
        wts = struct.unpack_from('<' + FMT_CHAR[bw['format']] * bw['size'], d, bw['ofs'] + v * bw['stride'])
        best = max(range(len(wts)), key=lambda k: wts[k])
        return idx[best] if wts[best] > 0 else -1

    hand_set = set()
    if not a.keep_hand:
        for s in sides: hand_set |= subtree(index[f'{a.hand}_{s}'])
    def hand_weight(v):
        idx = struct.unpack_from('<' + FMT_CHAR[bi['format']] * bi['size'], d, bi['ofs'] + v * bi['stride'])
        wts = struct.unpack_from('<' + FMT_CHAR[bw['format']] * bw['size'], d, bw['ofs'] + v * bw['stride'])
        tot = float(sum(wts)) or 1.0
        return sum(w for j, w in zip(idx, wts) if j in hand_set) / tot

    vkeep = [dominant(v) in keep_joints and hand_weight(v) < a.hand_weight_max for v in range(nv)]

    # meshes and triangles
    meshes = [struct.unpack_from('<6I', d, h['ofs_meshes'] + i * 24) for i in range(h['num_meshes'])]
    tris = struct.unpack_from('<%dI' % (h['num_triangles'] * 3), d, h['ofs_triangles'])

    new_meshes, new_tris, vert_order = [], [], []
    remap = {}
    report = []
    for (mn, mm, fv, mnv, ft, mnt) in meshes:
        kept = []
        for t in range(ft, ft + mnt):
            tv = tris[t * 3:t * 3 + 3]
            if all(vkeep[v] for v in tv): kept.append(tv)
        if not kept:
            continue
        first_v = len(vert_order)
        used = sorted({v for tv in kept for v in tv})
        for v in used:
            remap[v] = len(vert_order); vert_order.append(v)
        first_t = len(new_tris)
        for tv in kept:
            new_tris.append(tuple(remap[v] for v in tv))
        new_meshes.append((mn, mm, first_v, len(used), first_t, len(kept)))
        report.append(f'  {name(mn):<12} {name(mm):<44} tris {len(kept):>6}/{mnt:<6} verts {len(used):>6}/{mnv}')

    if not new_tris: sys.exit('nothing kept')

    # adjacency: neighbour across edge k (vertex k -> k+1), 0xFFFFFFFF if none
    edges = collections.defaultdict(list)
    for ti, tv in enumerate(new_tris):
        for k in range(3):
            edges[frozenset((tv[k], tv[(k + 1) % 3]))].append(ti)
    adj = []
    for ti, tv in enumerate(new_tris):
        for k in range(3):
            others = [o for o in edges[frozenset((tv[k], tv[(k + 1) % 3]))] if o != ti]
            adj.append(others[0] if others else 0xFFFFFFFF)

    # assemble
    out = bytearray(124)
    def put(blob):
        ofs = len(out); out.extend(blob); return ofs
    nh = dict(h)
    nh['ofs_text'] = put(text)
    nh['num_meshes'] = len(new_meshes)
    nh['ofs_meshes'] = put(b''.join(struct.pack('<6I', *m) for m in new_meshes))
    nh['num_vertexes'] = len(vert_order)
    va_hdr_ofs = put(bytes(20 * len(arrays)))
    nh['ofs_vertexarrays'] = va_hdr_ofs
    for i, ar in enumerate(arrays):
        blob = b''.join(d[ar['ofs'] + v * ar['stride']:ar['ofs'] + (v + 1) * ar['stride']] for v in vert_order)
        ofs = put(blob)
        struct.pack_into('<5I', out, va_hdr_ofs + i * 20, ar['type'], ar['flags'], ar['format'], ar['size'], ofs)
    nh['num_triangles'] = len(new_tris)
    nh['ofs_triangles'] = put(struct.pack('<%dI' % (len(new_tris) * 3), *[v for tv in new_tris for v in tv]))
    nh['ofs_adjacency'] = put(struct.pack('<%dI' % len(adj), *adj))
    def copy(count_key, ofs_key, stride):
        n = h[count_key]
        if n == 0 or h[ofs_key] == 0:
            nh[ofs_key] = 0; return
        nh[ofs_key] = put(d[h[ofs_key]:h[ofs_key] + n * stride])
    copy('num_joints', 'ofs_joints', 48)
    copy('num_poses', 'ofs_poses', 88)
    copy('num_anims', 'ofs_anims', 20)
    nh['ofs_frames'] = put(d[h['ofs_frames']:h['ofs_frames'] + h['num_frames'] * h['num_framechannels'] * 2]) if h['num_frames'] else 0
    nh['ofs_bounds'] = put(d[h['ofs_bounds']:h['ofs_bounds'] + h['num_frames'] * 32]) if h['ofs_bounds'] else 0
    copy('num_comment', 'ofs_comment', 1)
    nh['filesize'] = len(out)
    out[:16] = b'INTERQUAKEMODEL\0'
    struct.pack_into('<27I', out, 16, *[nh[k] for k in HDR])
    open(a.out, 'wb').write(out)

    print(f'side {a.side}: kept joints {len(keep_joints)} (excluded prefixes {excludes}, hand {"kept" if a.keep_hand else "cut"})')
    print('\n'.join(report))
    print(f'wrote {a.out}: {len(new_meshes)} meshes, {len(vert_order)} verts, {len(new_tris)} tris, '
          f'{sum(1 for x in adj if x == 0xFFFFFFFF)} open edges, {len(out)} bytes')

main()
