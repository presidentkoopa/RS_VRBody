# Mockup: quake torso + Slayer arms (cut) + RS hands in the cuffs. Headless Blender, scratch only.
# blender -b --factory-startup -P compose_mockup.py -- OUT_PREFIX ARMS_IQM HAND_IQM HAND_TEX TORSO_MDL TORSO_TEX
#
# Frame: the Slayer file frame -- +X left, -Y forward, +Z up, map units.
# Arms are skinned on the CPU (linear blend) for the posed shots. The hand is rigid, placed so its
# forearm stub end sits 1 map unit inside the Slayer wrist cuff and its fingers point along the forearm.
import bpy, sys, os, struct, math
from mathutils import Vector, Quaternion, Matrix

A = sys.argv[sys.argv.index('--') + 1:]
OUT, ARMS, HAND, HAND_TEX, TORSO, TORSO_TEX = A[:6]
TORSO_YAWS = [int(x) for x in (A[6] if len(A) > 6 else '180,0').split(',')]

# ------------------------------------------------------------------ readers
def read_iqm(path):
    d = open(path, 'rb').read()
    h = struct.unpack_from('<27I', d, 16)
    (ver, fsize, flags, ntext, otext, nmesh, omesh, nva, nvert, ova, ntri, otri, oadj, njoint, ojoint,
     npose, opose, nanim, oanim, nframe, nfc, oframe, obounds, ncom, ocom, next_, oext) = h
    text = d[otext:otext + ntext]
    def s(o): return text[o:text.index(b'\0', o)].decode('latin-1')
    arr = {}
    for i in range(nva):
        t, fl, f, sz, off = struct.unpack_from('<5I', d, ova + i * 20)
        arr[t] = (f, sz, off)
    def get(t, n, ch):
        f, sz, off = arr[t]
        return [struct.unpack_from('<' + ch * sz, d, off + v * sz * struct.calcsize(ch)) for v in range(n)]
    pos = get(0, nvert, 'f')
    uv = get(1, nvert, 'f') if 1 in arr else None
    bidx = get(4, nvert, 'H' if arr[4][0] == 3 else 'B') if 4 in arr else None
    bwt = get(5, nvert, 'B' if arr[5][0] == 1 else 'f') if 5 in arr else None
    tris = [struct.unpack_from('<3I', d, otri + i * 12) for i in range(ntri)]
    meshes = []
    for i in range(nmesh):
        n, m, fv, nv, ft, nt = struct.unpack_from('<6I', d, omesh + i * 24)
        meshes.append((s(n), s(m), fv, nv, ft, nt))
    joints = []
    for i in range(njoint):
        v = struct.unpack_from('<Ii3f4f3f', d, ojoint + i * 48)
        joints.append((s(v[0]), v[1], v[2:5], v[5:9], v[9:12]))
    wp, wr, ws = [], [], []
    for nm, par, t, r, sc in joints:
        q = Quaternion((r[3], r[0], r[1], r[2])); tv = Vector(t); sv = Vector(sc)
        if par < 0:
            wp.append(tv); wr.append(q); ws.append(sv)
        else:
            lt = Vector((tv.x * ws[par].x, tv.y * ws[par].y, tv.z * ws[par].z))
            wp.append(wp[par] + wr[par] @ lt); wr.append(wr[par] @ q)
            ws.append(Vector((sv.x * ws[par].x, sv.y * ws[par].y, sv.z * ws[par].z)))
    return dict(pos=pos, uv=uv, bidx=bidx, bwt=bwt, tris=tris, meshes=meshes,
                names=[j[0] for j in joints], parents=[j[1] for j in joints], jpos=wp)

def read_mdl(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'IDPO'
    scale = struct.unpack_from('<3f', d, 8); trans = struct.unpack_from('<3f', d, 20)
    nskins, sw, sh, nverts, ntris, nframes = struct.unpack_from('<6i', d, 48)
    o = 84
    for _ in range(nskins):
        g, = struct.unpack_from('<i', d, o); o += 4
        if g == 0: o += sw * sh
        else:
            nb, = struct.unpack_from('<i', d, o); o += 4 + 4 * nb + nb * sw * sh
    st = [struct.unpack_from('<3i', d, o + i * 12) for i in range(nverts)]; o += nverts * 12
    tris = [struct.unpack_from('<4i', d, o + i * 16) for i in range(ntris)]; o += ntris * 16
    t, = struct.unpack_from('<i', d, o); o += 4
    assert t == 0, 'group frame first; not handled'
    o += 24
    vb = d[o:o + nverts * 4]
    pos = [tuple(scale[k] * vb[i * 4 + k] + trans[k] for k in range(3)) for i in range(nverts)]
    return pos, st, tris, sw, sh

# ------------------------------------------------------------------ scene helpers
mats = {}
def material(key, tex):
    if key in mats: return mats[key]
    m = bpy.data.materials.new(key); m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    if tex and os.path.exists(tex) and bsdf:
        node = m.node_tree.nodes.new('ShaderNodeTexImage'); node.image = bpy.data.images.load(tex, check_existing=True)
        m.node_tree.links.new(node.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        print('NO TEXTURE for', key, tex)
    mats[key] = m
    return m

def add_mesh(name, verts, faces, loop_uvs, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    if loop_uvs is not None:
        uvl = me.uv_layers.new()
        li = 0
        for poly in me.polygons:
            for k, loop_index in enumerate(poly.loop_indices):
                uvl.data[loop_index].uv = loop_uvs[poly.index][k]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob

def clear_scene():
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes): bpy.data.meshes.remove(me)
    for cam in list(bpy.data.cameras): bpy.data.cameras.remove(cam)

# ------------------------------------------------------------------ data
bpy.ops.wm.read_factory_settings(use_empty=True)
arms = read_iqm(ARMS)
hand = read_iqm(HAND)
tpos, tst, ttris, tsw, tsh = read_mdl(TORSO)
J = {n: i for i, n in enumerate(arms['names'])}
children = {}
for i, p in enumerate(arms['parents']): children.setdefault(p, []).append(i)
def subtree(root):
    out, stck = set(), [root]
    while stck:
        j = stck.pop(); out.add(j); stck.extend(children.get(j, []))
    return out

def rigid(q, pivot):
    return Matrix.Translation(pivot) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pivot)

def pose_transforms(posed):
    """per-joint 4x4 and per-side (elbow, wrist, forearm rotation) for the hands"""
    T = [Matrix.Identity(4) for _ in arms['names']]
    sides = {}
    for s, sx in (('rt', -1.0), ('lf', 1.0)):
        S = arms['jpos'][J['arm_upper_' + s]]; E = arms['jpos'][J['arm_lower_' + s]]; W = arms['jpos'][J['arm_hand_' + s]]
        if posed:
            up_target = Vector((-sx * 0.30, -0.70, -0.65)).normalized()   # forward, down, a little inward
            Q_up = (E - S).normalized().rotation_difference(up_target)
            M_up = rigid(Q_up, S)
            E2 = M_up @ E; W1 = M_up @ W
            fore_target = Vector((-sx * 0.25, -0.96, 0.10)).normalized()   # forward, slightly in and up
            Q_el = (W1 - E2).normalized().rotation_difference(fore_target)
            M_el = rigid(Q_el, E2) @ M_up
        else:
            M_up = M_el = Matrix.Identity(4); E2 = E
        low = subtree(J['arm_lower_' + s]); up = subtree(J['arm_upper_' + s])
        for j in up: T[j] = M_up
        for j in low: T[j] = M_el
        sides[s] = (M_el @ E, M_el @ W, M_el)
    return T, sides

def skinned_positions(T):
    out = []
    for v, p in enumerate(arms['pos']):
        pv = Vector(p); acc = Vector((0, 0, 0)); tw = 0.0
        for j, w in zip(arms['bidx'][v], arms['bwt'][v]):
            if w <= 0: continue
            w = w / 255.0; acc += (T[j] @ pv) * w; tw += w
        out.append(acc / tw if tw > 0 else pv)
    return out

def build_arms(T):
    P = skinned_positions(T)
    armdir = os.path.dirname(ARMS)
    for (mn, mm, fv, nv, ft, nt) in arms['meshes']:
        verts = P[fv:fv + nv]
        faces = [tuple(i - fv for i in arms['tris'][t]) for t in range(ft, ft + nt)]
        uvs = [[(arms['uv'][i][0], 1.0 - arms['uv'][i][1]) for i in arms['tris'][t]] for t in range(ft, ft + nt)]
        add_mesh('arm_' + mn, verts, faces, uvs, material(mm, os.path.join(armdir, os.path.basename(mm))))

K_HAND = 0.34          # model units -> map units on the world-hand path at Scale 1.0
STUB_END_Z = 10.6      # forearm stub end, model units (+z)
STUB_INSIDE = 1.0      # map units of stub pushed inside the cuff

def build_hand(side, elbow, wrist, M_el):
    d = (wrist - elbow).normalized()
    a = (arms['jpos'][J['index_part02_' + side]] - arms['jpos'][J['pinky_part02_' + side]])
    a = M_el.to_3x3() @ a
    a = (a - d * a.dot(d)).normalized()
    # hand_left.iqm's FILE geometry is a right hand (fingers curl and thumb sit toward +y with index at +x,
    # fingers -z). The engine draws it as the left hand; outside the engine it is the right, so the
    # LEFT arm gets the mirror here. (First mockup had this backwards -- owner spotted it.)
    mirror = 1.0 if side == 'rt' else -1.0
    cz = -d                                     # model +z (toward the stub) points back up the forearm
    cx = a if mirror > 0 else -a                # model +x is the index side; mirrored, the index is at -x
    cy = cz.cross(cx)
    R = Matrix((cx, cy, cz)).transposed()
    P0 = wrist + d * (STUB_END_Z * K_HAND - STUB_INSIDE)
    verts = [P0 + R @ (Vector((mirror * p[0], p[1], p[2])) * K_HAND) for p in hand['pos']]
    faces = [tuple(t) for t in hand['tris']]
    uvs = [[(hand['uv'][i][0], 1.0 - hand['uv'][i][1]) for i in t] for t in hand['tris']]
    add_mesh('hand_' + side, verts, faces, uvs, material('rs_hand', HAND_TEX))

# quake torso: fit from the owner's ini (scale 0.75, z 1.4); the shoulder estimate from plan 3c,
# model (-1.3, +-9, 13), is put on the Slayer shoulder centre (0, 1.27, 51.71)
def build_torso(yaw):
    sxy, sz = 0.75, 0.75 * 1.4
    def xf(p):
        x, y, z = p
        if yaw == 180: X, Y = -sxy * y, sxy * x
        else:          X, Y = sxy * y, -sxy * x
        return Vector((X, Y, sz * z))
    sh = xf((-1.3, 0.0, 13.0))
    off = Vector((0.0, 1.27, 51.71)) - sh
    verts = [xf(p) + off for p in tpos]
    faces, uvs = [], []
    for ff, a, b, c in ttris:
        faces.append((a, b, c))
        tri_uv = []
        for vi in (a, b, c):
            onseam, s_, t_ = tst[vi]
            if onseam and not ff: s_ += tsw // 2
            tri_uv.append(((s_ + 0.5) / tsw, 1.0 - (t_ + 0.5) / tsh))
        uvs.append(tri_uv)
    add_mesh('torso', verts, faces, uvs, material('torso', TORSO_TEX))

# ------------------------------------------------------------------ render
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'TEXTURE'
scene.display.shading.show_backface_culling = False
scene.render.resolution_x = 1280; scene.render.resolution_y = 960
world = bpy.data.worlds.new('w'); scene.world = world; world.color = (0.25, 0.25, 0.28)

def shot(name, loc, look, lens, fname):
    cam = bpy.data.cameras.new(name); co = bpy.data.objects.new(name, cam); scene.collection.objects.link(co)
    co.location = loc
    co.rotation_euler = (Vector(look) - Vector(loc)).normalized().to_track_quat('-Z', 'Y').to_euler()
    cam.lens = lens; cam.clip_start = 0.05; cam.clip_end = 10000
    scene.camera = co; scene.render.filepath = fname
    bpy.ops.render.render(write_still=True); print('RENDERED', fname)

for yaw in TORSO_YAWS:
    for posed in (False, True):
        clear_scene()
        T, sides = pose_transforms(posed)
        build_arms(T)
        for s in ('rt', 'lf'):
            e, w, M = sides[s]
            build_hand(s, e, w, M)
        build_torso(yaw)
        tag = f"{OUT}_yaw{yaw}_{'reach' if posed else 'bind'}"
        shot('threeq', (-40, -52, 60), (0, -8, 45), 35, tag + '_threequarter.png')
        shot('side', (-60, -10, 48), (0, -8, 45), 35, tag + '_side.png')
        shot('firstperson', (0, 0.5, 60.5), (0, -18, 40), 14, tag + '_firstperson.png')
print('DONE')
