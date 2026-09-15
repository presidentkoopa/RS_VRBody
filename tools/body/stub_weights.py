import struct, collections
d = open('E:/DOOMWork/RS_WorldHands/models/hands/hand_left.iqm', 'rb').read()
h = struct.unpack_from('<27I', d, 16)
ntext, otext, nva, nvert, ova, njoint, ojoint = h[3], h[4], h[7], h[8], h[9], h[13], h[14]
text = d[otext:otext + ntext]
def s(o): return text[o:text.index(b'\0', o)].decode()
names = [s(struct.unpack_from('<I', d, ojoint + i * 48)[0]) for i in range(njoint)]
arr = {}
for i in range(nva):
    t, fl, f, sz, off = struct.unpack_from('<5I', d, ova + i * 20)
    arr[t] = (f, sz, off)
pos = [struct.unpack_from('<3f', d, arr[0][2] + v * 12) for v in range(nvert)]
ich = 'H' if arr[4][0] == 3 else 'B'; ib = 2 if ich == 'H' else 1
def infl(v):
    idx = struct.unpack_from('<4' + ich, d, arr[4][2] + v * 4 * ib)
    w = struct.unpack_from('<4B', d, arr[5][2] + v * 4)
    return idx, w
bands = [(-99, 0), (0, 2.5), (2.5, 5), (5, 7.5), (7.5, 11)]
for lo, hi in bands:
    dom = collections.Counter(); root_w = 0.0; n = 0
    for v in range(nvert):
        if not (lo <= pos[v][2] < hi): continue
        idx, w = infl(v); n += 1
        k = max(range(4), key=lambda i: w[i]); dom[names[idx[k]]] += 1
        root_w += sum(w[i] for i in range(4) if names[idx[i]] == 'Root_joint') / 255.0
    print('z [%5.1f,%5.1f): verts %4d  mean Root_joint weight %.2f  dominant %s' % (lo, hi, n, (root_w / n) if n else 0, dom.most_common(3)))
