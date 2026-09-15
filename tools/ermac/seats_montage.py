"""Rebuild the two seat sheets (out/gun_seats_vanilla.png, out/gun_seats_plus.png) from renders already on disk,
one row per gun in seats.json order: side and under view, labelled with the gun, its hand, its seat and its grip."""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
seats = json.load(open(os.path.join(HERE, "seats.json")))
for group, title in (("vanilla", "Vanilla"), ("plus", "Vanilla+ extras (the Vanilla+ versions of Vanilla guns use the Vanilla props above)")):
    rows = [(p, s) for p, s in seats.items() if s["group"] == group
            and os.path.exists(os.path.join(HERE, "out", "seats", "%s_side.png" % p))]
    if not rows:
        continue
    fig, axes = plt.subplots(len(rows), 2, figsize=(10, 3.9 * len(rows)), dpi=60)
    for i, (prop, s) in enumerate(rows):
        seat = s["new"] if s.get("new") else s["old"]
        for j, view in enumerate(("side", "under")):
            ax = axes[i, j]; ax.set_axis_off()
            ax.imshow(plt.imread(os.path.join(HERE, "out", "seats", "%s_%s.png" % (prop, view)))[60:900, 100:1180])
            ax.set_title("%s (%s hand) seat %s, %s" % (prop.replace("WM_Prop", ""), s["hand"], [round(float(v), 1) for v in seat], view), fontsize=11)
    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.995))
    fig.savefig(os.path.join(HERE, "out", "gun_seats_%s.png" % group))
    print("wrote out/gun_seats_%s.png (%d guns)" % (group, len(rows)))
