// ============================================================================
// THE PARTS.
//
// A body here is not a model. It is a set of SLOTS -- a torso, two hands, nine
// holsters, two boots -- and each slot is filled by a PART that can be swapped
// for another without the rig knowing or caring what it is. Quake's torso today,
// a green armour voxel when you pick armour up; Quake's leather holster or the
// wireframe ring; Quake's fist, RS hands, or something else later.
//
// TWO LEVELS OF PLACEMENT, AND KEEPING THEM SEPARATE IS THE WHOLE DESIGN:
//
//   THE SLOT SEAT -- where a holster hangs on YOUR BODY. Owned by the rig, set
//   per actor through FollowBodyOfs, tuned and saved per slot. It is a property
//   of your proportions, not of the mesh, so it survives swapping the mesh.
//
//   THE PART FIT -- how a given MESH sits once it is in that slot. Owned by the
//   part, through MODELDEF PlacementCVars, which the engine reads live every
//   frame and folds into the model's own transform. It is a property of the
//   mesh, not of you, so it survives changing your body proportions.
//
// Collapsing those two into one set of numbers is the mistake QuakeVR's offsets
// bake in, and it is why its numbers cannot be lifted piecemeal: each one
// silently compensates for the other. Kept apart, a new mesh needs its own fit
// and inherits every seat, and a re-tuned body keeps every mesh.
//
// ADDING A VARIANT is: one class here, one MODELDEF block, one line in the
// registry in body_rig.zs. Nothing in the rig changes.
// ============================================================================

class RS_BodyPart : Actor abstract
{
	Default
	{
		+NOBLOCKMAP
		+NOGRAVITY
		+NOINTERACTION
		+DONTSPLASH
		+NOTONAUTOMAP
		+NOTELEPORT
		Radius 1;
		Height 1;
		RenderStyle "Normal";
	}
}

// ---------------------------------------------------------------- torso ----

class RS_PartTorsoQuake : RS_BodyPart
{
	States { Spawn: TRSO A -1; Stop; }
}

// THE RECOLOURS. Same mesh, same sprite, a different Skin in MODELDEF -- see
// the RECOLOURED TORSOS block there for how the skins were made. Separate
// classes only because MODELDEF binds per class; nothing else differs.
//
// TRSO A, the SAME sprite the Quake torso uses, and deliberately: MODELDEF
// resolves (class, sprite, frame), and a sprite with no lump behind it never
// binds -- the torso would simply not draw. These once pointed at RSBP, which
// has no lump anywhere, and the classes themselves had never been declared,
// so the engine refused the whole pk3 at MODELDEF before either mattered.
class RS_PartTorsoPlain : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }
class RS_PartTorsoGreen : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }
class RS_PartTorsoBlue  : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }
class RS_PartTorsoRed   : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }

// THE ARMOUR, WORN. The armour pickups' own voxels -- ARM1A green, ARM2A blue --
// drawn in the torso slot while you wear that armour. Red is the green vest
// with only its green turned red. It is never worn: near death it is laid
// translucent OVER either vest (syncBreath in body_rig.zs), which only works
// because it is the same shape. torsoStyle decides which vest is worn.
class RS_PartVestGreen : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }
class RS_PartVestBlue  : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }
class RS_PartVestRed   : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }

// -------------------------------------------------------------- holster ----

class RS_PartHolsterQuake : RS_BodyPart
{
	States { Spawn: HSHL A -1; Stop; }
}

// ----------------------------------------------------------------- hand ----
//
// HANDS DO NOT LIVE IN THE BODY FRAME and that is not an inconsistency. A
// holster hangs off your torso; a hand goes where the controller goes, and the
// two are different frames that disagree constantly -- which is the point, since
// reaching into a holster is exactly the moment they differ.
//
// So a hand part is placed by the engine's HAND path (MODELDEF FollowMainHand /
// FollowOffHand) and the rig never writes FollowBodyMode on it. Main and off are
// separate classes only because MODELDEF binds per class and each needs its own
// follow flag.

// The Quake fist and open hand were here: out on the owner's word (2026-09-15).

// WORN, NEVER SPAWNED. When RS_WorldHands owns the hand slots its hand is the
// one drawn, and these are what it wears: the rig hands a hand one of these as
// its modeldef (A_ChangeModel), and the hand draws that MODELDEF -- this mesh, at
// this scale, on this rig's own hand sliders -- while staying the actor that
// grabs and holds. See body_rig.zs dressWorldHands.
//
// DECOUPLED, WITH A BaseFrame, because the hand wearing them is: the engine
// looks a decoupled actor's MODELDEF up by class alone, and refuses bone
// questions about a class without a BaseFrame.
class RS_HandWearBase : Actor abstract
{
	Default { +NOINTERACTION; +NOBLOCKMAP; +DECOUPLEDANIMATIONS; }
	States { Spawn: QHND A -1; Stop; }
}
// The Ermac glove (hand_ermac.iqm): the same skeleton and every frame of the default RS
// hand, so it poses exactly like it and needs no frame map.
class RS_HandWearGloveMain : RS_HandWearBase {}
class RS_HandWearGloveOff  : RS_HandWearBase {}

// ----------------------------------------------------------------- helmet ----
//
// Worn on the head (body_rig.zs placeActor, RSLOT_HELMET). The mesh's origin is the
// eye, so the rig seats it at your head with no offset; the near-eye fade on its
// placement prefix hides it from your own view. See the MODELDEF block.
class RS_PartHelmetMarine : RS_BodyPart { States { Spawn: TRSO A -1; Stop; } }

// ----------------------------------------------------------------- boot ----
//
// The mesh ships in this pk3. It used to be referenced out of RS_ModelSwapper,
// which meant the body lost its feet the moment that mod left the load order --
// a hard dependency that looked like good hygiene.
//
// Step animation is not implemented. The slot exists, it is placed like any
// other, and whatever animates it later does so by moving this actor -- the rig
// does not need to change for that.

class RS_PartBootHeavy : RS_BodyPart
{
	States { Spawn: BOOT A -1; Stop; }
}

// The rigged IQM hands, as an alternate hand style. Same slot, same frame, same
// controller -- only the mesh and its pose numbering differ, which is exactly
// what a part variant is for.
//
// +DECOUPLEDANIMATIONS is NOT optional and its absence is not a warning: it is
// the half of a pair with MODELDEF BaseFrame, and the mismatch takes the game
// down on map load with nothing logged. See the MODELDEF note.
class RS_PartHandIQMBase : RS_BodyPart
{
	Default { +DECOUPLEDANIMATIONS; }
	States
	{
	Spawn:
		// ANY REAL SPRITE, NEVER TNT1. TNT1 is not "an invisible sprite" -- it
		// is an instruction to skip the actor entirely, checked BEFORE any model
		// is considered, so a TNT1 actor with a perfect MODELDEF draws nothing
		// and reports nothing. RS_HandWorldBase carries the same warning on the
		// same line, and I wrote TNT1 here anyway.
		QHND A -1;
		Stop;
	}
}

class RS_PartHandIQMMain : RS_PartHandIQMBase {}
class RS_PartHandIQMOff  : RS_PartHandIQMBase {}

// ----------------------------------------------------------------- arms ----
//
// THE SLAYER'S ARMS BETWEEN YOUR TORSO AND YOUR HANDS. The engine's reach chain
// (actor.zs SetModelReachChain) bends each one every drawn frame so its wrist
// lands in the hand actually on the controller -- RS_WorldHands' hand when that
// mod owns the slot, this rig's own otherwise. The hand leads and is never moved.
//
// DECOUPLED WITH A BaseFrame, as the engine notes ask: a decoupled model with no
// animation draws its bind pose, which is exactly what the solve starts from. A
// REAL spawn sprite, never TNT1 (see RS_PartHandIQMBase).
//
// ONE CLASS PER LOOK because MODELDEF binds per class: the full arm or just the
// forearm, each plain or wearing the armour tint. The rig picks among them
// (armStyle), so a pickup swaps the gauntlet the same way it swaps the torso.
class RS_PartArmBase : RS_BodyPart abstract
{
	Default { +DECOUPLEDANIMATIONS; }
	States { Spawn: TRSO A -1; Stop; }
}
class RS_PartArmSlayerR          : RS_PartArmBase {}
class RS_PartArmSlayerRGreen     : RS_PartArmBase {}
class RS_PartArmSlayerRBlue      : RS_PartArmBase {}
class RS_PartArmSlayerL          : RS_PartArmBase {}
class RS_PartArmSlayerLGreen     : RS_PartArmBase {}
class RS_PartArmSlayerLBlue      : RS_PartArmBase {}
class RS_PartForearmSlayerR      : RS_PartArmBase {}
class RS_PartForearmSlayerRGreen : RS_PartArmBase {}
class RS_PartForearmSlayerRBlue  : RS_PartArmBase {}
class RS_PartForearmSlayerL      : RS_PartArmBase {}
class RS_PartForearmSlayerLGreen : RS_PartArmBase {}
class RS_PartForearmSlayerLBlue  : RS_PartArmBase {}
// The red breath laid over each arm look (body_rig.zs syncArmBreath), never worn.
class RS_PartArmSlayerRRed       : RS_PartArmBase {}
class RS_PartArmSlayerLRed       : RS_PartArmBase {}
class RS_PartForearmSlayerRRed   : RS_PartArmBase {}
class RS_PartForearmSlayerLRed   : RS_PartArmBase {}

// ---------------------------------------------------------------- the marine ----
//
// THE DOOM MARINE (classic), AN OPTIONAL BODY, torso up: torso with shoulder pads, and arms whose hands are
// cut so the hand on your controller sits in the wrist. From the owner's Doom Eternal Classic Slayer download
// (models/marine/PROVENANCE.md). Its armour is RECOLOURED, never swapped for a vest (owner, 2026-09-15):
// green, blue while a blue suit is worn or armour is 150+, and red breathing over it at low health.
//
// DECOUPLED WITH A BaseFrame, like the Slayer arms: IQMs drawn in their bind pose, bent by the reach chain.
class RS_PartTorsoMarineBase : RS_BodyPart abstract
{
	Default { +DECOUPLEDANIMATIONS; }
	States { Spawn: TRSO A -1; Stop; }
}
class RS_PartTorsoMarineGreen : RS_PartTorsoMarineBase {}
class RS_PartTorsoMarineBlue  : RS_PartTorsoMarineBase {}
class RS_PartTorsoMarineRed   : RS_PartTorsoMarineBase {}   // the breath, never worn

// THE MARINE'S ARMS, one per side, per ARM PAIRING and per colour. The cut rim is laid onto the RS wrist the
// arm meets, and which wrist that is depends on "Arms reaching the wrong hands" (rs_body_arm_swap): A = on
// (the anatomical pairing), E = off (the engine's). The pairing letter comes BEFORE the colour so
// armBreathClassFor's "strip Green/Blue, add Red" lands on the red copy.
class RS_PartArmMarineRAGreen : RS_PartArmBase {}
class RS_PartArmMarineRABlue  : RS_PartArmBase {}
class RS_PartArmMarineRARed   : RS_PartArmBase {}
class RS_PartArmMarineREGreen : RS_PartArmBase {}
class RS_PartArmMarineREBlue  : RS_PartArmBase {}
class RS_PartArmMarineRERed   : RS_PartArmBase {}
class RS_PartArmMarineLAGreen : RS_PartArmBase {}
class RS_PartArmMarineLABlue  : RS_PartArmBase {}
class RS_PartArmMarineLARed   : RS_PartArmBase {}
class RS_PartArmMarineLEGreen : RS_PartArmBase {}
class RS_PartArmMarineLEBlue  : RS_PartArmBase {}
class RS_PartArmMarineLERed   : RS_PartArmBase {}

// THE MARINE'S HANDS: RS_WorldHands' RS hand -- same skeleton, every frame -- with its wrist stub shaped to the
// marine arm reaching it and its skin toned to the marine's. Worn by the world hand (dressWorldHands), one per
// hand and per pairing.
class RS_HandWearMarineMainA : RS_HandWearBase {}
class RS_HandWearMarineMainE : RS_HandWearBase {}
class RS_HandWearMarineOffA  : RS_HandWearBase {}
class RS_HandWearMarineOffE  : RS_HandWearBase {}

// ============================================================================
// THE WHOLE BODY.
//
// Everything above this line is the PART rig: a body assembled from a torso, two
// arms, two hands and a helmet, each its own mesh, each needing its own fit, its
// own wrist socket and a decision about which arm reaches which hand. That rig is
// parked in _parked/parts_body_2026-09-18 and is kept only as a reference.
//
// A whole body is one rigged model on one skeleton, and it BRINGS ITS OWN HANDS.
// That single fact deletes the wrist seam (there is no join), the arm-pairing
// question (its sides are its own), the per-arm socket and stub work, and the
// "which torso goes with which arms" problem. What is left to tune is where the
// body sits on you and how long its arms are -- a handful of numbers instead of
// two hundred.
//
// +DECOUPLEDANIMATIONS because the rig drives its joints directly (reach chains
// for the arms) rather than playing a sequence.
// ============================================================================
class RS_BodyWhole : RS_BodyPart abstract
{
	Default { +DECOUPLEDANIMATIONS; }
	States { Spawn: TRSO A -1; Stop; }
}

// The Doom Eternal Classic Slayer. models/marine/marine_whole.iqm, 152 joints,
// 15 surfaces -- see the MODELDEF block for what each surface is.
class RS_PartBodyMarine : RS_BodyWhole {}


// WHERE THE BODY'S ARM REACHES TO.
//
// A whole body's hands are part of the mesh, so nothing on the controller needs
// DRAWING -- but the reach chain still needs an actor to aim at, because that is
// what SetModelReachTarget takes. This is that actor and nothing else: no model,
// no sprite, invisible, sitting on the controller in the hand frame exactly as a
// drawn hand would.
//
// Keeping the hand SLOTS filled with these, rather than emptying them, is what
// lets the whole body reuse the part rig's arm machinery unchanged -- armTarget,
// the swap, the sockets and the seat all still find something where they expect a
// hand to be.
class RS_BodyHandAnchor : RS_BodyPart
{
	Default { RenderStyle "None"; Alpha 0; }
	States { Spawn: TNT1 A -1; Stop; }
}

// HIS HANDS. Pinned to the controllers by the engine, exactly as every hand in
// this rig has always been -- FollowMainHand/FollowOffHand in the MODELDEF, the
// hand frame in the rig. The body's arms then REACH these, which is the order
// that was always right and that the whole-body mesh briefly inverted.
class RS_HandMarineMain : RS_BodyPart { Default { +DECOUPLEDANIMATIONS; } States { Spawn: TRSO A -1; Stop; } }
class RS_HandMarineOff  : RS_BodyPart { Default { +DECOUPLEDANIMATIONS; } States { Spawn: TRSO A -1; Stop; } }

// THE DARK AGES PRAETOR. bigwig's GMod port, 83-joint ValveBiped skeleton, and the
// second whole body -- which is the one that proves the shape, because adding it was
// a registry line, a MODELDEF block and a menu entry rather than three days of wrist
// work. His hands were already their own meshes, so nothing was cut.
class RS_PartBodyPraetor : RS_BodyWhole {}
class RS_HandPraetorMain : RS_BodyPart { Default { +DECOUPLEDANIMATIONS; } States { Spawn: TRSO A -1; Stop; } }
class RS_HandPraetorOff  : RS_BodyPart { Default { +DECOUPLEDANIMATIONS; } States { Spawn: TRSO A -1; Stop; } }

// THE BREATH COPIES. The same body in red, laid over the worn one with a pulsing
// alpha when health is low. A copy rather than a tint because the pulse has to move
// every frame and repainting a dozen surfaces per tic to do it would be absurd.
class RS_PartBodyMarineRed  : RS_BodyWhole {}
class RS_PartBodyPraetorRed : RS_BodyWhole {}
