"""Seat every Vanilla and Vanilla+ gun in the hand: move its trigger onto the trigger of a gun that already sits right.

REFERENCES (the owner's tuned seats, checked in renders): the M4A3 on wm_main for the main hand, the Pistolet on
wm_off for the off hand. Their trigger surface centroid, through the engine chain with the owner's ini seat, is
where a trigger belongs relative to that controller.

PER GUN: its card's trigger surface (or a hand-picked landmark, LANDMARKS below, for meshes without one), through
the chain with its current seat; the seat's ofs_x/y/z then change by the gap. The placement offset moves a model by
exactly its own amount in engine axes (ingame_chain.py), so one step is exact. Yaw, pitch and roll are kept: every
gun still points the way it does today. A grip that rakes differently from a pistol's may still want a pitch or a
nudge -- the renders show that.

Writes seats.json: {prop: {"prefix", "hand", "old": [x,y,z], "new": [x,y,z], "landmark"}}.
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "E:/DOOMWork/tools")
import ingame_chain as ic
from md3 import MD3Model

# Props on the Vanilla and Vanilla+ sets (WM_VP_* guns use the Vanilla props). The three props being re-meshed
# (Chaingun, Rocket Launcher, BFG) wait for their new models.
VANILLA = ["WM_PropM4A3", "WM_PropPistolet", "WM_PropPumpM37", "WM_PropPumpDoom", "WM_PropSSG", "WM_PropBullpupPump",
           "WM_PropChaingun", "WM_PropMachineGun", "WM_PropRocketLauncher", "WM_PropRPG", "WM_PropPlasmaRifle", "WM_PropPlasmaRifleBlue",
           "WM_PropBFG", "WM_PropBFGHeavy", "WM_PropChainsaw", "WM_PropChainsawHeavy"]
PLUS = ["WM_PropMoonlight", "WM_PropSunset", "WM_PropCola", "WM_PropSMG", "WM_PropTec9", "WM_PropRifle", "WM_PropM16",
        "WM_PropFlamer", "WM_PropFlamethrower", "WM_PropRailgun"]
WAITING = []    # the swaps landed: Chaingun -> GH minigun (da8ef16), BFG -> BFG 10000 mesh (bda53ba), Rocket Launcher -> RPG mesh (c4c529f)
REF = {"main": ("WM_PropM4A3", "m4a3_trigger"), "off": ("WM_PropPistolet", "rec.001")}

# Trigger surface per prop, from the cards (role = trigger). Meshes without one get LANDMARKS: a file-space point
# (md3 units, before MODELDEF Scale) filled in by hand after looking at the mesh; None = not placed yet.
TRIGGER_SURFACE = {
    "WM_PropM4A3": "m4a3_trigger", "WM_PropPistolet": "rec.001", "WM_PropPumpM37": "m37a2_trigger",
    "WM_PropBullpupPump": "trigger", "WM_PropCola": "Trigger", "WM_PropRifle": "trigger", "WM_PropM16": "trigger",
    "WM_PropTec9": "trigger", "WM_PropSMG": "trigger", "WM_PropPlasmaRifle": "trigger", "WM_PropPlasmaRifleBlue": "trigger",
    "WM_PropRailgun": "trigger", "WM_PropMachineGun": "trigger", "WM_PropRPG": "trigger", "WM_PropBFG": "trigger", "WM_PropBFGHeavy": "trigger",
    "WM_PropChainsawHeavy": "trigger", "WM_PropFlamer": "trigger", "WM_PropFlamethrower": "trigger",
}
LANDMARKS = {}
if os.path.exists(os.path.join(HERE, "landmarks.json")):
    LANDMARKS = {k: v for k, v in json.load(open(os.path.join(HERE, "landmarks.json"))).items() if v}

ini = ic.read_ini()
props = ic.read_props()


def landmark_file(prop):
    """The landmark in file space (md3 units): trigger surface centroid, or the hand-picked point."""
    if prop in LANDMARKS:
        return np.array(LANDMARKS[prop], dtype=float), "landmark"
    surf = TRIGGER_SURFACE.get(prop)
    if not surf:
        return None, "none"
    m = MD3Model.load(props[prop]["md3"])
    for s in m.surfaces:
        if s.name == surf:
            return np.array(s.verts[0]).mean(axis=0), "trigger:" + surf
    return None, "surface %s missing" % surf


def world(prop, point, pl=None):
    p = props[prop]
    pl = pl or ic.placement(p["prefix"], ini)
    M = ic.chain(p["scale"], p["offset"], *p["base"], pl)
    return ic.to_engine(point[None, :], M)[0], pl


targets = {}
for hand, (rp, surf) in REF.items():
    pt, _ = landmark_file(rp)
    targets[hand], _ = world(rp, pt)
    print("target %-4s from %-16s trigger at engine %s (seat %s)" % (hand, rp, targets[hand].round(3), ic.placement(props[rp]["prefix"], ini)["ofs"]))

seats = {}
for group, names in (("vanilla", VANILLA), ("plus", PLUS)):
    for prop in names:
        p = props[prop]
        pt, how = landmark_file(prop)
        pl = ic.placement(p["prefix"], ini)
        old = list(pl["ofs"])
        if pt is None:
            seats[prop] = dict(group=group, prefix=p["prefix"], hand=p["hand"], old=old, new=None, landmark=how)
            print("%-24s %-4s %-7s NO LANDMARK (%s) -- seat kept %s" % (prop, p["hand"], group, how, old))
            continue
        cur, _ = world(prop, pt, pl)
        d = targets[p["hand"]] - cur                  # engine (x, y up, z) = placement (ofs_x, ofs_z, ofs_y)
        new = [old[0] + d[0], old[1] + d[2], old[2] + d[1]]
        chk, _ = world(prop, pt, ic.placement(p["prefix"], ini, dict(ofs=new)))
        seats[prop] = dict(group=group, prefix=p["prefix"], hand=p["hand"], old=old,
                           new=[round(v, 2) for v in new], landmark=how)
        print("%-24s %-4s %-7s %-22s seat %-22s -> %-26s (moved %.1f, check gap %.4f)"
              % (prop, p["hand"], group, how, [round(v, 2) for v in old], [round(v, 2) for v in new],
                 float(np.linalg.norm(d)), float(np.linalg.norm(chk - targets[p["hand"]]))))
for prop in WAITING:
    seats[prop] = dict(group="waiting", prefix=props[prop]["prefix"], hand=props[prop]["hand"], old=None, new=None,
                       landmark="new mesh not landed")
json.dump(seats, open(os.path.join(HERE, "seats.json"), "w"), indent=1)
print("wrote seats.json")
