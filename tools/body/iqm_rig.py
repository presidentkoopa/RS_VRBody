import struct, sys, math, re, collections

PATH = sys.argv[1]
data = open(PATH, 'rb').read()

magic = data[:16]
H = struct.unpack_from('<27I', data, 16)
names = ['version','filesize','flags','num_text','ofs_text','num_meshes','ofs_meshes',
         'num_vertexarrays','num_vertexes','ofs_vertexarrays','num_triangles','ofs_triangles',
         'ofs_adjacency','num_joints','ofs_joints','num_poses','ofs_poses','num_anims','ofs_anims',
         'num_frames','num_framechannels','ofs_frames','ofs_bounds','num_comment','ofs_comment',
         'num_extensions','ofs_extensions']
h = dict(zip(names, H))
print('magic', magic, 'file bytes', len(data))
for k in ['version','filesize','num_meshes','num_vertexes','num_triangles','num_joints','num_poses','num_anims','num_frames']:
    print(f'  {k} = {h[k]}')

def text(o):
    base = h['ofs_text']
    end = data.index(b'\0', base + o)
    return data[base + o:end].decode('latin-1')

# joints: name, parent, t[3], r[4], s[3]
joints = []
for i in range(h['num_joints']):
    v = struct.unpack_from('<Ii3f4f3f', data, h['ofs_joints'] + i * 48)
    joints.append(dict(name=text(v[0]), parent=v[1], t=v[2:5], r=v[5:9], s=v[9:12]))

def qmul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return (aw*bx + ax*bw + ay*bz - az*by,
            aw*by - ax*bz + ay*bw + az*bx,
            aw*bz + ax*by - ay*bx + az*bw,
            aw*bw - ax*bx - ay*by - az*bz)

def qrot(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v)
    tx = 2*(y*vz - z*vy); ty = 2*(z*vx - x*vz); tz = 2*(x*vy - y*vx)
    return (vx + w*tx + (y*tz - z*ty), vy + w*ty + (z*tx - x*tz), vz + w*tz + (x*ty - y*tx))

world = [None]*len(joints)
for i, j in enumerate(joints):
    if j['parent'] < 0:
        world[i] = (j['t'], j['r'], j['s'])
    else:
        pt, pr, ps = world[j['parent']]
        lt = tuple(a*b for a, b in zip(j['t'], ps))
        wt = tuple(a + b for a, b in zip(pt, qrot(pr, lt)))
        world[i] = (wt, qmul(pr, j['r']), tuple(a*b for a, b in zip(ps, j['s'])))

def dist(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))

children = collections.defaultdict(list)
for i, j in enumerate(joints):
    children[j['parent']].append(i)

# meshes
meshes = []
for i in range(h['num_meshes']):
    n, m, fv, nv, ft, nt = struct.unpack_from('<6I', data, h['ofs_meshes'] + i*24)
    meshes.append(dict(name=text(n), material=text(m), fv=fv, nv=nv, nt=nt))

# vertex arrays
va = {}
for i in range(h['num_vertexarrays']):
    t, fl, fmt, size, ofs = struct.unpack_from('<5I', data, h['ofs_vertexarrays'] + i*20)
    va[t] = (fmt, size, ofs)
print('vertex arrays (type: format,size):', {k: v[:2] for k, v in va.items()})

fmtmap = {1: ('B', 1), 3: ('H', 2), 5: ('I', 4)}
idx_fmt, idx_size, idx_ofs = va[4]
w_fmt, w_size, w_ofs = va[5]
ic, ib = fmtmap[idx_fmt]
wc = 'B' if w_fmt == 1 else 'f'
wb = 1 if w_fmt == 1 else 4

def influences(v):
    idx = struct.unpack_from('<' + ic*idx_size, data, idx_ofs + v*idx_size*ib)
    wts = struct.unpack_from('<' + wc*w_size, data, w_ofs + v*w_size*wb)
    return [(a, b) for a, b in zip(idx, wts) if b > 0]

mesh_joints = []
joint_meshes = collections.defaultdict(set)
joint_vcount = collections.Counter()
for mi, m in enumerate(meshes):
    js = collections.Counter()
    for v in range(m['fv'], m['fv'] + m['nv']):
        for a, _ in influences(v):
            js[a] += 1
            joint_meshes[a].add(mi)
            joint_vcount[a] += 1
    mesh_joints.append(js)

print('\nMESHES')
for mi, m in enumerate(meshes):
    top = ', '.join(joints[a]['name'] for a, _ in mesh_joints[mi].most_common(4))
    print(f"  [{mi:2}] {m['name']:<32} verts {m['nv']:>6} tris {m['nt']:>6} joints used {len(mesh_joints[mi]):>3}  top: {top}")

skinned = sum(1 for i in range(len(joints)) if joint_vcount[i] > 0)
print(f'\njoints that move any vertex: {skinned} of {len(joints)}')

print('\nANIMS')
for i in range(h['num_anims']):
    n, ff, nf, fr, fl = struct.unpack_from('<3IfI', data, h['ofs_anims'] + i*20)
    print(f'  {text(n)} first {ff} frames {nf} rate {fr}')

pat = re.compile(sys.argv[2] if len(sys.argv) > 2 else r'arm|clav|shoulder|hand|wrist|elbow|twist|roll|neck|spine|hip|leg|knee|foot|pelvis|head', re.I)

def chain(i):
    out = []
    while i >= 0:
        out.append(joints[i]['name']); i = joints[i]['parent']
    return ' < '.join(out[:6])

print('\nBODY JOINTS (index, name, parent, children, bind world pos, dist to parent, verts moved, meshes)')
for i, j in enumerate(joints):
    if not pat.search(j['name']):
        continue
    p = j['parent']
    d = dist(world[i][0], world[p][0]) if p >= 0 else 0
    kids = ','.join(joints[c]['name'] for c in children[i][:4])
    wp = world[i][0]
    print(f"  {i:4} {j['name']:<34} parent {joints[p]['name'] if p>=0 else '-':<30} "
          f"pos ({wp[0]:8.2f},{wp[1]:8.2f},{wp[2]:8.2f}) len {d:7.2f} verts {joint_vcount[i]:6} "
          f"meshes {sorted(joint_meshes[i])} kids [{kids}]")

print('\nROOT CHAIN of first match per side:')
for key in ['hand_rt', 'hand_lf', 'foot_rt', 'foot_lf']:
    for i, j in enumerate(joints):
        if key in j['name'].lower():
            print(f'  {key}: {chain(i)}')
            break
