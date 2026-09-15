// ============================================================================
// THE RIG.
//
// Owns the slots, decides what fills each one, and places all of them from a
// SINGLE pass so they cannot drift apart. That last part is not incidental: the
// bug this whole package exists to avoid was one object placed on the display's
// clock and its neighbour placed on the tic's, so the two swam. Everything worn
// goes through placeSlot() or it is not part of the body.
//
// OFF THE TIC RATE. A world actor is normally placed by script at 35Hz and
// interpolated between samples -- which cannot work for anything hung on a head
// that moves at ninety, because interpolating between two stale samples of
// something that already moved just smooths the lag. AActor::FollowBodyMode
// hands the DRAW to the renderer, which rebuilds the matrix each frame from the
// live pose (VRMode::GetHmdTransform). The actor stays a real world actor with a
// real position for everything that reads one; only the drawing moves.
//
// SetOrigin still runs on every part, every tic, and still matters: it is the
// position a save records, what any distance test measures against, and what
// draws when there is no headset at all.
// ============================================================================

enum RS_BodySlotId
{
	RSLOT_TORSO = 0,
	RSLOT_HAND_MAIN,
	RSLOT_HAND_OFF,
	RSLOT_HOLSTER_0,   // HipLeft
	RSLOT_HOLSTER_1,   // HipRight
	RSLOT_HOLSTER_2,   // HeadLeft
	RSLOT_HOLSTER_3,   // HeadRight
	RSLOT_HOLSTER_4,   // PectoralLeft
	RSLOT_HOLSTER_5,   // PectoralRight
	RSLOT_HOLSTER_6,   // HipLeft2
	RSLOT_HOLSTER_7,   // HipRight2
	RSLOT_HOLSTER_8,   // Pouch
	RSLOT_BOOT_L,
	RSLOT_BOOT_R,
	// The arms come LAST on purpose: the slot loop decides the torso and the hands
	// before them, and an arm needs both. Appended, so every saved slot index above
	// keeps its meaning.
	RSLOT_ARM_R,
	RSLOT_ARM_L,
	// The helmet, on your head. Appended for the same reason as the arms.
	RSLOT_HELMET,
	RSLOT_COUNT
}

// Which frame a slot is placed in. A hand follows the controller and never the
// body; everything else hangs off the body.
// WHAT THE HAND IS DOING, not which frame it is on.
//
// A mesh's frame numbers are its own business: the IQM rig has a 1298-frame clip
// with the slide pinch at 1292, and Quake's hand.mdl has eighteen vertex frames
// with nothing like it. A gun that published frame numbers would be publishing
// numbers that mean different things to different hands -- and would have to be
// rewritten for every hand ever added.
//
// So a gun publishes what it WANTS, each hand style says what that looks like on
// its own mesh, and neither knows anything about the other.
enum RS_HandPose
{
	RPOSE_OPEN = 0,       // nothing held, at rest
	RPOSE_POINT,          // 3-4-5 closed, index and thumb out
	RPOSE_TRIGGER,        // index curled, empty hand
	RPOSE_FIST,           // all closed -- a punch
	RPOSE_PINCH,          // thumb to index
	RPOSE_THUMBOUT,       // fist, thumb clear -- a magazine release
	RPOSE_GRIPFIRE,       // on a gun, trigger pulled, thumb parked
	RPOSE_GRIP,           // on a gun, index resting on the trigger
	RPOSE_GRIP_TU,        // same, thumb lifted
	RPOSE_HOLD_ROUND,     // one cartridge, fingertips
	RPOSE_HOLD_SHELL,     // a shotgun shell, fuller grip
	RPOSE_INSERT,         // thumb driving it home
	RPOSE_HOLD_SLIDE,     // pinched on the serrations
	RPOSE_HOLD_MAG,       // magazine, thumb along the spine
	RPOSE_HOLD_FOREGRIP,  // vertical foregrip
	RPOSE_HOLD_FOREND,    // a pump, a fat cylinder
	RPOSE_REACH,          // fingers splayed flat
	RPOSE_REACH_CLAW,     // spread and relaxed -- about to close on something
	RPOSE_SUPPORT,        // wrapped round the firing hand
	RPOSE_SALUTE,
	RPOSE_COUNT
}

enum RS_BodyFrame
{
	RFRAME_BODY = 0,
	RFRAME_HAND_MAIN,
	RFRAME_HAND_OFF,
	RFRAME_ARM          // hangs in the body frame, bent onto a hand by the engine
}

class RS_VRBodyRig : EventHandler
{
	// CLASS LEVEL, NOT INSIDE A METHOD. ZScript does not accept a const declared
	// in a function body -- RS_Holsters carries a comment saying exactly this and
	// it still cost a load failure here.
	//
	// The engine picks which CONTROLLER a psprite rides from its caller and then
	// from the layer id, treating anything at or above PSprite.OFFHANDWEAPON as
	// the off hand -- which is the only reason a non-weapon can reach that hand.
	// One psprite layer per worn thing. Every one is >= PSprite.OFFHANDWEAPON so
	// nothing lands on a weapon layer, and they are spaced clear of RS_Hands'
	// 900000/1900000.
	//
	// Body slots sit ABOVE the hands so they draw after them -- psprites draw in
	// id order, and a torso should resolve against a hand rather than the other
	// way round.
	const LAYER_BODY_BASE = 1910000;   // + slot index

	const LAYER_MAIN = 900001;
	const LAYER_OFF  = 1900001;   // >= PSprite.OFFHANDWEAPON -- that is what puts it on the other controller

	// ---- what fills each slot, and where it sits -------------------------
	Array<Actor>  parts;
	Array<String> partClass;    // the class name currently spawned, "" for none

	// Seat, in MAP UNITS on the body's own axes: X forward, Y right, Z up.
	// Same convention as AActor::FollowBodyOfs, which is what these feed.
	//
	// Declared one per line rather than comma-separated: ZScript's parser is not
	// C, and a template type in a multi-declarator line is not worth finding out
	// about from a mod that will not load.
	Array<Double> sFwd;
	Array<Double> sSide;
	Array<Double> sUp;
	Array<Double> sYaw;
	Array<Double> sPitch;
	Array<Double> sRoll;
	Array<Double> sScale;

	private bool ready;
	private int  lastEditSlot;
	private bool warnedSpawn;
	private bool warnedDefer;


	// ---- in-headset placement --------------------------------------------
	// Sliders are the wrong instrument for fourteen objects you have to LOOK at
	// to judge. Reaching out, squeezing, and putting a holster where your hand
	// already is takes a second and is correct by construction.
	//
	// It also sidesteps the menu entirely: the seat sliders cannot update while
	// a menu is open because the game is paused and nothing script-side ticks.
	// Dragging happens during play, so that problem does not exist.
	// ---- the body's own heading ------------------------------------------
	// Holsters hang off your BODY, not your head. Driven straight off HmdYaw
	// they orbit your face: glance left and your hip holster goes with you, so
	// it is never in the same place twice and blind reach is impossible. The
	// whole value of a holster is reaching without looking.
	// "m" because ZScript names are CASE-INSENSITIVE: the public BodyYaw()
	// accessor below (for body_holsters.zs) and a field called bodyYaw are the
	// same name to the compiler -- "Attempt to redefine" -- and the game will
	// not start. slotWorldAt / SlotWorld are split for the same reason.
	private double mBodyYaw;
	private bool   bodyYawInit;
	private double lastTurnYaw;

	private bool editMode;
	private int  grabbedMain;   // slot being dragged by the main hand, -1 none
	private int  grabbedOff;
	// Where on the holster each hand gripped it, so it is carried by that point
	// and does not jump its centre onto the hand.
	private Vector3 grabOfsMain;
	private Vector3 grabOfsOff;
	// Last tic's grips: placement mode picks up and drops on a squeeze, not a hold.
	private bool prevGripMain;
	private bool prevGripOff;
	// The holster slider test (startHolsterTest): tics until it reports.
	private int     holTestTics;
	private Vector3 holTestFrom;
	private double  holTestBase;

	// ---- the registry ----------------------------------------------------
	// style name -> class, per slot kind. ADDING A VARIANT IS ONE LINE HERE
	// plus a class in body_parts.zs and a MODELDEF block. Nothing else.
	//
	// Kept as plain parallel arrays rather than anything cleverer because this
	// is read once at register time and the failure mode of "clever" here is a
	// mod that does not load at all.
	Array<String> regKind;
	Array<String> regStyle;
	Array<String> regClass;

	private void reg(string kind, string style, string cls)
	{
		regKind.Push(kind); regStyle.Push(style); regClass.Push(cls);
	}

	private string lookup(string kind, string style)
	{
		if (style == "" || style ~== "none") return "";
		for (int i = 0; i < regKind.Size(); ++i)
			if (regKind[i] ~== kind && regStyle[i] ~== style)
				return regClass[i];
		return "";
	}

	// Which kind of part a slot takes.
	static string slotKind(int s)
	{
		if (s == RSLOT_TORSO)                            return "torso";
		if (s == RSLOT_HAND_MAIN)                        return "handmain";
		if (s == RSLOT_HAND_OFF)                         return "handoff";
		if (s >= RSLOT_HOLSTER_0 && s <= RSLOT_HOLSTER_8) return "holster";
		if (s == RSLOT_ARM_R)                            return "armright";
		if (s == RSLOT_ARM_L)                            return "armleft";
		if (s == RSLOT_HELMET)                           return "helmet";
		return "boot";
	}

	static int slotFrame(int s)
	{
		if (s == RSLOT_HAND_MAIN) return RFRAME_HAND_MAIN;
		if (s == RSLOT_HAND_OFF)  return RFRAME_HAND_OFF;
		if (s == RSLOT_ARM_R || s == RSLOT_ARM_L) return RFRAME_ARM;
		return RFRAME_BODY;
	}

	static string slotName(int s)
	{
		switch (s)
		{
			case RSLOT_TORSO:      return "Torso";
			case RSLOT_HAND_MAIN:  return "Hand (main)";
			case RSLOT_HAND_OFF:   return "Hand (off)";
			case RSLOT_HOLSTER_0:  return "Holster: hip left";
			case RSLOT_HOLSTER_1:  return "Holster: hip right";
			case RSLOT_HOLSTER_2:  return "Holster: head left";
			case RSLOT_HOLSTER_3:  return "Holster: head right";
			case RSLOT_HOLSTER_4:  return "Holster: pectoral left";
			case RSLOT_HOLSTER_5:  return "Holster: pectoral right";
			case RSLOT_HOLSTER_6:  return "Holster: hip left 2";
			case RSLOT_HOLSTER_7:  return "Holster: hip right 2";
			case RSLOT_HOLSTER_8:  return "Pouch";
			case RSLOT_BOOT_L:     return "Boot left";
			case RSLOT_BOOT_R:     return "Boot right";
			case RSLOT_ARM_R:      return "Arm right";
			case RSLOT_ARM_L:      return "Arm left";
			case RSLOT_HELMET:     return "Helmet";
		}
		return "?";
	}

	// The starting seats. Deliberately the same numbers RS_Holsters ships in its
	// own table so a body assembled here lands where that system already put
	// things -- if the two ever disagree, one of them has been tuned and the
	// other has not, and that is worth being able to see.
	//
	// The vertical numbers assume roughly a 50-unit eye height. They are a
	// starting point to drag from, not a claim about anyone's proportions.
	private void defaultSeat(int s, out double f, out double sd, out double u,
	                         out double y, out double p, out double r, out double sc)
	{
		f = 0; sd = 0; u = 0; y = 0; p = 0; r = 0; sc = 1.0;
		switch (s)
		{
			case RSLOT_TORSO:      f =  0; sd =   0; u = -17;              break;
			case RSLOT_HAND_MAIN:                                          break;
			case RSLOT_HAND_OFF:                                           break;
			case RSLOT_HOLSTER_0:  f = -2; sd =  -9; u = -21.5; p = 90;    break;
			case RSLOT_HOLSTER_1:  f = -2; sd =   9; u = -21.5; p = 90;    break;
			case RSLOT_HOLSTER_2:  f =  7; sd = -10; u =  -2.5; p = 90;    break;
			case RSLOT_HOLSTER_3:  f =  7; sd =  10; u =  -2.5; p = 90;    break;
			case RSLOT_HOLSTER_4:  f = -1; sd =  -6; u = -11.0; p = 90;    break;
			case RSLOT_HOLSTER_5:  f = -1; sd =   6; u = -11.0; p = 90;    break;
			case RSLOT_HOLSTER_6:  f = -2; sd = -16; u = -21.5; p = 90;    break;
			case RSLOT_HOLSTER_7:  f = -2; sd =  16; u = -21.5; p = 90;    break;
			case RSLOT_HOLSTER_8:  f = -4; sd =   0; u = -18.0; p = 90;    break;
			case RSLOT_BOOT_L:     f =  0; sd =  -6; u = -46.0;            break;
			case RSLOT_BOOT_R:     f =  0; sd =   6; u = -46.0;            break;
		}
	}

	private static double normalizeDeg(double a)
	{
		while (a >  180.0) a -= 360.0;
		while (a < -180.0) a += 360.0;
		return a;
	}

	// Ported from RS_Holsters, including the part that is not obvious.
	private void updateBodyYaw(PlayerPawn pawn)
	{
		snapTurn = false;
		if (!bodyYawInit)
		{
			bodyYawInit = true;
			mBodyYaw     = pawn.HmdYaw;
			lastTurnYaw = pawn.VRTurnYaw;
			return;
		}

		// CONTROLLER TURN MOVES THE BODY 1:1 -- no deadzone, no easing.
		//
		// Snap and stick turn rotate the whole virtual body; your hips went with
		// it because nothing physical happened. Putting that through the neck
		// deadzone is a permanent drift: a 45-degree snap fits inside a
		// 50-degree deadzone, so the body refuses to follow, and every snap
		// leaves the holsters further behind with no path back -- each one is
		// individually "within neck range".
		double turnDelta = normalizeDeg(pawn.VRTurnYaw - lastTurnYaw);
		lastTurnYaw = pawn.VRTurnYaw;
		if (turnDelta != 0) mBodyYaw = normalizeDeg(mBodyYaw + turnDelta);
		// A SNAP TURN: every body part's heading jumps this tic, and drawing that
		// interpolated would sweep it round over one tic (a 45-degree snap is 17.5
		// degrees a frame) instead of snapping. Stick turning moves a few degrees a
		// tic and stays interpolated.
		snapTurn = abs(turnDelta) > 10.0;

		// THE HANDS (plan 4b idea 9). Both hands held out in front say where the
		// body is facing better than the head does -- you look around while you
		// aim. handsHeading answers how much they count (0 when either hand is
		// down, near the body or behind it) and where they point. With 0 every line
		// below is exactly the head rule it replaced. Checked offline at 35Hz with
		// the owner's settings (_old\...\armcut_2026-09-14\body_yaw_sim.py).
		double handsYaw;
		double w = handsHeading(pawn, handsYaw);

		// Yaw stops meaning anything near-vertical: looking at the floor, a
		// small head movement swings it wildly. Freeze rather than chase noise --
		// unless the hands are steering: aiming low while looking down is normal.
		bool headOk = abs(pawn.HmdPitch) <= cvf("rs_body_yaw_maxpitch", 55.0);
		if (w <= 0.0 && !headOk) return;

		double target = pawn.HmdYaw;
		if (w > 0.0) target = headOk ? normalizeDeg(pawn.HmdYaw + normalizeDeg(handsYaw - pawn.HmdYaw) * w) : handsYaw;
		double d = normalizeDeg(target - mBodyYaw);

		// Inside the neck's range the body does not move at all. This is what
		// makes a head shake cost nothing. The hands narrow it.
		double dead = cvf("rs_body_yaw_deadzone", 65.0);
		dead += (cvf("rs_body_yaw_hands_deadzone", 10.0) - dead) * w;
		if (abs(d) <= dead) return;

		// Past it, follow only the EXCESS and only partway per tic, so the body
		// eases round instead of snapping.
		double excess = (d > 0) ? (d - dead) : (d + dead);
		double follow = cvf("rs_body_yaw_follow", 0.06);
		follow += (cvf("rs_body_yaw_hands_follow", 0.25) - follow) * w;
		double step = excess * follow;
		double cap = cvf("rs_body_yaw_hands_maxstep", 0.0);
		if (w > 0.0 && cap > 0.0) step = clamp(step, -cap, cap);
		mBodyYaw = normalizeDeg(mBodyYaw + step);
	}

	// How much the two hands steer the body (0..1) and where they point. A hand
	// counts once it is out from the headset horizontally, in the front half of
	// the body and not hanging low; the two together count as much as the weaker
	// one, so one hand out and one down leaves the head in charge.
	private double handsHeading(PlayerPawn pawn, out double heading)
	{
		heading = 0.0;
		double scale = cvf("rs_body_yaw_hands", 1.0);
		if (scale <= 0.0) return 0.0;
		double hmin  = cvf("rs_body_yaw_hands_min", 6.0);
		double hspan = max(0.001, cvf("rs_body_yaw_hands_span", 6.0));
		double fwd0  = cvf("rs_body_yaw_hands_fwd", 0.0);
		double fspan = max(0.001, cvf("rs_body_yaw_hands_fwd_span", 0.5));
		double low   = cvf("rs_body_yaw_hands_low", 30.0);

		double sx = 0.0;
		double sy = 0.0;
		double w  = 1.0;
		for (int h = 0; h < 2; ++h)
		{
			Vector3 at = (h == 0) ? pawn.AttackPos : pawn.OffhandPos;
			if (at == (0, 0, 0)) return 0.0;
			Vector3 rel = at - pawn.HmdPos;
			double dist = rel.XY.Length();
			if (dist < 0.001 || rel.Z < -low) return 0.0;
			double hy = atan2(rel.Y, rel.X);
			double wh = clamp((dist - hmin) / hspan, 0.0, 1.0)
			          * clamp((cos(hy - mBodyYaw) - fwd0) / fspan, 0.0, 1.0);
			w = min(w, wh);
			sx += cos(hy) * wh;
			sy += sin(hy) * wh;
		}
		if (w <= 0.0) return 0.0;
		heading = atan2(sy, sx);
		return w * scale;
	}

	// A world position expressed as a SEAT -- the exact inverse of what
	// placeSlot does to put a part in the world. The basis is orthonormal, so
	// the inverse is the same projection; if this ever stops matching placeSlot,
	// a dragged holster will not stay where it was dropped.
	private static Vector3 worldToSeat(PlayerPawn pawn, Vector3 world, double headingDeg)
	{
		Vector3 rel = world - pawn.HmdPos;
		double fx = cos(headingDeg), fy = sin(headingDeg);
		double rx = sin(headingDeg), ry = -cos(headingDeg);
		return (rel.X * fx + rel.Y * fy,
		        rel.X * rx + rel.Y * ry,
		        rel.Z);
	}

	// The slot nearest this hand, or -1. Only body-frame slots: a hand cannot
	// grab itself.
	private int nearestSlot(PlayerPawn pawn, Vector3 handPos, double radius)
	{
		int best = -1;
		double bestD = radius * radius;
		for (int s = 0; s < RSLOT_COUNT; ++s)
		{
			// HOLSTERS ONLY. The torso and boots are set once and then never
			// thought about again, and having them compete for a grab means
			// reaching for a hip holster and coming away with your chest --
			// which is worse than not being able to grab them at all.
			if (s < RSLOT_HOLSTER_0 || s > RSLOT_HOLSTER_8) continue;
			if (!parts[s]) continue;
			if (s == grabbedMain || s == grabbedOff) continue;   // the other hand has it
			// WHERE IT IS DRAWN, not its seat: a holster moved on its own page is
			// grabbed where you see it.
			Vector3 d = SlotWorld(pawn, s) - handPos;
			double dd = d dot d;
			if (dd < bestD) { bestD = dd; best = s; }
		}
		return best;
	}

	private void toggleGrab(PlayerPawn pawn, bool mainHand)
	{
		int held = mainHand ? grabbedMain : grabbedOff;
		if (held >= 0)
		{
			if (mainHand) grabbedMain = -1; else grabbedOff = -1;
			level.VRHaptic(mainHand ? 0 : 1, 0.6, 15.0);
			// DROPPED IS KEPT. A drop that also needed "Save the body" pressed
			// came back in the old place next launch.
			saveProfile("vrbody");
			showMsg(String.Format("Dropped %s -- saved", slotName(held)));
			return;
		}

		// HOLSTERS ARE WHAT PLACEMENT MODE MOVES. It used to move only
		// RS_VR_PistolTest's ammo pouch unless a switch on the seats page was on,
		// and said so in the console alone -- which in a headset is a grab that
		// silently does nothing. That package is retired; the switch is gone.
		Vector3 at = mainHand ? pawn.AttackPos : pawn.OffhandPos;
		int s = nearestSlot(pawn, at, cvf("rs_body_grab_radius", 12.0));
		if (s < 0)
		{
			showMsg("No holster within reach of that hand");
			return;
		}
		Vector3 ofs = at - SlotWorld(pawn, s);
		if (mainHand) { grabbedMain = s; grabOfsMain = ofs; }
		else          { grabbedOff  = s; grabOfsOff  = ofs; }
		level.VRHaptic(mainHand ? 0 : 1, 0.4, 10.0);
		showMsg(String.Format("Holding %s -- grip again to drop", slotName(s)));
	}

	// POSITION ONLY. Orientation stays whatever the slot was given -- capturing
	// wrist angle at drop time leaves every holster tilted at whatever angle
	// your hand happened to be at, which nobody wants and RS_Holsters learned
	// the same way.
	private void updateGrabs(PlayerPawn pawn)
	{
		if (grabbedMain >= 0) dragTo(pawn, grabbedMain, pawn.AttackPos  - grabOfsMain);
		if (grabbedOff  >= 0) dragTo(pawn, grabbedOff,  pawn.OffhandPos - grabOfsOff);
		if (grabbedMain >= 0 || grabbedOff >= 0) lastEditSlot = -1;   // refresh the sliders
	}

	// Moves slot s's SEAT so the holster is DRAWN at `want`. Drawn is the seat plus
	// that holster's own live fit (its page), so the fit's offset comes off first --
	// or a holster moved on its page would ride beside the hand, not in it. Runs
	// before this tic's placement, so drawnAt still describes the current seat.
	private void dragTo(PlayerPawn pawn, int s, Vector3 want)
	{
		Vector3 fit = SlotWorld(pawn, s) - slotWorldAt(pawn, s);
		Vector3 v = worldToSeat(pawn, want - fit, mBodyYaw);
		sFwd[s] = v.X; sSide[s] = v.Y; sUp[s] = v.Z;
	}

	// PLACEMENT MODE'S GRAB IS THE CONTROLLER GRIP: squeeze on a holster to pick it
	// up, squeeze again to drop it. It used to be two extra bindable keys only,
	// which nobody reaches for with a controller in each hand. Those still work.
	private void pollGripGrabs(PlayerPawn pawn)
	{
		bool gm = pawn.GripHeldMain;
		bool go = pawn.GripHeldOff;
		if (gm && !prevGripMain) toggleGrab(pawn, true);
		if (go && !prevGripOff)  toggleGrab(pawn, false);
		prevGripMain = gm;
		prevGripOff  = go;
	}

	// Said where you can see it: the console is not in the headset.
	private static void showMsg(string msg)
	{
		Console.Printf("\c[Gold]RS_VRBody: %s", msg);
		Console.MidPrint(SmallFont, msg);
	}

	// ---- the holster slider test -----------------------------------------
	//
	// "A holster's page moves nothing" has three causes that look the same in a
	// headset: the value never reaches the player's userinfo copy the renderer
	// reads, the renderer's matrix does not use it, or the holster you see is not
	// the actor it is set on. This moves holster 0 up 2 through its own slider
	// cvar, then a few tics later says which -- and puts it back.
	private void startHolsterTest()
	{
		let raw = CVar.FindCVar("rs_bp_hol0_ofs_z");
		if (!raw) { showMsg("TEST: rs_bp_hol0_ofs_z does not exist"); return; }
		holTestBase = raw.GetFloat();
		holTestFrom = drawnValid[RSLOT_HOLSTER_0] ? drawnAt[RSLOT_HOLSTER_0] : (0, 0, 0);
		raw.SetFloat(holTestBase + 2.0);
		holTestTics = 8;
		showMsg("TEST: moving holster 0 up 2...");
	}

	private void tickHolsterTest()
	{
		if (holTestTics <= 0 || --holTestTics > 0) return;
		int s = RSLOT_HOLSTER_0;
		let raw = CVar.FindCVar("rs_bp_hol0_ofs_z");
		let usr = CVar.GetCVar("rs_bp_hol0_ofs_z", players[consoleplayer]);
		double rawV = raw ? raw.GetFloat() : -999.0;
		double usrV = usr ? usr.GetFloat() : -999.0;
		double moved = drawnValid[s] ? (drawnAt[s] - holTestFrom).Length() : -1.0;
		string prefix = "no actor";
		if (parts[s]) prefix = parts[s].PlacementPrefix;
		showMsg(String.Format("TEST holster 0: slider %.1f  renderer copy %.1f  drawn moved %.2f  prefix %s",
			rawV, usrV, moved, prefix));
		if (raw) raw.SetFloat(holTestBase);
	}

	// WHAT EACH POSE LOOKS LIKE, per hand mesh.
	//
	// The IQM rig carries one 1298-frame clip: 0-10 are the baked hand shapes
	// and 1289+ the manipulation set, which no sprite letter can name and which
	// was therefore authored and unreachable until frames could be addressed by
	// number.
	//
	// Quake's hand.mdl has eighteen vertex frames and nothing resembling a slide
	// pinch, so several poses collapse onto its closed grip. A missing pose is
	// answered with the nearest thing the mesh HAS rather than left blank -- a
	// hand that stops posing because one shape is unavailable looks broken; one
	// that closes slightly wrong looks like a hand.
	private static int poseFrame(string style, int pose)
	{
		// "glove" is the Ermac glove on the RS hand's skeleton and frames: same table.
		if (style ~== "rs" || style ~== "glove" || style ~== "iqm")
		{
			// hand_left.iqm, one 1298-frame clip. 0-10 are the baked shapes,
			// 513 the animator's own fist, 1289+ the manipulation set. Frames
			// 11-1288 are the unaddressed source animation.
			//
			// The manipulation set is only reachable at all because frames can
			// be addressed by NUMBER: no sprite letter can name frame 1292, so
			// those poses were authored and unusable until that existed.
			switch (pose)
			{
				case RPOSE_OPEN:          return 0;
				case RPOSE_POINT:         return 1;
				case RPOSE_TRIGGER:       return 2;
				case RPOSE_FIST:          return 3;
				case RPOSE_PINCH:         return 4;
				case RPOSE_THUMBOUT:      return 5;
				case RPOSE_GRIPFIRE:      return 6;
				case RPOSE_GRIP:          return 8;      // READY, thumb down
				case RPOSE_GRIP_TU:       return 7;
				case RPOSE_HOLD_ROUND:    return 1289;
				case RPOSE_HOLD_SHELL:    return 1290;
				case RPOSE_INSERT:        return 1291;
				case RPOSE_HOLD_SLIDE:    return 1292;
				case RPOSE_HOLD_MAG:      return 1293;
				case RPOSE_HOLD_FOREGRIP: return 1294;
				case RPOSE_HOLD_FOREND:   return 1295;
				case RPOSE_REACH:         return 1296;
				case RPOSE_REACH_CLAW:    return 1298;
				case RPOSE_SUPPORT:       return 1297;
				case RPOSE_SALUTE:        return 1299;
			}
			return 0;
		}

		// hand.mdl: eighteen vertex frames, no manipulation set. It can say
		// open, closed and the tweens between and nothing finer, so the fine
		// poses collapse onto its closed grip. A hand that stops posing because
		// one shape is missing looks broken; one that closes slightly wrong
		// still looks like a hand.
		switch (pose)
		{
			case RPOSE_OPEN:       return 5;
			case RPOSE_REACH:      return 5;
			case RPOSE_REACH_CLAW: return 3;
			case RPOSE_POINT:      return 1;
			case RPOSE_TRIGGER:    return 1;
		}
		return 2;
	}

	// Blend state per hand, so fingers TRAVEL between shapes. Setting both ends
	// equal with a lerp of zero is an explicit instruction not to blend, and
	// that reads as the hand teleporting between poses.
	private int    blendFrom[2];
	private int    blendTo[2];
	private double blendT[2];

	// WHAT SHAPE EACH HAND SHOULD BE IN, PUBLISHED FOR WHOEVER DRAWS IT.
	//
	// Runs every tic for both hands whether or not this rig spawned a hand --
	// because when RS_WorldHands is loaded it did not, and that is exactly when
	// something else needs to be told.
	//
	// A FRAME NUMBER, NOT A POSE INDEX, and the difference is the whole reason
	// this works. The two packages do NOT share a pose vocabulary and cannot be
	// made to without one of them adopting the other's enum:
	//
	//     idx  RS_VRBody RPOSE_     RS_WorldHands POSE_
	//     0-6  OPEN..GRIPFIRE       identical
	//     7    GRIP                 GRIP_TU        <-- diverges here
	//     8    GRIP_TU              READY_TD
	//     9+   HOLD_ROUND..SALUTE   READY_TU, FIRE_TU, then a jump to 1289
	//
	// RS_VRBody numbers 20 poses contiguously; RS_WorldHands numbers 11 and
	// then jumps to HOLD_BASE 1289 where the manipulation set actually lives in
	// the mesh. Passing an index across that boundary makes the wrong shape,
	// silently, and only for the poses above 6 -- which is every interesting
	// one.
	//
	// So the rig translates and publishes the RESULT. poseFrame() already owns
	// that translation per hand style, and a frame number is exactly what
	// RS_HandWorldBase.poseHold already accepts from anything holding
	// something. The body becomes one more publisher rather than a special
	// case, which is the same reason poseHold was built to take a number and
	// not a set of weapon flags.
	//
	// -1 means "nothing to say" -- an open hand with nothing to do is the
	// consumer's own default, and overriding it here would stop the
	// controllers from driving the hand at rest.
	// THE STYLE HERE IS WHOSE MESH IS ACTUALLY ON THE CONTROLLER, which is not
	// always what rs_body_style_hand* says. When the slot is deferred, the hand
	// being drawn is RS_WorldHands' hand_left.iqm no matter what style this mod
	// has saved -- so a player left on "quake" would have their pose translated
	// through hand.mdl's eighteen vertex frames and published as a frame number
	// for a mesh that is not there. Every pose above the first few would be
	// wrong, and it would look like the pose system half-working rather than
	// like a unit mismatch.
	private void publishPose()
	{
		for (int hand = 0; hand < 2; ++hand)
		{
			int slot = (hand == 0) ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF;

			string style;
			if (handSlotIsForeign(slot))
				style = "rs";                                     // hand_left.iqm
			else
				style = cvs(hand == 0 ? "rs_body_style_handmain"
				                      : "rs_body_style_handoff", "quake");

			int pose = clamp(cvi(hand == 0 ? "rs_body_pose_main" : "rs_body_pose_off",
			                     RPOSE_OPEN), 0, RPOSE_COUNT - 1);

			// RPOSE_OPEN publishes -1, not frame 0. "Open" is what a hand with
			// nothing to do already does on its own, and forcing it would stop
			// the controllers driving an idle hand -- a finger on the trigger
			// would stop reading as one.
			int frame = (pose == RPOSE_OPEN) ? -1 : poseFrame(style, pose);
			seti(hand == 0 ? "rs_body_poseframe_main" : "rs_body_poseframe_off", frame);
		}
	}

	// ---- RS_WorldHands' hand, wearing this rig's hand style ---------------
	//
	// WITH RS_WorldHands LOADED ITS HAND IS THE ONE DRAWN (handSlotIsForeign),
	// and it used to be drawn as its own mesh whatever the style menu said -- the
	// Quake hands were chosen and never appeared. So the style goes ON that hand:
	// A_ChangeModel gives it one of the RS_HandWear* modeldefs, which brings the
	// Quake mesh, its scale and this rig's own hand sliders, and "pose.wear"
	// tells it how that mesh numbers its poses. It stays RS_WorldHands' actor, so
	// grabbing, holding and pinning are untouched.
	//
	// "rs" takes the mesh off again (a modeldef of '' is the class's own). Done on
	// change only -- and again whenever the hand actor is a new one, after a map
	// load -- never per tic.
	private Name  dressedAs[2];
	private Actor dressedOn[2];

	private void dressWorldHands()
	{
		for (int hand = 0; hand < 2; ++hand)
		{
			int slot = (hand == 0) ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF;
			if (!handSlotIsForeign(slot)) continue;

			String cls = (hand == 0) ? "RS_HandWorldMain" : "RS_HandWorldOff";
			Actor hd = Actor(ThinkerIterator.Create(cls).Next());
			if (!hd) { dressedOn[hand] = null; continue; }

			string style = cvs(hand == 0 ? "rs_body_style_handmain" : "rs_body_style_handoff", "rs");
			Name want = wearClass(style, hand);
			// THE MARINE'S HANDS: with a marine arm reaching this hand, the RS hand wears its marine fit -- the
			// wrist stub shaped to that arm and the marine's skin tone. Same skeleton and frames as the RS hand.
			bool marineHand = (want == '') && (style ~== "rs") && armIsMarineOn(hand);
			if (marineHand) want = marineWear(hand);
			if (hd == dressedOn[hand] && want == dressedAs[hand]) continue;

			hd.A_ChangeModel(want);
			let ps = ServiceIterator.Find("RS_HandPoseService").Next();
			// A mesh on the hand's own skeleton and frames ("glove", the marine fit) is not
			// "worn": no frame map, and its bones can be asked for.
			bool ownFrames = (want == '') || (style ~== "glove") || marineHand;
			if (ps) ps.GetInt("pose.wear", ownFrames ? "" : wearFrames(style), hand, 0, null, 'RS_VRBody');
			dressedAs[hand] = want;
			dressedOn[hand] = hd;
		}
	}

	private static Name wearClass(string style, int hand)
	{
		if (style ~== "quake") return (hand == 0) ? 'RS_HandWearQuakeMain' : 'RS_HandWearQuakeOff';
		if (style ~== "open")  return (hand == 0) ? 'RS_HandWearOpenMain'  : 'RS_HandWearOpenOff';
		if (style ~== "glove")  return (hand == 0) ? 'RS_HandWearGloveMain' : 'RS_HandWearGloveOff';
		return '';
	}

	// Is the arm reaching this hand a marine arm? The main hand is reached by the right arm slot unless
	// rs_body_arm_swap turns the pairing round (armTarget). Read from last tic's arm part, so a newly picked
	// marine arm dresses its hand a tic later.
	private bool armIsMarineOn(int hand)
	{
		bool fromRight = (hand == 0) != cvb("rs_body_arm_swap", false);
		return partClass[fromRight ? RSLOT_ARM_R : RSLOT_ARM_L].IndexOf("ArmMarine") >= 0;
	}

	// The marine fit for this hand and the current pairing: A when "Arms reaching the wrong hands" is on.
	private Name marineWear(int hand)
	{
		bool anat = cvb("rs_body_arm_swap", false);
		if (hand == 0) return anat ? 'RS_HandWearMarineMainA' : 'RS_HandWearMarineMainE';
		return anat ? 'RS_HandWearMarineOffA' : 'RS_HandWearMarineOffE';
	}

	// The hand's own frame for every pose, mapped to this style's -- built from
	// poseFrame, the one table that already knows both meshes, so nothing here
	// can drift from it. Any frame not in the table (RS_WorldHands has a few of
	// its own) takes the style's fallback shape.
	private static string wearFrames(string style)
	{
		string s = "";
		for (int p = 0; p < RPOSE_COUNT; ++p)
			s = s .. String.Format("%d:%d,", poseFrame("rs", p), poseFrame(style, p));
		return s .. String.Format("*:%d", poseFrame(style, -1));
	}

	private void poseHand(Actor a, int hand, int pose)
	{
		int want = poseFrame(cvs("rs_body_style_" .. (hand == 0 ? "handmain" : "handoff"), "quake"), pose);
		if (want != blendTo[hand])
		{
			// Target changed mid-blend. Two frame numbers cannot express an
			// in-between shape, so start from the nearer end of the blend in
			// progress rather than snapping back to where it began.
			blendFrom[hand] = (blendT[hand] >= 0.5) ? blendTo[hand] : blendFrom[hand];
			blendTo[hand]   = want;
			blendT[hand]    = 0.0;
		}

		double rate = cvf("rs_body_pose_blend", 4.0);
		if (rate <= 0.0) blendT[hand] = 1.0;
		else blendT[hand] = min(1.0, blendT[hand] + 1.0 / rate);
		if (blendT[hand] >= 1.0) blendFrom[hand] = blendTo[hand];

		a.ModelFrame     = blendFrom[hand];
		a.ModelFrameNext = blendTo[hand];
		a.ModelFrameLerp = blendT[hand];
	}

	// ---- cvar helpers ----------------------------------------------------

	private static double cvf(string n, double def)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		return c ? c.GetFloat() : def;
	}
	private static bool cvb(string n, bool def)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		return c ? c.GetBool() : def;
	}
	private static int cvi(string n, int def)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		return c ? c.GetInt() : def;
	}
	private static string cvs(string n, string def)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		return c ? c.GetString() : def;
	}

	// ---- lifecycle -------------------------------------------------------

	override void OnRegister()
	{
		reg("torso",    "quake",  "RS_PartTorsoQuake");

		// THE SAME MESH WEARING A DIFFERENT SKIN. See the note in MODELDEF:
		// vrtorso.mdl's own 8-bit skin is overridden by a MODELDEF Skin line, so
		// each of these is one PNG and one block rather than a second model.
		//
		// The skins are hue-replaced with luminance preserved per pixel, so the
		// grime and the panel lines survive -- these are not tints.
		reg("torso",    "plain",  "RS_PartTorsoPlain");
		reg("torso",    "green",  "RS_PartTorsoGreen");
		reg("torso",    "blue",   "RS_PartTorsoBlue");
		reg("torso",    "red",    "RS_PartTorsoRed");
		// THE ARMOUR, WORN -- chosen by torsoStyle, never by the menu. Registered
		// like any style so a vest swaps in by the same path as a menu change.
		reg("torso",    "vestgreen", "RS_PartVestGreen");
		reg("torso",    "vestblue",  "RS_PartVestBlue");
		reg("torso",    "vestred",   "RS_PartVestRed");
		reg("holster",  "quake",  "RS_PartHolsterQuake");
		// HAND STYLES. Every one is a world actor on the controller, so they are
		// interchangeable at runtime and the rig never learns which is in the
		// slot. Adding another is a class, a MODELDEF block and one line here.
		reg("handmain", "quake",  "RS_PartHandQuakeMain");
		reg("handmain", "rs",     "RS_PartHandIQMMain");
		reg("handoff",  "rs",     "RS_PartHandIQMOff");
		reg("handoff",  "quake",  "RS_PartHandQuakeOff");
		reg("handmain", "open",   "RS_PartHandOpenMain");
		reg("handoff",  "open",   "RS_PartHandOpenOff");
		reg("boot",     "heavy",  "RS_PartBootHeavy");
		// The name this style had before it was renamed off the mod it came
		// from. Kept because a style name lives in the player's ini, and
		// renaming one silently switches them to a style that no longer exists
		// -- which reads as the part vanishing for no reason.
		reg("boot",     "swapper","RS_PartBootHeavy");
		// THE ARMS. armStyle picks the look: the base style from the menu, with
		// "green"/"blue" appended when the gauntlet wears your armour.
		reg("armright", "slayer",        "RS_PartArmSlayerR");
		reg("armright", "slayergreen",   "RS_PartArmSlayerRGreen");
		reg("armright", "slayerblue",    "RS_PartArmSlayerRBlue");
		reg("armright", "forearm",       "RS_PartForearmSlayerR");
		reg("armright", "forearmgreen",  "RS_PartForearmSlayerRGreen");
		reg("armright", "forearmblue",   "RS_PartForearmSlayerRBlue");
		reg("armleft",  "slayer",        "RS_PartArmSlayerL");
		reg("armleft",  "slayergreen",   "RS_PartArmSlayerLGreen");
		reg("armleft",  "slayerblue",    "RS_PartArmSlayerLBlue");
		reg("armleft",  "forearm",       "RS_PartForearmSlayerL");
		reg("armleft",  "forearmgreen",  "RS_PartForearmSlayerLGreen");
		reg("armleft",  "forearmblue",   "RS_PartForearmSlayerLBlue");
		// THE HELMET: the Doom Eternal Classic Slayer's (models/helmet/PROVENANCE.md).
		reg("helmet",   "marine",        "RS_PartHelmetMarine");
		// THE DOOM MARINE (classic), an optional body. The menu offers only "marine"; torsoStyle and armStyle
		// decide the colour (and, for an arm, the pairing letter a/e) every tic, as they do for the others.
		reg("torso",    "marine",        "RS_PartTorsoMarineGreen");
		reg("torso",    "marineblue",    "RS_PartTorsoMarineBlue");
		reg("armright", "marineagreen",  "RS_PartArmMarineRAGreen");
		reg("armright", "marineablue",   "RS_PartArmMarineRABlue");
		reg("armright", "marineegreen",  "RS_PartArmMarineREGreen");
		reg("armright", "marineeblue",   "RS_PartArmMarineREBlue");
		reg("armleft",  "marineagreen",  "RS_PartArmMarineLAGreen");
		reg("armleft",  "marineablue",   "RS_PartArmMarineLABlue");
		reg("armleft",  "marineegreen",  "RS_PartArmMarineLEGreen");
		reg("armleft",  "marineeblue",   "RS_PartArmMarineLEBlue");
	}

	private void ensure()
	{
		if (ready) return;
		parts.Resize(RSLOT_COUNT);
		partClass.Resize(RSLOT_COUNT);
		sFwd.Resize(RSLOT_COUNT);  sSide.Resize(RSLOT_COUNT); sUp.Resize(RSLOT_COUNT);
		sYaw.Resize(RSLOT_COUNT);  sPitch.Resize(RSLOT_COUNT); sRoll.Resize(RSLOT_COUNT);
		sScale.Resize(RSLOT_COUNT);
		for (int s = 0; s < RSLOT_COUNT; ++s)
		{
			double f, sd, u, y, p, r, sc;
			defaultSeat(s, f, sd, u, y, p, r, sc);
			sFwd[s] = f; sSide[s] = sd; sUp[s] = u;
			sYaw[s] = y; sPitch[s] = p; sRoll[s] = r; sScale[s] = sc;
			parts[s] = null; partClass[s] = "";
		}
		lastEditSlot = -1;
		grabbedMain = -1;
		grabbedOff = -1;
		ready = true;
		loadProfile("vrbody");
	}

	override void WorldLoaded(WorldEvent e)
	{
		// Actors do not survive a level change, so drop every handle rather than
		// writing through a stale pointer next tic. The SEATS survive -- they are
		// yours, not the level's.
		for (int s = 0; s < parts.Size(); ++s) { parts[s] = null; partClass[s] = ""; }
		glow[0] = null; glow[1] = null;
		for (int i = 0; i < 16; ++i) hlCopy[i] = null;
		breath = null; breathClass = ""; breathAlpha = 0.0; breathPhase = 0.0;
	}

	// ---- placement -------------------------------------------------------

	// PUBLIC, for anything else that needs to anchor to a slot's live position
	// without re-deriving body yaw or duplicating the seat math -- currently
	// body_holsters.zs, which parks the stored-weapon prop wherever the shell
	// mesh actually is. Assume a second caller; that is why these exist
	// instead of staying private like slotWorldAt below.
	Vector3 SlotWorld(PlayerPawn pawn, int s)
	{
		// A HOLSTER IS WHERE YOU SEE IT: its seat plus its own live fit, as the
		// renderer draws it. The reach test, the glow and the stored gun all ask
		// here, so a holster moved on its page is reached where it now is.
		if (s >= RSLOT_HOLSTER_0 && s <= RSLOT_HOLSTER_8 && drawnValid[s]) return drawnAt[s];
		return slotWorldAt(pawn, s);
	}

	// NAME LITERALS, not a Name built from formatted text: a literal needs no
	// conversion, so there is nothing here that can fail to compile.
	static const Name HOLSTER_PREFIX[] = {
		'rs_bp_hol0', 'rs_bp_hol1', 'rs_bp_hol2', 'rs_bp_hol3', 'rs_bp_hol4',
		'rs_bp_hol5', 'rs_bp_hol6', 'rs_bp_hol7', 'rs_bp_hol8' };
	static const Name HOLSTER_GATE[] = {
		'rs_body_hl0', 'rs_body_hl1', 'rs_body_hl2', 'rs_body_hl3', 'rs_body_hl4',
		'rs_body_hl5', 'rs_body_hl6', 'rs_body_hl7', 'rs_body_hl8' };

	private Name holsterPrefix(int s)
	{
		return HOLSTER_PREFIX[s - RSLOT_HOLSTER_0];
	}

	// Where each holster was DRAWN this tic -- see the pass after the slot loop.
	Vector3 drawnAt[16];
	bool    drawnValid[16];
	double  BodyYaw() { return mBodyYaw; }
	// True on the tic a snap turn moved the body: anything else seated in the body
	// frame at display rate (body_holsters.zs's stored guns) clears its interpolation.
	private bool snapTurn;
	bool    SnapTurnThisTic() { return snapTurn; }
	// Placement mode moves holsters rather than using them; the holsters stand down.
	bool    EditModeOn() { return editMode; }

	// Where a slot sits in the world, from its seat and the BODY's heading.
	// Nothing is a world actor any more, so this is the only source of truth for
	// "where is that holster" -- the grab test and the markers both read it.
	private Vector3 slotWorldAt(PlayerPawn pawn, int s)
	{
		double fx = cos(mBodyYaw), fy = sin(mBodyYaw);
		double rx = sin(mBodyYaw), ry = -cos(mBodyYaw);
		return (pawn.HmdPos.X + sFwd[s] * fx + sSide[s] * rx,
		        pawn.HmdPos.Y + sFwd[s] * fy + sSide[s] * ry,
		        pawn.HmdPos.Z + sUp[s]);
	}

	// WORLD ACTORS. Everything worn lives in the map, not in the HUD bubble.
	//
	// This is where it has to end up: a HUD-slot thing is drawn inside YOUR view
	// only and no other player can ever see it, so a body anyone else can see
	// must be a world actor. It also gets room lighting and is hidden by walls,
	// which a HUD one never can be.
	//
	// The cost, until the weapons follow: a world body cannot sort against a HUD
	// weapon, so hands and guns pass through the torso. That is not a bug to
	// chase -- it is what two render passes do, and it goes away when the guns
	// move out too.
	//
	// Two anchors, both at draw rate:
	//   hands       -> the CONTROLLER, MODELDEF FollowMainHand/FollowOffHand
	//   everything  -> the BODY, AActor::FollowBodyMode 2 with our own heading
	private void placeSlot(PlayerPawn pawn, int s) { placeActor(pawn, parts[s], s); }

	// The placement itself, for anything worn in slot s: the part, or the
	// breath laid over it, which must sit exactly where the part does or it is
	// a red ghost beside you instead of a tint on you.
	private void placeActor(PlayerPawn pawn, Actor a, int s)
	{
		if (!a) return;

		// EACH HOLSTER ITS OWN LIVE FIT, by ID. The per-actor prefix outranks the
		// MODELDEF's shared rs_bp_holster and the renderer reads it every frame,
		// so a holster's own page moves that holster while the menu is open.
		// Set here rather than once at spawn so the glow's copy of the mesh gets
		// it too -- a glow on the old fit would sit beside the holster.
		if (s >= RSLOT_HOLSTER_0 && s <= RSLOT_HOLSTER_8)
			a.PlacementPrefix = holsterPrefix(s);

		if (s == RSLOT_HELMET) { placeHelmet(pawn, a); return; }

		// The marine torso, and the breath over it, hang on the shoulder line with the marine arms.
		if (s == RSLOT_TORSO)
		{
			String cn = a.GetClassName();
			if (cn.IndexOf("TorsoMarine") >= 0) { placeMarineTorso(pawn, a); return; }
		}

		int frame = slotFrame(s);
		if (frame == RFRAME_ARM) { placeArm(pawn, a, s); return; }
		if (frame != RFRAME_BODY)
		{
			// The engine places a follow-hand model from GetWeaponTransform at
			// draw rate; nothing here positions it. The world position is still
			// set so it exists somewhere sane with no headset and so anything
			// measuring distance to a hand has something to measure.
			Vector3 at = (frame == RFRAME_HAND_MAIN) ? pawn.AttackPos : pawn.OffhandPos;
			if (at == (0, 0, 0)) at = pawn.Pos;
			a.SetOrigin(at, true);
			a.FollowBodyMode = 0;

			// THE POSE, published by whatever the hand is dealing with.
			//
			// A cvar rather than a direct call, because the thing that knows
			// (a gun, a holster, a ladder) and the thing that draws (this) are
			// in different pk3s and neither may be loaded. An absent cvar reads
			// as RPOSE_OPEN, which is the correct answer for a hand with nothing
			// to do.
			int hand = (frame == RFRAME_HAND_MAIN) ? 0 : 1;
			poseHand(a, hand, clamp(cvi(hand == 0 ? "rs_body_pose_main" : "rs_body_pose_off",
			                            RPOSE_OPEN), 0, RPOSE_COUNT - 1));

			// AND NOTHING ELSE. A follow-hand model gets its whole transform
			// from GetWeaponTransform at draw time and its MODELDEF
			// PlacementCVars on top; the actor's own angles are zeroed by the
			// renderer and its Scale MULTIPLIES the placement scale.
			//
			// Writing Scale here from a second cvar meant two sliders fighting
			// over one number, which reads as the placement slider doing
			// nothing -- it was doing something and then being overwritten a
			// tic later. The gun has nothing doing this to it, which is exactly
			// why the gun's sliders worked and these did not.
			return;
		}

		// SEATS ARE IN THE BODY'S HEADING, not the head's -- so a hip holster
		// stays on your hip while you look around and can be reached for blind.
		double by = mBodyYaw;
		double fx = cos(by), fy = sin(by);
		double rx = sin(by), ry = -cos(by);
		a.SetOrigin((pawn.HmdPos.X + sFwd[s] * fx + sSide[s] * rx,
		             pawn.HmdPos.Y + sFwd[s] * fy + sSide[s] * ry,
		             pawn.HmdPos.Z + sUp[s]), true);

		// MODE 2: we supply the heading, so the seat goes in raw with nothing to
		// re-project. Mode 1 would use the renderer's own heading, which is not
		// visible from script and is not HmdYaw.
		a.FollowBodyOfs  = (sFwd[s], sSide[s], sUp[s]);
		a.FollowBodyYaw  = by;
		a.FollowBodyMode = 2;

		a.angle = by + sYaw[s];
		a.pitch = sPitch[s];
		a.roll  = sRoll[s];

		double sc = sScale[s];
		a.Scale = (sc, sc);

		// DRAWN AT DISPLAY RATE: last tic's heading turned toward this one, so a
		// smooth turn does not tick at 35Hz. A snap turn stays a snap -- cleared
		// after every write above, position and angles included.
		a.FollowBodyYawInterp = true;
		if (snapTurn) a.ClearInterpolation();
	}

	// ---- the helmet: on your head ----------------------------------------
	//
	// ON YOUR HEAD, NOT YOUR BODY. The mesh's origin is the eye, so the seat is no
	// offset at all: the body frame's origin IS the headset (GetHmdTransform), and
	// the helmet sits there at draw rate. Its heading is the HEAD's (HmdYaw, handed
	// in as mode 2's heading, so the renderer's subtraction leaves only the fit yaw),
	// and it nods and tilts with the head (HmdPitch / HmdRoll through the MODELDEF's
	// USEACTORPITCH / USEACTORROLL).
	//
	// PITCH AND ROLL ARE TIC RATE. GetHmdTransform carries position and heading only
	// -- by design, so holsters do not tip -- and the actor's own pitch and roll are
	// written here once a tic, drawn interpolated. You never see it: the near-eye fade
	// on rs_bp_helmet hides the helmet from your own eyes. A mirror or a chase camera
	// sees the nod at 35Hz until the engine has a head frame with pitch and roll.
	private void placeHelmet(PlayerPawn pawn, Actor a)
	{
		a.SetOrigin(pawn.HmdPos, true);
		a.FollowBodyOfs  = (0, 0, 0);
		a.FollowBodyYaw  = pawn.HmdYaw;
		a.FollowBodyMode = 2;
		a.angle = pawn.HmdYaw;
		a.pitch = pawn.HmdPitch;
		a.roll  = pawn.HmdRoll;
		a.Scale = (1.0, 1.0);   // the size is the fit's _scale
		a.FollowBodyYawInterp = true;
		if (snapTurn) a.ClearInterpolation();
	}

	// ONE HAND PER CONTROLLER, AND SOMEBODY ELSE MAY ALREADY OWN IT.
	//
	// RS_WorldHands puts RS_HandWorldMain/Off on the controllers: the same
	// hand_left.iqm, the same FollowMainHand/FollowOffHand frame, the same
	// 0.01 world scale as this rig's own RS_PartHandIQM*. Load both and each
	// controller carries TWO hands, separated by however far the two sets of
	// placement sliders happen to disagree -- and neither looks broken enough
	// to name, which is the worst kind of bug to find in a headset.
	//
	// The rig yields, and it is not a coin toss which way. RS_WorldHands' hand
	// can grab, hold, pass between hands, throw and brace; this rig's can only
	// pose.
	//
	// IT YIELDS THE POSE TOO, and that half is not optional. RS_HandWorldBase
	// runs its own blend and writes ModelFrame/ModelFrameNext/ModelFrameLerp
	// every tic (handworld.zs Tick). poseHand() writes the identical three
	// fields. Deferring the actor while still posing it would put two writers
	// on one transform a tic apart -- the exact failure that made the hand
	// placement sliders read as dead for a whole night. One writer.
	//
	// The rig keeps the part it is actually good at: SAYING WHAT SHAPE THE
	// HAND SHOULD BE IN. publishPose() below puts that on a cvar as a frame
	// number, and RS_WorldHands consumes it as one more publisher alongside
	// its own grab. See the note there.
	//
	// SOFT BY NAME, the same pattern every optional link in this family uses.
	// A hard class reference to something in another pk3 is a compile error
	// that is FATAL AND GLOBAL -- thingdef.cpp:420-424 refuses every pk3 later
	// in the load order -- so one absent mod would take the game down.
	//
	// Costs nothing when RS_WorldHands is absent: FindClass returns null, and
	// the rig fills its hand slots exactly as it always has.
	private bool handSlotIsForeign(int s)
	{
		if (s != RSLOT_HAND_MAIN && s != RSLOT_HAND_OFF) return false;
		if (!cvb("rs_body_defer_hands", true)) return false;

		// Name(), not a bare String. The only other non-literal FindClass in this
		// family wraps explicitly (wr_compat_modelswapper.zs) and this follows
		// it rather than relying on an implicit conversion.
		Name other = (s == RSLOT_HAND_MAIN) ? 'RS_HandWorldMain' : 'RS_HandWorldOff';
		if (!Object.FindClass(other)) return false;

		if (!warnedDefer)
		{
			Console.Printf("\c[Gold]RS_VRBody: RS_WorldHands is loaded, so it owns both hand slots.");
			Console.Printf("\c[Gold]  Hand placement is on its sliders (rs_hw_main / rs_hw_off), not this rig's.");
			Console.Printf("\c[Gold]  Set rs_body_defer_hands 0 to put the body's own hands back.");
			warnedDefer = true;
		}
		return true;
	}

	// ---- the arms ----------------------------------------------------------
	//
	// THE SLAYER'S ARMS, bent by the engine onto whichever hand is actually on
	// each controller. Everything the arm DOES happens in the renderer at draw
	// rate (actor.zs SetModelReachChain): the rig only says which joints, which
	// hand, and where on that hand. Render only and never saved, so nothing here
	// touches the game -- see Engine docs/IK_STAGE1_IMPL_NOTES.md.
	//
	// LINT-REACH: rs_arm_rt rs_arm_lf
	// LINT-SEATS: rs_arm_sock_rs rs_arm_sock_quake rs_arm_sock_marine

	// The look for an arm slot: the menu's base style, wearing the armour tint
	// the torso would -- 100-149 green, 150+ blue (armourBand).
	private string armStyle(PlayerPawn pawn, int s)
	{
		string look = (s == RSLOT_ARM_R) ? cvs("rs_body_style_armright", "slayer")
		                                 : cvs("rs_body_style_armleft",  "slayer");
		if (look == "" || look ~== "none") return "none";
		// THE MARINE'S ARMS are always armoured, in the torso's colour (blue whenever the worn torso is), and
		// cut for the arm pairing: "a" with "Arms reaching the wrong hands" on, "e" with it off.
		if (look ~== "marine")
		{
			string pair = cvb("rs_body_arm_swap", false) ? "a" : "e";
			bool blue = partClass[RSLOT_TORSO].IndexOf("Blue") >= 0;
			return "marine" .. pair .. (blue ? "blue" : "green");
		}
		if (!cvb("rs_body_arm_armor_color", true)) return look;
		// A WORN VEST SETS THE COLOUR (owner, 2026-09-15). The vest's colour is the SUIT's,
		// not the amount's, so a blue suit worn down below 150 is still a blue vest -- and
		// the gauntlets used to go green under it. The torso slot is decided before the arms
		// in the slot loop, so partClass[RSLOT_TORSO] is this tic's.
		string worn = partClass[RSLOT_TORSO];
		if (worn.IndexOf("VestBlue") >= 0)  return look .. "blue";
		if (worn.IndexOf("VestGreen") >= 0) return look .. "green";
		int band = armourBand(pawn);
		if (band == 2) return look .. "blue";
		if (band == 1) return look .. "green";
		return look;
	}

	// The hand this arm reaches, and which socket that hand's mesh has (0 the
	// rigged hand_left.iqm, 1 the Quake hand). The right arm takes the main hand
	// unless rs_body_arm_swap says the engine's IQM load mirror put it on the other
	// side (plan 3e) -- which is confirmed on screen, not assumed.
	private Actor armTarget(int s, out int sock)
	{
		sock = 0;
		bool main = (s == RSLOT_ARM_R);
		if (cvb("rs_body_arm_swap", false)) main = !main;
		int hand = main ? 0 : 1;
		int slot = main ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF;

		Actor hd;
		string style;
		if (handSlotIsForeign(slot))
		{
			// RS_WorldHands' hand, found by name so nothing here needs that mod.
			hd = dressedOn[hand];
			if (!hd) hd = Actor(ThinkerIterator.Create(main ? "RS_HandWorldMain" : "RS_HandWorldOff").Next());
			style = cvs(main ? "rs_body_style_handmain" : "rs_body_style_handoff", "rs");
		}
		else
		{
			hd = parts[slot];
			style = cvs(main ? "rs_body_style_handmain" : "rs_body_style_handoff", "quake");
		}
		// The Quake fist and the open hand share one cuff; everything else wears
		// the rigged hand's mesh (dressWorldHands).
		if (style ~== "quake" || style ~== "open") sock = 1;
		return hd;
	}

	// The arm hangs in the BODY frame (FollowBodyMode 2, the holsters' heading),
	// with its shoulders measured from the torso's own seat -- not ridden on the
	// torso actor, whose mesh changes under it: the armour vest swaps in with its
	// own model space and its own fit yaw, and a shoulder riding that would jump
	// on every pickup. The arm's PlacementCVars fit moves it live on top.
	//
	// The chain is re-asserted every tic: idempotent, and it survives a load.
	// THE SHOULDER, AS A POINT ON THE TORSO MESH carried through the torso's fit,
	// by the renderer's own sums (models.cpp ObjectToWorldMatrix: the fit's uniform
	// and per-axis scale, with its offset added before the scale) -- so the arms
	// stay on the shoulders when the torso is resized. Returned relative to the
	// pawn's headset, in the body's axes. At the torso fit yaw of -180 the mesh's
	// front is -x, so its x comes out as forward negated; a different torso yaw
	// would need that sign changed. Magnitude only on the side, the arm picks it.
	private double, double, double shoulderSeat(bool right)
	{
		double sc = cvf("rs_bp_torso_scale",   1.0); if (sc <= 0.0) sc = 1.0;
		double sx = cvf("rs_bp_torso_scale_x", 1.0); if (sx <= 0.0) sx = 1.0;
		double sy = cvf("rs_bp_torso_scale_y", 1.0); if (sy <= 0.0) sy = 1.0;
		double sz = cvf("rs_bp_torso_scale_z", 1.0); if (sz <= 0.0) sz = 1.0;
		double mx = cvf("rs_body_arm_shoulder_x", -1.3);
		double my = cvf("rs_body_arm_shoulder_y", 10.0);
		double mz = cvf("rs_body_arm_shoulder_z", 13.0) + cvf("rs_bp_torso_ofs_z", 0.0);
		double side = my * sc * sy + cvf("rs_body_arm_trim_side", 0.0);
		double f  = sFwd[RSLOT_TORSO] - mx * sc * sx + cvf("rs_body_arm_trim_fwd", 0.0);
		double sd = sSide[RSLOT_TORSO] + (right ? side : -side);
		double u  = sUp[RSLOT_TORSO] + mz * sc * sz + cvf("rs_body_arm_trim_up", 0.0);
		return f, sd, u;
	}

	private void placeArm(PlayerPawn pawn, Actor a, int s)
	{
		bool right = (s == RSLOT_ARM_R);
		String armClass = a.GetClassName();
		bool marine = armClass.IndexOf("ArmMarine") >= 0;
		double f, sd, u;
		if (marine) { [f, sd, u] = marineShoulderSeat(right, false); }
		else        { [f, sd, u] = shoulderSeat(right); }

		double by = mBodyYaw;
		double fx = cos(by), fy = sin(by);
		double rx = sin(by), ry = -cos(by);
		a.SetOrigin((pawn.HmdPos.X + f * fx + sd * rx,
		             pawn.HmdPos.Y + f * fy + sd * ry,
		             pawn.HmdPos.Z + u), true);
		a.FollowBodyOfs  = (f, sd, u);
		a.FollowBodyYaw  = by;
		a.FollowBodyMode = 2;
		a.angle = by;
		a.pitch = 0;
		a.roll  = 0;
		a.Scale = (1.0, 1.0);   // the size is the fit's _scale, never a second writer
		// The shoulders turn with the torso at display rate; a snap stays a snap.
		a.FollowBodyYawInterp = true;
		if (snapTurn) a.ClearInterpolation();

		// The rig's joints and directions in the arm's MODEL space (the IQM file's
		// (x, z, y)): the arm's own side outward, file down and file back, and the
		// twist reference -- the Slayer's index-minus-pinky off the forearm.
		Name up, mid, wrist, tuning;
		Vector3 outward, twistRef;
		if (marine)
		{
			// The marine's own bones. twistRef by the same method as the Slayer's (index minus pinky
			// off the forearm, in model order), measured on the marine skeleton at its 0.872 scale.
			up    = right ? 'bip_upperArm_R' : 'bip_upperArm_L';
			mid   = right ? 'bip_lowerArm_R' : 'bip_lowerArm_L';
			wrist = right ? 'bip_hand_R'     : 'bip_hand_L';
			tuning = right ? 'rs_arm_rt' : 'rs_arm_lf';
			outward  = right ? (-1, 0, 0) : (1, 0, 0);
			twistRef = right ? (0.1929, 0.6177, -0.7624) : (-0.1929, 0.6177, -0.7624);
		}
		else if (right)
		{
			up = 'arm_upper_rt'; mid = 'arm_lower_rt'; wrist = 'arm_hand_rt'; tuning = 'rs_arm_rt';
			outward = (-1, 0, 0);
			twistRef = (0.4117, 0.4096, -0.8141);
		}
		else
		{
			up = 'arm_upper_lf'; mid = 'arm_lower_lf'; wrist = 'arm_hand_lf'; tuning = 'rs_arm_lf';
			outward = (1, 0, 0);
			twistRef = (-0.4117, 0.4096, -0.8141);
		}
		a.SetModelReachChain(0, up, mid, wrist, tuning);
		a.SetModelReachFrame(0, outward, (0, -1, 0), (0, 0, 1), twistRef);
		a.SetModelReachFollowJoint(0, 'None');

		int sock;
		Actor hd = armTarget(s, sock);
		if (!hd) { a.ClearModelReachChain(0); return; }

		// THE WRIST SOCKETS, in each hand's model space and units (plan 3c/3g):
		// the Quake hands' shared 15-vertex cuff; the rigged hand's wrist at its
		// palm, 0.5 map units back (1.47 model units). Their sliders add live on top.
		//
		// THE BENDING WRIST (plan 4b idea 1, IK_ADDITIONS_IMPL_NOTES.md): after the
		// solve the rigged hand's Root_joint turns its forearm stub along the solved
		// forearm -- up to rs_arm_*_aim_max degrees, weighted by rs_arm_*_aim -- while
		// HANDPALM and the fingers stay on the controller. It used to be a rigid stub
		// 2.604 map units behind the palm, which poked through the gauntlet whenever
		// the wrist bent. The Quake hands have no stub and keep their cuff.
		if (sock == 1)
		{
			a.SetModelReachTarget(0, hd, (-6.90, 1.43, -1.10), (1, 0, 0), (0, 0, 0), 'rs_arm_sock_quake');
			a.SetModelReachTargetJoint(0, 'None');
		}
		else if (marine)
		{
			// THE MARINE WRIST, MEASURED (tools/marine: wrist_socket.py, stub_reshape.py, arm_rim_tuck.py,
			// wrist_flex.py; VR_BODY_QUEUE.md item 3). Its forearm is not centred on its own joint line, so
			// the arm's wrist joint lands off the rigged hand's centre line -- by how much depends on which
			// hand this arm reaches, so on the pairing. The hand it reaches wears the matching marine fit
			// (dressWorldHands). The stub is AIMED ABOUT THAT SAME POINT, not the hand's origin: about the
			// origin, a 40-degree bend pushed the stub 0.3-0.4 map units through the forearm; about the
			// landing point the seam stays within about 0.2. Model order (file x, z, y), model units.
			bool anat = cvb("rs_body_arm_swap", false);
			Vector3 p;
			if (right) p = anat ? (0.38, 1.47, -1.53) : (0.30, 1.47, 1.60);
			else       p = anat ? (2.03, 1.47, -1.35) : (0.96, 1.47, 1.68);
			a.SetModelReachTarget(0, hd, p, (0, -1, 0), (1, 0, 0), 'rs_arm_sock_marine');
			a.SetModelReachTargetJoint(0, 'Root_joint', p, 70);
		}
		else
		{
			a.SetModelReachTarget(0, hd, (0, 1.47, 0), (0, -1, 0), (1, 0, 0), 'rs_arm_sock_rs');
			a.SetModelReachTargetJoint(0, 'Root_joint', (0, 0, 0), 70);
		}
	}

	// ---- the marine: one rig on the shoulder line --------------------------
	//
	// The marine's torso and arms come from ONE skeleton, so they share one anchor: the SHOULDER LINE this
	// rig already keeps (shoulderSeat -- the torso's shoulder point through its fit, and the trims). The
	// torso's PivotOffset is the midpoint of its shoulder joints and sits at the line's centre; each arm's is
	// its own shoulder joint, MARINE_SHOULDER_HALF either side, scaled by the marine torso's fit size so a
	// resized torso keeps its arms on its shoulders. The torso fit's offsets move only the torso: move the
	// whole marine with the shoulder trims ("Where the shoulders sit").
	const MARINE_SHOULDER_HALF = 7.238;

	private double, double, double marineShoulderSeat(bool right, bool centre)
	{
		double f, sd, u;
		[f, sd, u] = shoulderSeat(right);
		double sc = cvf("rs_bp_marinetorso_scale",   1.0); if (sc <= 0.0) sc = 1.0;
		double sx = cvf("rs_bp_marinetorso_scale_x", 1.0); if (sx <= 0.0) sx = 1.0;
		sd = sSide[RSLOT_TORSO];
		if (!centre) sd += (right ? 1.0 : -1.0) * MARINE_SHOULDER_HALF * sc * sx;
		return f, sd, u;
	}

	// Placed in the body frame exactly as an arm is (placeArm), on the shoulder line's centre.
	private void placeMarineTorso(PlayerPawn pawn, Actor a)
	{
		double f, sd, u;
		[f, sd, u] = marineShoulderSeat(true, true);
		double by = mBodyYaw;
		double fx = cos(by), fy = sin(by);
		double rx = sin(by), ry = -cos(by);
		a.SetOrigin((pawn.HmdPos.X + f * fx + sd * rx,
		             pawn.HmdPos.Y + f * fy + sd * ry,
		             pawn.HmdPos.Z + u), true);
		a.FollowBodyOfs  = (f, sd, u);
		a.FollowBodyYaw  = by;
		a.FollowBodyMode = 2;
		a.angle = by;
		a.pitch = 0;
		a.roll  = 0;
		a.Scale = (1.0, 1.0);   // the size is the fit's _scale, never a second writer
		a.FollowBodyYawInterp = true;
		if (snapTurn) a.ClearInterpolation();
	}

	// ARM SIZE FROM YOUR OWN REACH (plan 4b idea 2). Arms straight out to the
	// sides: the span between the hands, less the shoulders the body draws, halved,
	// is one arm from shoulder to palm. The Slayer's is 20.147 at size 1 (bones
	// 8.849 + 8.694, wrist to palm 2.604). Both arm sizes, clamped 0.7..1.5.
	// Shoulder height is reported, never changed -- the torso is yours.
	private void calibrateArms(PlayerPawn pawn)
	{
		Vector3 m = pawn.AttackPos;
		Vector3 o = pawn.OffhandPos;
		if (m == (0, 0, 0) || o == (0, 0, 0))
		{
			Console.Printf("\c[Red]RS_VRBody: no hand positions to measure -- hold both controllers out and try again");
			return;
		}
		double sf, ssd, su;
		[sf, ssd, su] = shoulderSeat(true);
		double span  = (m - o).Length();
		double reach = (span - 2.0 * abs(ssd - sSide[RSLOT_TORSO])) * 0.5;
		double size  = clamp(reach / 20.147, 0.7, 1.5);
		setf("rs_bp_armright_scale", size);
		setf("rs_bp_armleft_scale",  size);

		double shoulderZ = pawn.HmdPos.Z + su;
		double handsZ    = (m.Z + o.Z) * 0.5;
		Console.Printf("\c[Gold]RS_VRBody: hands %.1f apart, so each arm is %.1f shoulder to palm -- arm size %.2f",
			span, reach, size);
		Console.Printf("\c[Gold]  Your hands are %.1f %s the shoulders the body draws.",
			abs(handsZ - shoulderZ), (handsZ >= shoulderZ) ? "above" : "below");
	}

	// ---- the torso: what it is wearing -----------------------------------
	//
	// THE MENU'S COLOUR IS ONLY THE BASE, and armour overrides it in two
	// separate ways that must not be confused:
	//
	//   THE VEST is armour you are WEARING. It goes on only when you pick up a
	//   suit, and comes off when your armour falls below that suit's range --
	//   after which bonuses change the colour and never put the vest back.
	//   RS_BodyArmorWatch, at the bottom of this file, is what knows.
	//
	//   THE COLOUR is armour you HAVE: 0-99 your base colour, 100-149 green,
	//   150+ blue, straight off the number.
	//
	// Both are just style names in the same registry the menu uses, so
	// syncSlotPart swaps the part exactly as it would for a menu change. Health
	// is not decided here at all -- it is a breath laid over whatever this
	// chooses (syncBreath).
	private string torsoStyle(PlayerPawn pawn)
	{
		string style = cvs("rs_body_style_torso", "quake");
		if (style == "" || style ~== "none") return "none";

		// THE MARINE RECOLOURS AND NEVER WEARS A VEST (owner, 2026-09-15: "recolour, keep the mesh", and
		// "follow the suit"): blue while a blue suit is worn, green while a green one is, otherwise by the
		// amount (150+ blue), and green at rest. Its red breath is laid over it like any torso's (syncBreath).
		if (style ~== "marine")
		{
			let mw = RS_BodyArmorWatch(pawn.FindInventory("RS_BodyArmorWatch"));
			if (!mw) pawn.GiveInventory("RS_BodyArmorWatch", 1);
			bool blue;
			if (mw && mw.suit == 2)      blue = true;
			else if (mw && mw.suit == 1) blue = false;
			else                         blue = (armourBand(pawn) == 2);
			return blue ? "marineblue" : "marine";
		}

		let watch = RS_BodyArmorWatch(pawn.FindInventory("RS_BodyArmorWatch"));
		if (!watch)
			pawn.GiveInventory("RS_BodyArmorWatch", 1);
		else if (watch.suit > 0 && cvb("rs_body_armor_voxel", true))
			return (watch.suit == 2) ? "vestblue" : "vestgreen";

		if (cvb("rs_body_armor_color", true))
		{
			int band = armourBand(pawn);
			if (band == 2) return "blue";
			if (band == 1) return "green";
		}
		return style;
	}

	// 0 under 100, 1 for 100-149, 2 for 150 and up. How much, not what kind:
	// the colour is the number, and the vest is what carries the kind.
	private int armourBand(PlayerPawn pawn)
	{
		let arm = BasicArmor(pawn.FindInventory("BasicArmor"));
		int amount = arm ? arm.Amount : 0;
		if (amount >= RS_BodyArmorWatch.BLUE_AT)  return 2;
		if (amount >= RS_BodyArmorWatch.GREEN_AT) return 1;
		return 0;
	}

	// ---- looking down: see past your own chest ---------------------------
	//
	// Look at your feet and the torso fades to rs_body_lookdown_alpha, so your
	// boots and the floor are not hidden behind a solid chest; look back up and
	// it returns. Driven by head PITCH (Doom's convention: positive is down --
	// HmdPitch is the viewpoint's own pitch, vk_openxrdevice.cpp), smoothstepped
	// so there is no edge at either end of the range, and eased a little so a
	// quick glance does not step at the 35Hz tic.
	//
	// TRANSLUCENT ONLY WHILE FADED. RenderStyle "Normal" makes the renderer
	// ignore Alpha outright -- body_holsters.zs carries the same warning -- but
	// a translucent torso also sorts with every other translucent thing in the
	// room. So it goes back to Normal the moment it is fully opaque, and costs
	// nothing while you are looking ahead.
	// No initialisers: ZScript class fields cannot have them (a load-time parse
	// error that stops every mod). lookLogged false means nothing logged yet.
	private bool   lookLogged;             // has a [LOOKDOWN] line been written yet
	private double lookLogPitch;           // the head pitch last written to the log
	private int    lookLogState;           // 0 opaque, 1 fading, 2 fully faded, as last logged
	private double lookFade;       // 0 opaque .. 1 fully faded to the target alpha
	private double torsoVisible;   // this tic's torso alpha, for the breath laid over it

	private void applyLookFade(PlayerPawn pawn)
	{
		double target = 0.0;
		if (cvb("rs_body_lookdown_fade", true))
		{
			double t = clamp((pawn.HmdPitch - cvf("rs_body_lookdown_start", 30.0)) / 25.0, 0.0, 1.0);
			target = t * t * (3.0 - 2.0 * t);
		}
		lookFade += (target - lookFade) * 0.35;
		if (abs(lookFade - target) < 0.002) lookFade = target;

		double low = clamp(cvf("rs_body_lookdown_alpha", 0.5), 0.0, 1.0);
		// The standing transparency first, then the look-down fade on top of
		// it -- so a half-see-through torso still fades further when you look
		// at your feet, and the breath scales with both.
		double solid = 1.0 - clamp(cvf("rs_body_torso_transparency", 0.0), 0.0, 0.9);
		torsoVisible = solid * (1.0 - lookFade * (1.0 - low));

		Actor torso = parts[RSLOT_TORSO];

		// [LOOKDOWN] -- WHAT THE FADE SAW, so a headset test says why it did or
		// did not fade: the head pitch it was given (positive is down), where the
		// fade starts, and the torso's alpha. On a 10-degree change of pitch or a
		// change of state only, never per tic. A pitch that stays near 0 while
		// you look at your feet means the engine is not giving the body the head.
		double pitchNow = Actor.Normalize180(pawn.HmdPitch);
		int stateNow = (lookFade <= 0.0) ? 0 : ((lookFade >= 1.0) ? 2 : 1);
		if (!lookLogged || abs(pitchNow - lookLogPitch) >= 10.0 || stateNow != lookLogState)
		{
			lookLogged   = true;
			lookLogPitch = pitchNow;
			lookLogState = stateNow;
			Console.PrintfEx(PRINT_NONOTIFY, "[LOOKDOWN] head pitch %.1f (fade %s, starts at %.0f) -> torso alpha %.2f%s",
				pitchNow, cvb("rs_body_lookdown_fade", true) ? "on" : "OFF",
				cvf("rs_body_lookdown_start", 30.0), torsoVisible, torso ? "" : "  (NO TORSO to fade)");
		}

		if (!torso) return;
		if (torsoVisible >= 0.999) torso.A_SetRenderStyle(1.0, STYLE_Normal);
		else                       torso.A_SetRenderStyle(torsoVisible, STYLE_Translucent);
	}

	// ---- the breath: health, laid over the torso -------------------------
	//
	// Near death a red copy of whatever you are wearing fades in and out over
	// it, slowly, like breathing -- the red torso over any torso, the red vest
	// over either vest. Same mesh, placed by the same code as the part, so it
	// lies exactly on it. World models draw with DF_LEqual (hw_models.cpp,
	// BeginDrawModel), so identical geometry passes the depth test and the red
	// just tints what is underneath.
	//
	// A BREATH, NOT A FLASH, and not for looks: a hard on/off is a
	// photosensitivity hazard. This is a sine with no edge anywhere in it, and
	// even at its fastest it is under one cycle a second. Healing lets it out
	// the same way -- a fade, never a cut.
	//
	// NOTHING MIXES. The part underneath keeps its colour and the red is only
	// ever laid over it and taken away again, so between breaths you see your
	// armour exactly. A blended hue would say neither thing honestly: red over
	// green is the muddy brown of "no armour, healthy".
	private Actor  breath;
	private string breathClass;
	private double breathPhase;
	private double breathAlpha;

	private void syncBreath(PlayerPawn pawn)
	{
		if (!parts[RSLOT_TORSO])
		{
			if (breath) breath.Destroy();
			breath = null; breathClass = ""; breathAlpha = 0.0; breathPhase = 0.0;
			return;
		}

		string worn = partClass[RSLOT_TORSO];
		string want = "RS_PartTorsoRed";
		if (worn.IndexOf("TorsoMarine") >= 0) want = "RS_PartTorsoMarineRed";
		else if (worn.IndexOf("Vest") >= 0)   want = "RS_PartVestRed";
		int below = max(1, cvi("rs_body_breathe_below", 25));
		int hp    = pawn.Health;

		if (cvb("rs_body_breathe", true) && hp > 0 && hp < below)
		{
			double t    = 1.0 - double(hp) / below;   // 0 at the threshold, near 1 at death
			double secs = 2.6 - 1.4 * t;              // one breath per 2.6s, down to 1.2s
			breathPhase += 1.0 / (secs * 35.0);
			if (breathPhase >= 1.0) breathPhase -= 1.0;

			// Deeper as it gets worse, and never fully opaque: even at the top
			// of a breath near death, the armour shows through.
			double peak = 0.45 + 0.35 * t;
			breathAlpha = peak * (0.5 - 0.5 * cos(breathPhase * 360.0));
		}
		else
		{
			breathAlpha = max(0.0, breathAlpha - 0.03);
			breathPhase = 0.0;
			if (breathAlpha <= 0.0)
			{
				if (breath) breath.Destroy();
				breath = null; breathClass = "";
				return;
			}
		}

		if (!breath || breathClass != want)
		{
			if (breath) breath.Destroy();
			breath = null;
			breathClass = want;
			class<Actor> cls = (class<Actor>)(want);
			if (!cls) return;
			breath = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);
			if (!breath) return;
			breath.A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");
			placeActor(pawn, breath, RSLOT_TORSO);
			breath.ClearInterpolation();
		}
		placeActor(pawn, breath, RSLOT_TORSO);
		// Scaled by the torso's own look-down fade: a red layer at full
		// strength over a half-faded chest would read as a red ghost.
		breath.A_SetRenderStyle(breathAlpha * torsoVisible, STYLE_Translucent);
	}

	// ---- the breath on the arms ------------------------------------------
	//
	// The torso's breath, carried onto the Slayer arms: a copy of whichever arm
	// look is worn (full arm or forearm, plain or armour-tinted) with the red
	// gauntlet, at the torso breath's own alpha, so both arms and the chest
	// breathe as one. Same switch (rs_body_breathe) and threshold; when the torso
	// breath is gone, so is this.
	//
	// PLACED BY placeActor, WHICH FOR AN ARM SLOT IS placeArm: the copy gets the
	// same shoulder seat, reach chain and hand target as the arm, so the engine
	// solves it onto the same hand in the same frame and it lies exactly on the
	// arm (DF_LEqual passes identical geometry, as the torso breath relies on).
	// It also rides the arm's placement prefix, so the near-eye fade applies.
	private Actor  armBreath[2];
	private string armBreathClass[2];

	private static string armBreathClassFor(string worn)
	{
		if (worn.IndexOf("Green") >= 0) worn = worn.Left(worn.Length() - 5);
		else if (worn.IndexOf("Blue") >= 0) worn = worn.Left(worn.Length() - 4);
		return worn .. "Red";
	}

	private void syncArmBreath(PlayerPawn pawn)
	{
		for (int i = 0; i < 2; ++i)
		{
			int s = RSLOT_ARM_R + i;
			string want = (parts[s] && partClass[s] != "") ? armBreathClassFor(partClass[s]) : "";
			class<Actor> cls = (want != "") ? (class<Actor>)(want) : null;

			if (!cls || breathAlpha <= 0.0)
			{
				if (armBreath[i]) armBreath[i].Destroy();
				armBreath[i] = null; armBreathClass[i] = "";
				continue;
			}

			if (!armBreath[i] || armBreathClass[i] != want)
			{
				if (armBreath[i]) armBreath[i].Destroy();
				armBreath[i] = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);
				armBreathClass[i] = want;
				if (!armBreath[i]) continue;
				armBreath[i].A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");
				placeActor(pawn, armBreath[i], s);
				armBreath[i].ClearInterpolation();
			}
			placeActor(pawn, armBreath[i], s);
			armBreath[i].A_SetRenderStyle(breathAlpha, STYLE_Translucent);
		}
	}

	// ---- the holster in reach: breathe it --------------------------------
	//
	// When a squeeze of this hand would store or draw at a holster, that
	// holster breathes in rs_body_holster_glow_color -- "is my hand in the right
	// place" answered without looking down. Driven by the holster handler's own
	// claim (RS_VRBodyHolsters.claimSlot), so it lights exactly when a grip
	// would act and never when it would not.
	//
	// A COPY OF THE HOLSTER MESH, the breath's technique: placed by placeActor
	// so it lies exactly on the holster, drawn flat in the chosen colour
	// (STYLE_TranslucentStencil, fillcolor via SetShade) with its alpha on a
	// slow sine. The engine's outline effect cannot do this -- it is
	// sprite-only (hw_sprites.cpp), and a holster is a model.
	private Actor  glow[2];
	private int    glowSlot[2];
	private String glowClass[2];
	private double glowPhase;

	private void syncHolsterGlow(PlayerPawn pawn)
	{
		let hol = RS_VRBodyHolsters(EventHandler.Find("RS_VRBodyHolsters"));
		bool on = hol != null && cvb("rs_body_holster_glow", true);

		glowPhase += 1.0 / (1.3 * 35.0);
		if (glowPhase >= 1.0) glowPhase -= 1.0;
		double peak  = clamp(cvf("rs_body_holster_glow_strength", 0.6), 0.05, 1.0);
		double alpha = peak * (0.35 + 0.65 * (0.5 - 0.5 * cos(glowPhase * 360.0)));
		int    col   = cvi("rs_body_holster_glow_color", 0x40FF80);

		for (int h = 0; h < 2; ++h)
		{
			int s = on ? hol.claimSlot[h] : -1;
			if (s < RSLOT_HOLSTER_0 || s > RSLOT_HOLSTER_8 || !parts[s] || partClass[s] == "") s = -1;
			// Both hands on one holster: one glow, not two stacked.
			if (h == 1 && s >= 0 && glow[0] && glowSlot[0] == s) s = -1;

			if (s < 0)
			{
				if (glow[h]) glow[h].Destroy();
				glow[h] = null;
				continue;
			}

			if (!glow[h] || glowSlot[h] != s || glowClass[h] != partClass[s])
			{
				if (glow[h]) glow[h].Destroy();
				glow[h] = null;
				class<Actor> cls = (class<Actor>)(partClass[s]);
				if (!cls) continue;
				glow[h] = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);
				if (!glow[h]) continue;
				glow[h].A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");
				glowSlot[h]  = s;
				glowClass[h] = partClass[s];
				placeActor(pawn, glow[h], s);
				glow[h].ClearInterpolation();
			}
			placeActor(pawn, glow[h], s);
			glow[h].SetShade(col);
			glow[h].A_SetRenderStyle(alpha, STYLE_TranslucentStencil);
		}
	}


	// ---- a holster's page lights that holster ---------------------------
	//
	// One copy of each holster's mesh, always present, drawn only while its
	// rs_body_hl<ID> is above zero. AActor::VisibleCVar is read by the RENDERER
	// every frame, so this answers while the menu has the game paused -- no
	// play-side script runs then, which is why the in-reach glow cannot. The
	// holster's page sets the cvar on open and clears it on leave
	// (RS_HolsterPageMenu, body_menu.zs).
	//
	// Same mesh, placed by placeActor with the same live-fit prefix, so it lies
	// exactly on the holster and moves with that holster's sliders.
	private Actor  hlCopy[16];
	private String hlClass[16];

	private void syncHolsterHighlights(PlayerPawn pawn)
	{
		int    col = cvi("rs_body_holster_glow_color", 0x40FF80);
		double str = clamp(cvf("rs_body_holster_glow_strength", 0.6), 0.05, 1.0);

		for (int s = RSLOT_HOLSTER_0; s <= RSLOT_HOLSTER_8; ++s)
		{
			if (!parts[s] || partClass[s] == "")
			{
				if (hlCopy[s]) hlCopy[s].Destroy();
				hlCopy[s] = null;
				continue;
			}

			if (!hlCopy[s] || hlClass[s] != partClass[s])
			{
				if (hlCopy[s]) hlCopy[s].Destroy();
				hlCopy[s] = null;
				class<Actor> cls = (class<Actor>)(partClass[s]);
				if (!cls) continue;
				hlCopy[s] = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);
				if (!hlCopy[s]) continue;
				hlCopy[s].A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");
				hlCopy[s].VisibleCVar = HOLSTER_GATE[s - RSLOT_HOLSTER_0];
				hlClass[s] = partClass[s];
				placeActor(pawn, hlCopy[s], s);
				hlCopy[s].ClearInterpolation();
			}

			placeActor(pawn, hlCopy[s], s);
			hlCopy[s].SetShade(col);
			hlCopy[s].A_SetRenderStyle(str, STYLE_TranslucentStencil);
		}
	}


	private void syncSlotPart(PlayerPawn pawn, int s)
	{
		string kind  = slotKind(s);
		// THE TORSO IS DECIDED, not read: the menu's colour is only its base,
		// and armour and health override it every tic. See torsoStyle.
		string style;
		if (s == RSLOT_TORSO)                  style = torsoStyle(pawn);
		else if (slotFrame(s) == RFRAME_ARM)   style = armStyle(pawn, s);
		else                                   style = cvs("rs_body_style_" .. kind, "");
		string want  = lookup(kind, style);

		if (!cvb("rs_body_enabled", true)) want = "";
		if (handSlotIsForeign(s))          want = "";
		// AN ARM NEEDS A TORSO TO HANG FROM AND A HAND ACTOR TO REACH. Psprite
		// hands have no model the engine can put a wrist on, so with none there is
		// no arm at all rather than one bent at nothing (plan 3a).
		if (slotFrame(s) == RFRAME_ARM)
		{
			int sock;
			if (!parts[RSLOT_TORSO] || !armTarget(s, sock)) want = "";
		}
		if (want == partClass[s] && (parts[s] || want == "")) return;

		if (parts[s]) { parts[s].Destroy(); parts[s] = null; }
		partClass[s] = want;
		if (want == "") return;

		class<Actor> cls = (class<Actor>)(want);
		if (!cls)
		{
			if (!warnedSpawn)
			{
				Console.Printf("\c[Red]RS_VRBody: no such class \"%s\" for %s", want, slotName(s));
				warnedSpawn = true;
			}
			partClass[s] = "";
			return;
		}
		parts[s] = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);

		// THE SAME CALL THE TEST PISTOL MAKES, and it is the only thing that
		// differed between a part whose placement sliders worked and one whose
		// did not. A_ChangeModel with empty arguments changes no model; what it
		// does is ALLOCATE the per-actor model data the render path consults.
		//
		// Four separate readings of the MODELDEF, the cvar declarations and the
		// menu wiring all said the hands were correct, because they were. The
		// difference was never in any of them.
		if (parts[s])
		{
			parts[s].A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");

			// PLACED NOW, HISTORY CLEARED. It was spawned at the pawn's feet,
			// and a part swapped mid-play -- picking up armour does it -- would
			// otherwise be drawn for a frame sliding up from there to where it
			// is worn.
			placeSlot(pawn, s);
			parts[s].ClearInterpolation();
		}
	}

	// ---- the edit surface ------------------------------------------------
	//
	// Seven sliders, and a selector saying which slot they drive. The
	// alternative is seven cvars times fourteen slots in the menu, which nobody
	// can find anything in. On a slot change the sliders are LOADED FROM the
	// slot; otherwise they are written BACK TO it, so a slider is always showing
	// the truth about the slot named above it.

	private void pumpEdit()
	{
		int es = clamp(cvi("rs_body_edit_slot", 0), 0, RSLOT_COUNT - 1);

		// A HAND IS NEVER EDITED HERE. It rides the controller, not you, so its
		// numbers are MODELDEF placement cvars the RENDERER reads -- which is
		// what makes those move a hand while you are looking at the slider.
		//
		// This page cannot do that for anything: it is script, and script does
		// not run while a menu is open. Relaying hand values through it was
		// worse than leaving them out, because a slider that only takes effect
		// once you close the menu is indistinguishable from one that is broken.
		if (slotFrame(es) != RFRAME_BODY) return;

		if (es != lastEditSlot)
		{
			lastEditSlot = es;
			setf("rs_body_p_fwd",   sFwd[es]);
			setf("rs_body_p_side",  sSide[es]);
			setf("rs_body_p_up",    sUp[es]);
			setf("rs_body_p_yaw",   sYaw[es]);
			setf("rs_body_p_pitch", sPitch[es]);
			setf("rs_body_p_roll",  sRoll[es]);
			setf("rs_body_p_scale", sScale[es]);
			Console.Printf("\c[Gold]RS_VRBody: editing %s", slotName(es));
			return;
		}

		sFwd[es]   = cvf("rs_body_p_fwd",   sFwd[es]);
		sSide[es]  = cvf("rs_body_p_side",  sSide[es]);
		sUp[es]    = cvf("rs_body_p_up",    sUp[es]);
		sYaw[es]   = cvf("rs_body_p_yaw",   sYaw[es]);
		sPitch[es] = cvf("rs_body_p_pitch", sPitch[es]);
		sRoll[es]  = cvf("rs_body_p_roll",  sRoll[es]);
		sScale[es] = cvf("rs_body_p_scale", sScale[es]);
	}

	private static void setf(string n, double v)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		if (c) c.SetFloat(v);
	}
	private static void seti(string n, int v)
	{
		let c = CVar.GetCVar(n, players[consoleplayer]);
		if (c && c.GetInt() != v) c.SetInt(v);
	}

	// ---- persistence -----------------------------------------------------

	private void saveProfile(string name)
	{
		level.JSONProfileBegin();
		for (int s = 0; s < RSLOT_COUNT; ++s)
		{
			string k = String.Format("s%d_", s);
			level.JSONProfileSetDouble(k .. "fwd",   sFwd[s]);
			level.JSONProfileSetDouble(k .. "side",  sSide[s]);
			level.JSONProfileSetDouble(k .. "up",    sUp[s]);
			level.JSONProfileSetDouble(k .. "yaw",   sYaw[s]);
			level.JSONProfileSetDouble(k .. "pitch", sPitch[s]);
			level.JSONProfileSetDouble(k .. "roll",  sRoll[s]);
			level.JSONProfileSetDouble(k .. "scale", sScale[s]);
		}
		if (level.JSONProfileSave(name))
			Console.Printf("\c[Gold]RS_VRBody: saved \"%s\"", name);
		else
			Console.Printf("\c[Red]RS_VRBody: could not save \"%s\"", name);
	}

	private void loadProfile(string name)
	{
		if (!level.JSONProfileLoad(name)) return;
		for (int s = 0; s < RSLOT_COUNT; ++s)
		{
			string k = String.Format("s%d_", s);
			sFwd[s]   = level.JSONProfileGetDouble(k .. "fwd",   sFwd[s]);
			sSide[s]  = level.JSONProfileGetDouble(k .. "side",  sSide[s]);
			sUp[s]    = level.JSONProfileGetDouble(k .. "up",    sUp[s]);
			sYaw[s]   = level.JSONProfileGetDouble(k .. "yaw",   sYaw[s]);
			sPitch[s] = level.JSONProfileGetDouble(k .. "pitch", sPitch[s]);
			sRoll[s]  = level.JSONProfileGetDouble(k .. "roll",  sRoll[s]);
			sScale[s] = level.JSONProfileGetDouble(k .. "scale", sScale[s]);
		}
		lastEditSlot = -1;   // force the sliders to reload from the new numbers
		Console.Printf("\c[Gold]RS_VRBody: loaded \"%s\"", name);
	}

	override void NetworkProcess(ConsoleEvent e)
	{
		if (e.Player != consoleplayer) return;
		ensure();
		PlayerPawn pawn = players[consoleplayer].mo;
		if (!pawn) return;
		if (e.Name ~== "rs_body_edit")
		{
			bool wasHolding = grabbedMain >= 0 || grabbedOff >= 0;
			editMode = !editMode;
			grabbedMain = -1; grabbedOff = -1;
			// A grip already held when it switches on must not also pick something up.
			prevGripMain = pawn.GripHeldMain;
			prevGripOff  = pawn.GripHeldOff;
			if (!editMode && wasHolding) saveProfile("vrbody");
			showMsg(editMode
				? "PLACEMENT MODE ON -- grip a holster to pick it up, grip again to drop it"
				: "Placement mode off");
			return;
		}
		if (e.Name ~== "rs_body_holtest") { startHolsterTest(); return; }
		if (e.Name ~== "rs_body_grab_main") { if (editMode) toggleGrab(pawn, true);  return; }
		if (e.Name ~== "rs_body_grab_off")  { if (editMode) toggleGrab(pawn, false); return; }
		// NUDGE A HAND FROM THE CONSOLE, with no menu anywhere in the path.
		//
		// Six rounds of "the sliders do nothing" turned out to be the owner on a
		// page that did not write the cvar the renderer reads. This writes it
		// directly and prints the value, so "does moving this number move the
		// hand" can be answered in one keypress without trusting any menu.
		if (e.Name ~== "rs_body_handtest")
		{
			double v = cvf("rs_bp_handmain_ofs_x", 0.0) + 0.05;
			if (v > 1.0) v = -1.0;
			setf("rs_bp_handmain_ofs_x", v);
			Console.Printf("\c[Gold]rs_bp_handmain_ofs_x = %.2f  -- the main hand should have moved", v);
			return;
		}

		if (e.Name ~== "rs_body_arm_calibrate") { calibrateArms(pawn); return; }
		if (e.Name ~== "rs_body_save")  { saveProfile("vrbody"); return; }
		if (e.Name ~== "rs_body_load")  { loadProfile("vrbody"); return; }
		if (e.Name ~== "rs_body_reset")
		{
			int es = clamp(cvi("rs_body_edit_slot", 0), 0, RSLOT_COUNT - 1);
			double f, sd, u, y, p, r, sc;
			defaultSeat(es, f, sd, u, y, p, r, sc);
			sFwd[es] = f; sSide[es] = sd; sUp[es] = u;
			sYaw[es] = y; sPitch[es] = p; sRoll[es] = r; sScale[es] = sc;
			lastEditSlot = -1;
			Console.Printf("\c[Gold]RS_VRBody: reset %s", slotName(es));
			return;
		}
		if (e.Name ~== "rs_body_dump")
		{
			// Plain %s / %.1f only. ZScript's Printf is not C's and width and
			// justification specifiers are not worth discovering the hard way in
			// a diagnostic whose entire job is to be readable when something else
			// has already gone wrong.
			for (int s = 0; s < RSLOT_COUNT; ++s)
				Console.Printf("[%d] %s: fwd %.1f side %.1f up %.1f | yaw %.0f pitch %.0f roll %.0f | scale %.2f | %s",
					s, slotName(s), sFwd[s], sSide[s], sUp[s], sYaw[s], sPitch[s], sRoll[s], sScale[s],
					partClass[s] == "" ? "(empty)" : partClass[s]);
			return;
		}
	}

	// ---- markers -----------------------------------------------------------
	//
	// THE REACH TEST IS INVISIBLE AND THAT IS ITS WHOLE DANGER.
	//
	// nearestSlot measures pawn.AttackPos against slotWorldAt(). If AttackPos is
	// not where the hand is DRAWN, the radius is being measured from somewhere
	// else and a reach that looks correct simply never fires -- with nothing in
	// any log to say why, because nothing is wrong enough to report.
	//
	// That is the exact failure that cost this session a night: correct-looking
	// code, a silent cancellation, and a gesture that never triggers. Three
	// particles behind a cvar make it a one-glance question instead.
	//
	// Offsets are relative to the pawn because A_SpawnParticle takes them that
	// way; the whole point is to draw where the CODE thinks things are, so a
	// disagreement with the drawn hand is visible rather than inferred.
	private void drawMarkers(PlayerPawn pawn)
	{
		if (!cvb("rs_body_reach_markers", true)) return;

		Vector3 mh = pawn.AttackPos  - pawn.Pos;
		Vector3 oh = pawn.OffhandPos - pawn.Pos;
		pawn.A_SpawnParticle(0xFF3030, 0, 2, 4.0, 0, mh.x, mh.y, mh.z);   // main hand, red
		pawn.A_SpawnParticle(0x30A0FF, 0, 2, 4.0, 0, oh.x, oh.y, oh.z);   // off hand, blue

		// Every holster the reach test can actually see. A holster with no
		// marker is one nearestSlot is skipping.
		for (int s = RSLOT_HOLSTER_0; s <= RSLOT_HOLSTER_8; ++s)
		{
			if (!parts[s]) continue;
			Vector3 d = SlotWorld(pawn, s) - pawn.Pos;
			bool held = (s == grabbedMain || s == grabbedOff);
			pawn.A_SpawnParticle(held ? 0xFFD000 : 0x40FF40, 0, 2, 3.0, 0, d.x, d.y, d.z);
		}
	}

	// ---- the one pass ----------------------------------------------------

	override void WorldTick()
	{
		PlayerPawn pawn = players[consoleplayer].mo;
		if (!pawn) return;

		ensure();
		pumpEdit();
		updateBodyYaw(pawn);
		if (editMode)
		{
			pollGripGrabs(pawn);
			updateGrabs(pawn);
		}
		drawMarkers(pawn);

		// BEFORE the slot loop, and outside it, because it has to run whether or
		// not this rig owns a hand -- when RS_WorldHands is loaded the hand slots
		// are empty and this is the only thing still speaking for them.
		publishPose();
		dressWorldHands();

		// ONE LOOP. Every worn thing is spawned and placed here, in the same tic,
		// from the same head pose, through the same function. When only half the
		// rig had a body seat the other half was still on the tic rate and the two
		// came apart -- which is what "the models never stayed in the holsters"
		// actually was.
		for (int s = 0; s < RSLOT_COUNT; ++s)
		{
			syncSlotPart(pawn, s);
			placeSlot(pawn, s);
		}

		// WHERE EACH HOLSTER IS DRAWN, once per tic: ModelPointToWorld replays
		// the renderer's own matrix, seat and live fit included, and SlotWorld is
		// asked dozens of times a tic. A point far from the seat means no pose or
		// no model this tic, and the seat is trusted instead.
		for (int hs = RSLOT_HOLSTER_0; hs <= RSLOT_HOLSTER_8; ++hs)
		{
			drawnValid[hs] = false;
			if (!parts[hs]) continue;
			Vector3 pw, pf, pu;
			[pw, pf, pu] = parts[hs].ModelPointToWorld(0, 0, 0);
			if ((pw - slotWorldAt(pawn, hs)).Length() > 64.0) continue;
			drawnAt[hs]    = pw;
			drawnValid[hs] = true;
		}
		tickHolsterTest();


		// Before the breath, which fades with it -- see applyLookFade.
		applyLookFade(pawn);

		// After the loop: it lies over the torso, so the torso has to have been
		// decided and placed this tic first.
		syncBreath(pawn);
		// The same breath on the arms, at the alpha syncBreath just set.
		syncArmBreath(pawn);

		// Also after the loop: it lies over a holster the loop just placed.
		syncHolsterGlow(pawn);
		// And one always-present copy per holster, lit only from its own page.
		syncHolsterHighlights(pawn);
	}
}

// ============================================================================
// WHICH ARMOUR YOU ARE WEARING -- as opposed to how much armour you have.
//
// The vest has to follow a PICKUP, not a number: pick up green armour and you
// wear the green vest; drop below 100 and it comes off; climb back to 100 on
// bonuses and only the colour changes. The armour itself cannot answer that --
// BasicArmor.ArmorType is set by a suit AND by a bonus picked up from zero
// (armor.zs, BasicArmorBonus.Use), and touching a suit you cannot use changes
// nothing at all. So this watches the pickups themselves.
//
// AN INVENTORY ITEM ON THE PLAYER, not a field on the rig, because the rig is
// an EventHandler and is rebuilt every level while your armour carries over.
// This travels with you, and is saved with you. It has no icon and never
// appears anywhere; the rig gives it to the player the first tic it is missing.
// ============================================================================
class RS_BodyArmorWatch : Inventory
{
	const GREEN_AT = 100;   // a suit worth this much is the green vest ...
	const BLUE_AT  = 150;   // ... and this much the blue; also where each comes off

	int suit;    // 0 no vest, 1 green, 2 blue
	int coverFloor;   // the vest stays on while armour is at or above this

	// A suit that has been OFFERED -- HandlePickup runs before the armour
	// decides whether it wants it -- and the armour as it stood at that moment.
	private Name pending;
	private int  pendingSave;
	private int  pendingTic;
	private int  pendingPrevAmount;
	private Name pendingPrevType;

	Default
	{
		+INVENTORY.UNDROPPABLE
		+INVENTORY.UNTOSSABLE
		Inventory.MaxAmount 1;
	}

	override bool HandlePickup(Inventory item)
	{
		let offered = BasicArmorPickup(item);
		if (offered && Owner)
		{
			let arm = BasicArmor(Owner.FindInventory("BasicArmor"));
			pending           = item.GetClassName();
			pendingSave       = offered.GetSaveAmount();   // skill-scaled, as Use applies it
			pendingTic        = level.maptime;
			pendingPrevAmount = arm ? arm.Amount : 0;
			pendingPrevType   = arm ? arm.ArmorType : 'None';
		}
		return Super.HandlePickup(item);   // never consumes anything itself
	}

	override void DoEffect()
	{
		Super.DoEffect();
		let arm = Owner ? BasicArmor(Owner.FindInventory("BasicArmor")) : null;
		int amount = arm ? arm.Amount : 0;

		// CONFIRMED only if the armour actually TOOK it: it now names this
		// suit, and it went up. A refused touch leaves both unchanged -- which
		// is the case that would otherwise put the vest back on for free, since
		// green armour already at 100 names GreenArmor whether you just touched
		// another one or not.
		if (pending != 'None')
		{
			if (arm && arm.ArmorType == pending
				&& (amount > pendingPrevAmount || arm.ArmorType != pendingPrevType))
			{
				if (pendingSave >= BLUE_AT)       { suit = 2; coverFloor = BLUE_AT; }
				else if (pendingSave >= GREEN_AT) { suit = 1; coverFloor = GREEN_AT; }
				// Anything smaller -- some mods have half-suits -- is not a vest.
				pending = 'None';
			}
			else if (level.maptime - pendingTic > 2)
			{
				pending = 'None';
			}
		}

		// OFF when it no longer covers you, and it stays off: nothing but the
		// next suit you pick up sets it again.
		if (suit > 0 && amount < coverFloor) { suit = 0; coverFloor = 0; }
	}
}
