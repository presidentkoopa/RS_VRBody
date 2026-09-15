# Mockup: the Classic marine's torso + shoulder pads + arms (hands cut) + RS hands at the wrists, in the three
# armour colours. Headless Blender, scratch only. Built from tools/body/compose_mockup.py (Slayer version).
# blender -b --factory-startup -P marine_mockup.py -- OUT_DIR IQM_DIR TEX_DIR HEAD_TEX HAND_IQM HAND_TEX
#
# Frame: the Source / Slayer file frame -- +X left, -Y forward, +Z up, map units (marine already scaled 0.872).
# Arms are skinned on the CPU (rigid upper / lower arm turns) for the reaching shots. The RS hand is rigid, placed
# as compose_mockup.py places it: stub end 1 map unit inside the wrist, fingers along the forearm, palm plane
# from the index-to-pinky knuckle line.
import bpy, sys, os, struct
from mathutils import Vector, Quaternion, Matrix

A = sys.argv[sys.argv.index('--') + 1:]
OUT, IQM_DIR, TEX_DIR, HEAD_TEX, HAND, HAND_TEX = A[:6]
# One colour per Blender process (7th argument): a single run over all three rendered green and then crashed
# (EXCEPTION_ACCESS_VIOLATION) setting up blue -- the meshes check clean, so the scene is not carried across.
COLOURS = A[6].split(',') if len(A) > 6 else ['green', 'blue', 'red']
os.makedirs(OUT, exist_ok=True)


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
    bidx = get(4, nvert, 'B') if 4 in arr else None
    bwt = get(5, nvert, 'B') if 5 in arr else None
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
    uvl = me.uv_layers.new()
    for poly in me.polygons:
        for k, li in enumerate(poly.loop_indices):
            uvl.data[li].uv = loop_uvs[poly.index][k]
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob


def clear_scene():
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob, do_unlink=True)
    for me in list(bpy.data.meshes): bpy.data.meshes.remove(me)
    for cam in list(bpy.data.cameras): bpy.data.cameras.remove(cam)


bpy.ops.wm.read_factory_settings(use_empty=True)
torso = read_iqm(os.path.join(IQM_DIR, 'marine_torso.iqm'))
arms = {'rt': read_iqm(os.path.join(IQM_DIR, 'marine_arm_rt.iqm')), 'lf': read_iqm(os.path.join(IQM_DIR, 'marine_arm_lf.iqm'))}
hand = read_iqm(HAND)
SK = arms['rt']                                     # every marine IQM carries the full 152-joint skeleton
J = {n: i for i, n in enumerate(SK['names'])}
children = {}
for i, p in enumerate(SK['parents']): children.setdefault(p, []).append(i)
def subtree(root):
    out, st = set(), [root]
    while st:
        j = st.pop(); out.add(j); st.extend(children.get(j, []))
    return out
SIDE = {'rt': 'R', 'lf': 'L'}


def tex_for(material_path, colour):
    base = os.path.splitext(os.path.basename(material_path))[0]
    if base == 'doomslayer_head':
        return HEAD_TEX
    return os.path.join(TEX_DIR, '%s_%s.png' % (base, colour))


def rigid(q, pivot):
    return Matrix.Translation(pivot) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pivot)


def pose_transforms(posed):
    T = [Matrix.Identity(4) for _ in SK['names']]
    sides = {}
    for s, sx in (('rt', -1.0), ('lf', 1.0)):
        c = SIDE[s]
        S = SK['jpos'][J['bip_upperArm_' + c]]; E = SK['jpos'][J['bip_lowerArm_' + c]]; W = SK['jpos'][J['bip_hand_' + c]]
        if posed:
            up_target = Vector((-sx * 0.30, -0.70, -0.65)).normalized()
            M_up = rigid((E - S).normalized().rotation_difference(up_target), S)
            E2 = M_up @ E; W1 = M_up @ W
            fore_target = Vector((-sx * 0.25, -0.96, 0.10)).normalized()
            M_el = rigid((W1 - E2).normalized().rotation_difference(fore_target), E2) @ M_up
        else:
            M_up = M_el = Matrix.Identity(4)
        for j in subtree(J['bip_upperArm_' + c]): T[j] = M_up
        for j in subtree(J['bip_lowerArm_' + c]): T[j] = M_el
        sides[s] = (M_el @ E, M_el @ W, M_el)
    return T, sides


def skinned(model, T):
    out = []
    for v, p in enumerate(model['pos']):
        pv = Vector(p); acc = Vector((0, 0, 0)); tw = 0.0
        for j, w in zip(model['bidx'][v], model['bwt'][v]):
            if w <= 0: continue
            w = w / 255.0; acc += (T[j] @ pv) * w; tw += w
        out.append(acc / tw if tw > 0 else pv)
    return out


def build_model(tag, model, P, colour):
    for (mn, mm, fv, nv, ft, nt) in model['meshes']:
        verts = P[fv:fv + nv]
        faces = [tuple(i - fv for i in model['tris'][t]) for t in range(ft, ft + nt)]
        uvs = [[(model['uv'][i][0], 1.0 - model['uv'][i][1]) for i in model['tris'][t]] for t in range(ft, ft + nt)]
        add_mesh(tag + '_' + mn, verts, faces, uvs, material(mm + '_' + colour, tex_for(mm, colour)))


K_HAND = 0.34
STUB_END_Z = 10.6
STUB_INSIDE = 1.0


def build_hand(side, elbow, wrist, M_el):
    c = SIDE[side]
    d = (wrist - elbow).normalized()
    a = M_el.to_3x3() @ (SK['jpos'][J['bip_index_1_' + c]] - SK['jpos'][J['bip_pinky_1_' + c]])
    a = (a - d * a.dot(d)).normalized()
    mirror = 1.0 if side == 'rt' else -1.0            # hand_left.iqm's file geometry is a right hand
    cz = -d
    cx = a if mirror > 0 else -a
    cy = cz.cross(cx)
    R = Matrix((cx, cy, cz)).transposed()
    P0 = wrist + d * (STUB_END_Z * K_HAND - STUB_INSIDE)
    verts = [P0 + R @ (Vector((mirror * p[0], p[1], p[2])) * K_HAND) for p in hand['pos']]
    faces = [tuple(t) for t in hand['tris']]
    if mirror < 0:
        faces = [(t[0], t[2], t[1]) for t in faces]
    uvs = [[(hand['uv'][i][0], 1.0 - hand['uv'][i][1]) for i in t] for t in faces]
    add_mesh('hand_' + side, verts, faces, uvs, material('rs_hand', HAND_TEX))


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


for colour in COLOURS:
    for posed in (False, True):
        clear_scene()
        T, sides = pose_transforms(posed)
        build_model('torso', torso, [Vector(p) for p in torso['pos']], colour)
        for s in ('rt', 'lf'):
            build_model('arm_' + s, arms[s], skinned(arms[s], T), colour)
            e, w, M = sides[s]
            build_hand(s, e, w, M)
        tag = os.path.join(OUT, 'marine_%s_%s' % (colour, 'reach' if posed else 'bind')).replace('\\', '/')
        shot('threeq', (-40, -52, 60), (0, -8, 45), 35, tag + '_threequarter.png')
        shot('side', (-60, -10, 48), (0, -8, 45), 35, tag + '_side.png')
        shot('firstperson', (0, 0.5, 60.5), (0, -18, 40), 14, tag + '_firstperson.png')
print('DONE')
