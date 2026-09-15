"""Blender (5.1) render of the finger-contact mockup. Run:
  blender -b --python render.py -- SCENE.json

SCENE.json: {"objs": [{"path": ..., "texture": ...}, ...],
             "shots": [{"file": ..., "cam": [x,y,z], "look": [x,y,z], "lens": 35}, ...]}
All geometry already posed and placed by the Python side; this only draws it.
"""
import json, sys
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
scene_desc = json.load(open(args[0]))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.display.shading.show_backface_culling = False
scene.render.resolution_x = 1280
scene.render.resolution_y = 960
world = bpy.data.worlds.new("w")
scene.world = world
world.color = (0.25, 0.25, 0.28)


def material(name, tex):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if tex:
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(tex)
        nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
    return m


for i, o in enumerate(scene_desc["objs"]):
    before = set(bpy.data.objects)
    bpy.ops.wm.obj_import(filepath=o["path"], forward_axis="Y", up_axis="Z")
    mat = material("m%d" % i, o.get("texture"))
    for ob in set(bpy.data.objects) - before:
        if ob.type == "MESH":
            ob.data.materials.clear()
            ob.data.materials.append(mat)

for s in scene_desc["shots"]:
    cam = bpy.data.cameras.new(s["file"])
    co = bpy.data.objects.new(s["file"], cam)
    scene.collection.objects.link(co)
    co.location = s["cam"]
    co.rotation_euler = (Vector(s["look"]) - Vector(s["cam"])).normalized().to_track_quat("-Z", "Y").to_euler()
    cam.lens = s.get("lens", 35)
    cam.clip_start = 0.05
    cam.clip_end = 10000
    scene.camera = co
    scene.render.filepath = s["file"]
    bpy.ops.render.render(write_still=True)
    print("RENDERED", s["file"])
print("DONE")
