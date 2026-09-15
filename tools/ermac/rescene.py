import json, os
HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
TAGS = ["pinch", "claw", "fist", "splay", "point", "flat"]
for t in TAGS:
    sc = json.load(open(HERE + "/scene_fit_%s.json" % t))
    sc["shots"] = [{"file": HERE + "/out/fit2_%s_side.png" % t, "cam": [70.0, 10.0, -6.0], "look": [0.0, 0.0, -8.0], "lens": 60},
                   {"file": HERE + "/out/fit2_%s_palm.png" % t, "cam": [10.0, 70.0, -6.0], "look": [0.0, 0.0, -8.0], "lens": 60}]
    json.dump(sc, open(HERE + "/scene_fit2_%s.json" % t, "w"), indent=1)
print("ok")
