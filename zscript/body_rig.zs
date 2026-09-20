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
	// THE WHOLE BODY -- one rigged model that is the torso, both arms, both hands,
	// the legs and the helmet at once. It does not sit alongside the parts above:
	// with rs_body_whole on it REPLACES them and they are left empty. Appended,
	// like the arms and the helmet, so no saved slot index shifts under a profile.
	RSLOT_BODY,
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

	// The legs. An object rather than more arrays on this class, because the walk
	// is a state machine with its own per-player state and it has no business
	// sharing a namespace with the seat table. See body_legs.zs.
	private RS_VRLegs legs;

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
		if (s == RSLOT_BODY)                             return "body";
		return "boot";
	}

	// WHICH SLOTS A WHOLE BODY MAKES REDUNDANT. Everything the one mesh already
	// contains: the torso, both arms, both hands, both boots and the helmet.
	// Holsters and the pouch are deliberately absent -- see syncSlotPart.
	static bool wholeBodyReplaces(int s)
	{
		return s == RSLOT_TORSO || s == RSLOT_HAND_MAIN || s == RSLOT_HAND_OFF
		    || s == RSLOT_ARM_R || s == RSLOT_ARM_L || s == RSLOT_HELMET
		    || s == RSLOT_BOOT_L || s == RSLOT_BOOT_R;
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
			case RSLOT_BODY:       return "Body (whole)";
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
			// A WHOLE BODY IS SEATED FROM THE FLOOR, not from the neck: his own
			// origin is between his boots and he stands 64.7 units. A starting
			// point to drag from, as every seat here is.
			case RSLOT_BODY:       f =  0; sd =   0; u = -50.0;            break;
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
			saveProfile(profileName());
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

		// The Quake hands (hand.mdl's eighteen frames) are out (owner, 2026-09-15), so every hand
		// this rig draws is on the RS hand's skeleton and frames: any other style name -- one an
		// old ini saved -- reads the same table.
		return poseFrame("rs", pose);
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
				                      : "rs_body_style_handoff", "rs");

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
		int want = poseFrame(cvs("rs_body_style_" .. (hand == 0 ? "handmain" : "handoff"), "rs"), pose);
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
		// WHOLE BODIES. One line per character, and that is the whole cost of
		// adding one -- no torso style, no arm pair, no hand variant, no pairing.
		reg("body",     "marine",  "RS_PartBodyMarine");
		reg("body",     "praetor", "RS_PartBodyPraetor");
		reg("handmain", "praetor", "RS_HandPraetorMain");
		reg("handoff",  "praetor", "RS_HandPraetorOff");
		// The invisible things the whole body's arms reach for -- see RS_BodyHandAnchor.
		// NO HAND ENTRY FOR THE MARINE. His hands are part of his mesh, so there is
		// nothing to register and nothing is spawned -- see the note at syncSlotPart.
		// The classes and their MODELDEF blocks stay on disk unused, because the
		// split may yet come back if the owner wants pinning more than attachment.
		reg("handmain", "anchor", "RS_BodyHandAnchor");
		reg("handoff",  "anchor", "RS_BodyHandAnchor");

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
		reg("handmain", "rs",     "RS_PartHandIQMMain");
		reg("handoff",  "rs",     "RS_PartHandIQMOff");
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
		// FALL BACK TO THE OLD SHARED PROFILE if this body has none of its own yet.
		// The owner has hand-tuned "vrbody" over weeks; a per-body split that started
		// everyone from defaults would read as having lost all of it.
		curProfile = profileName();
		if (!level.JSONProfileLoad(curProfile)) loadProfile("vrbody");
		else loadProfile(curProfile);
	}

	// The profile currently loaded, so a body switch knows what to save back.
	private string curProfile;

	// Called every tic. A body style change saves the body you are leaving and loads
	// the one you are arriving at, so neither is ever half-applied.
	private void pumpProfile()
	{
		string want = profileName();
		if (want == curProfile) return;
		if (curProfile != "") saveProfile(curProfile);
		curProfile = want;
		if (!level.JSONProfileLoad(want))
		{
			Console.Printf("\c[Gold]RS_VRBody: no holster layout for \"%s\" yet -- "
			               "keeping the current one, and it saves under that name.", want);
			return;
		}
		loadProfile(want);
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
		wholeHeadOn = null;   // a new body actor wears its MODELDEF skins again
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

	// ---- A DIAGNOSTIC THAT IS OFF UNTIL ASKED FOR --------------------------
	//
	// TWO THINGS WERE WRONG WITH THE FIRST VERSION OF THIS AND BOTH REACHED THE OWNER.
	//
	// IT SET AN ENGINE CVAR FROM PLAY SCOPE. `CVar.FindCVar("r_reachchain_debug").SetBool()`
	// from WorldTick aborts the VM -- "Attempt to change CVAR outside of menu code" -- and
	// took the game down on every map load. The refusal is CORRECT and is not to be worked
	// around: a play-scope script flipping an engine render cvar is exactly what that guard
	// exists to stop. An engine debug cvar is the owner's to set from the console. A cvar
	// this package DECLARES is ours. The trace is no longer touched from here at all.
	//
	// AND IT RAN WITHOUT BEING ASKED. It armed itself on map load in a normal game. A
	// diagnostic that decides for itself when to run is a diagnostic in somebody's way, and
	// this package has shipped default-on debug toggles before. rs_body_diag defaults FALSE
	// and nothing below happens until it is switched on.
	//
	// WHAT IT STILL DOES, once asked: writes the numbers ZScript can actually see to
	// rs_profiles/bodydiag.json -- where the headset is, where the body is seated, where
	// each arm's target is, and HOW FAR THAT TARGET IS FROM THE BODY'S SEAT. That last one
	// is the one that matters: a target further from the shoulder than the arm is long
	// cannot be reached, and the hand stops short wherever the arm ran out. If it is inside
	// arm's length instead, the arm is reaching and the fault is at the wrist.
	//
	// For the solver's own internals -- shoulder, elbow, gap, stretch -- `r_reachchain_debug 1`
	// in the console is the tool, and it belongs to whoever is at the console.
	private int    diagTics;
	private double diagAir, diagHeldR, diagHeldL, diagHead;
	private double diagMaxLbs, diagMaxLean, diagMaxReach;

	private void diagBurst(PlayerPawn pawn)
	{
		if (!cvb("rs_body_diag", false)) return;
		if (!pawn || !parts[RSLOT_BODY]) return;

		// STICKY, because a once-a-second snapshot misses the moment being reported.
		// "It looked wrong when I jumped" is useless if the sample landed while standing.
		// These accumulate from level start and answer "did this EVER happen", which is
		// the question actually being asked.
		diagTics++;
		bool praetorNow = (cvs("rs_body_whole_style", "marine") == "praetor");
		if (pawn.pos.z > pawn.floorz + 1.0 && !pawn.bOnMobj) diagAir = 1;
		if (handHolds(pawn, 0)) diagHeldR = 1;
		if (handHolds(pawn, 1)) diagHeldL = 1;
		if (headCopy) diagHead = 1;
		double wR = heldLbs(pawn, 0), wL = heldLbs(pawn, 1);
		if (wR + wL > diagMaxLbs) diagMaxLbs = wR + wL;
		// NO HEADSET, NO DISTANCES. HmdPos is (0,0,0) whenever the VR backend has not
		// written it -- every non-VR run, and any frame the runtime drops -- and the
		// distance from the pawn to the origin is then thousands of map units. These are
		// STICKY MAXIMA, so ONE such frame would poison lean_max and reach_max for the
		// rest of the level and make a real report unreadable. Caught on the very first
		// boot test, which reported a 4427-unit lean.
		double leanNow = 0;
		bool haveHmd = (pawn.HmdPos != (0, 0, 0));
		if (haveHmd)
		{
			double dx = pawn.HmdPos.X - pawn.pos.X, dy = pawn.HmdPos.Y - pawn.pos.Y;
			leanNow = sqrt(dx * dx + dy * dy);
			if (leanNow > diagMaxLean) diagMaxLean = leanNow;
			for (int h = 0; h < 2; ++h)
				if (handTgt[h] && handTgt[h].pos != (0, 0, 0))
				{
					double d = (handTgt[h].pos - pawn.HmdPos).Length();
					if (d > diagMaxReach) diagMaxReach = d;
				}
		}

		// ROLLING, ONCE A SECOND, OVERWRITING. The old report fired once at tic 70 and
		// stopped, so it described the first two seconds of a level and nothing the owner
		// ever actually reported. This one always holds the LATEST state plus the sticky
		// extremes above, so "check the log" has something in it whenever he says it.
		if (diagTics % 35 == 0)
		{
			Vector3 bodyAt = slotWorldAt(pawn, RSLOT_BODY);
			int sr, sl;
			Actor hr = armTarget(RSLOT_ARM_R, sr);
			Actor hl = armTarget(RSLOT_ARM_L, sl);
			level.JSONProfileBegin();
			level.JSONProfileSetDouble("style_is_praetor",
				cvs("rs_body_whole_style", "marine") == "praetor" ? 1 : 0);
			level.JSONProfileSetDouble("hmd_x", pawn.HmdPos.X);
			level.JSONProfileSetDouble("hmd_y", pawn.HmdPos.Y);
			level.JSONProfileSetDouble("hmd_z", pawn.HmdPos.Z);
			level.JSONProfileSetDouble("seat_x", bodyAt.X);
			level.JSONProfileSetDouble("seat_y", bodyAt.Y);
			level.JSONProfileSetDouble("seat_z", bodyAt.Z);
			level.JSONProfileSetDouble("seat_fwd", sFwd[RSLOT_BODY]);
			level.JSONProfileSetDouble("seat_side", sSide[RSLOT_BODY]);
			level.JSONProfileSetDouble("seat_up", sUp[RSLOT_BODY]);
			level.JSONProfileSetDouble("body_yaw", mBodyYaw);
			level.JSONProfileSetDouble("body_scale", sScale[RSLOT_BODY]);
			level.JSONProfileSetDouble("body_actor_x", parts[RSLOT_BODY].pos.X);
			level.JSONProfileSetDouble("body_actor_y", parts[RSLOT_BODY].pos.Y);
			level.JSONProfileSetDouble("body_actor_z", parts[RSLOT_BODY].pos.Z);
			level.JSONProfileSetDouble("r_null", hr ? 0 : 1);
			level.JSONProfileSetDouble("l_null", hl ? 0 : 1);
			if (hr)
			{
				level.JSONProfileSetDouble("r_is_worldhand",
					hr.GetClassName() == 'RS_HandWorldMain' ? 1 : 0);
				level.JSONProfileSetDouble("r_x", hr.pos.X);
				level.JSONProfileSetDouble("r_y", hr.pos.Y);
				level.JSONProfileSetDouble("r_z", hr.pos.Z);
				level.JSONProfileSetDouble("r_dist_from_seat", (hr.pos - bodyAt).Length());
				level.JSONProfileSetDouble("r_dist_from_hmd", (hr.pos - pawn.HmdPos).Length());
			}
			if (hl)
			{
				level.JSONProfileSetDouble("l_is_worldhand",
					hl.GetClassName() == 'RS_HandWorldOff' ? 1 : 0);
				level.JSONProfileSetDouble("l_x", hl.pos.X);
				level.JSONProfileSetDouble("l_y", hl.pos.Y);
				level.JSONProfileSetDouble("l_z", hl.pos.Z);
				level.JSONProfileSetDouble("l_dist_from_seat", (hl.pos - bodyAt).Length());
				level.JSONProfileSetDouble("l_dist_from_hmd", (hl.pos - pawn.HmdPos).Length());
			}
			// ---- everything shipped today, and whether it is actually on ----
			level.JSONProfileSetDouble("secs", diagTics / 35.0);
			level.JSONProfileSetDouble("have_hmd", haveHmd ? 1 : 0);
			level.JSONProfileSetDouble("praetor", praetorNow ? 1 : 0);
			// Which services answered. A missing one explains a dead feature outright:
			// no pose service = fingers cannot know what is held; no weight service =
			// no sag and no load, and both would otherwise look like a tuning problem.
			level.JSONProfileSetDouble("svc_pose", poseSv ? 1 : 0);
			level.JSONProfileSetDouble("svc_grip", gripSv ? 1 : 0);
			level.JSONProfileSetDouble("svc_weight", wgtSv ? 1 : 0);
			// Fingers
			level.JSONProfileSetDouble("held_r_now", handHolds(pawn, 0) ? 1 : 0);
			level.JSONProfileSetDouble("held_l_now", handHolds(pawn, 1) ? 1 : 0);
			level.JSONProfileSetDouble("ever_held_r", diagHeldR);
			level.JSONProfileSetDouble("ever_held_l", diagHeldL);
			level.JSONProfileSetDouble("fingers_on", cvb("rs_body_fingers", true) ? 1 : 0);
			level.JSONProfileSetDouble("finger_sign", cvf("rs_body_finger_sign", -1.0));
			// Wrist
			level.JSONProfileSetDouble("wrist_turn", cvf("rs_body_wrist_turn", 0));
			level.JSONProfileSetDouble("wrist_roll_share", cvf("rs_body_wrist_roll_share", 0.6));
			// Lean, and how far he actually leaned
			level.JSONProfileSetDouble("lean_on", cvb("rs_body_lean", true) ? 1 : 0);
			level.JSONProfileSetDouble("lean_now", leanNow);
			level.JSONProfileSetDouble("lean_max", diagMaxLean);
			level.JSONProfileSetDouble("lean_span", cvf("rs_body_lean_span", 14.0));
			// Jump
			level.JSONProfileSetDouble("jump_on", cvb("rs_legs_jump", true) ? 1 : 0);
			level.JSONProfileSetDouble("airborne_now", (pawn.pos.z > pawn.floorz + 1.0 && !pawn.bOnMobj) ? 1 : 0);
			level.JSONProfileSetDouble("ever_airborne", diagAir);
			// Head copy
			level.JSONProfileSetDouble("head_copy_now", headCopy ? 1 : 0);
			level.JSONProfileSetDouble("ever_head_copy", diagHead);
			level.JSONProfileSetDouble("show_face", cvb("rs_body_show_face", true) ? 1 : 0);
			level.JSONProfileSetDouble("show_helmet", cvb("rs_body_show_helmet", true) ? 1 : 0);
			// Weight
			level.JSONProfileSetDouble("lbs_r", wR);
			level.JSONProfileSetDouble("lbs_l", wL);
			level.JSONProfileSetDouble("lbs_max", diagMaxLbs);
			level.JSONProfileSetDouble("weight_lean_on", cvb("rs_body_weight_lean", true) ? 1 : 0);
			// How far the markers ever got from the head -- proof the targets track at all
			level.JSONProfileSetDouble("reach_max", diagMaxReach);
			level.JSONProfileSave("bodydiag");
			return;
		}
	}

	// ---- THE HAND TARGETS -------------------------------------------------
	//
	// Two plain actors this rig puts on the controllers every tic, for the chains to reach.
	// They exist because a chain CANNOT aim at RS_WorldHands' hands: those ride the
	// controller inside the draw, so their ObjectToWorldMatrix leaves the world translate
	// out on purpose and the solve resolves them to the pawn. See the note in armTarget.
	//
	// AttackPos / OffhandPos are the controller positions the playsim already publishes --
	// the same pair calibrateArms measures reach from. Angles come across too, so the
	// solver's fingerDir and twist reference mean something rather than reading off an
	// actor that is not turning.
	private Actor handTgt[2];

	private void handTargets(PlayerPawn pawn)
	{
		if (!pawn) return;
		if (!parts[RSLOT_BODY])
		{
			for (int h = 0; h < 2; ++h)
				if (handTgt[h]) { handTgt[h].Destroy(); handTgt[h] = null; }
			return;
		}
		for (int h = 0; h < 2; ++h)
		{
			Vector3 p;
			double ang, pit, rol;
			if (h == 0)
			{
				p = pawn.AttackPos;   ang = pawn.AttackAngle;
				pit = pawn.AttackPitch; rol = pawn.AttackRoll;
			}
			else
			{
				p = pawn.OffhandPos;  ang = pawn.OffhandAngle;
				pit = pawn.OffhandPitch; rol = pawn.OffhandRoll;
			}
			// A zero position is "no controller this tic" -- a desktop player, or a frame
			// before tracking starts. Leave the target where it was rather than dragging
			// the arm to the map origin.
			if (p == (0, 0, 0)) continue;

			if (!handTgt[h])
			{
				handTgt[h] = Actor.Spawn("RS_VRFootTarget", p);
				if (!handTgt[h]) continue;
			}
			handTgt[h].SetOrigin(p, true);
			handTgt[h].angle = ang;
			handTgt[h].pitch = pit;
			handTgt[h].roll  = rol;
		}
	}

	// THE WALK. Driven from here rather than from placePart because it is a state
	// machine that must run exactly once a tic, while placePart runs per slot.
	//
	// bodyOrigin is the body slot's own world seat, which is where the MODEL's
	// origin sits -- and that origin is at the mesh's feet (the marine runs z
	// 0.002 .. 64.687), so it is the right point to stand the feet around.
	private void tickLegs(PlayerPawn pawn)
	{
		if (!legs || !parts[RSLOT_BODY]) return;
		if (!cvb("rs_legs_enabled", true)) return;
		double sc = sScale[RSLOT_BODY];
		if (sc <= 0.05) sc = 1.0;
		legs.Tick(pawn, slotWorldAt(pawn, RSLOT_BODY), mBodyYaw, sc,
		          cvs("rs_body_whole_style", "marine") == "praetor");
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

		// HEIGHT IS THE SEAT'S SCALE, not a second writer on the actor. The fit's
		// own _scale belongs to the mesh and the owner's slider; this is how tall
		// HE is against how tall YOU are, which is a property of the slot.
		if (s == RSLOT_BODY)
		{
			double h = cvf("rs_body_whole_height", 1.0);
			sScale[RSLOT_BODY] = (h > 0.05) ? h : 1.0;
		}

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

			// HIS HAND HAS ONE FRAME. The pose table answers in the RS hand's
			// numbering -- 1289..1297 for the manipulation set -- and the marine's
			// hand IQM carries a single bind frame, so asking the renderer to blend
			// 1295 to 1295 on a one-frame model is asking for a frame that is not
			// there. It hung the level at load.
			//
			// He gets frame 0 until his hands have poses of their own, which is the
			// open hand-posing work (SetModelJointDrawPose, a pose as joint rotations
			// rather than frames). Nothing else about the hand changes.
			String hcn = a.GetClassName();
			if (hcn.IndexOf("HandMarine") >= 0)
			{
				a.ModelFrame = 0; a.ModelFrameNext = 0; a.ModelFrameLerp = 0.0;
			}
			else
			{
				poseHand(a, hand, clamp(cvi(hand == 0 ? "rs_body_pose_main" : "rs_body_pose_off",
				                            RPOSE_OPEN), 0, RPOSE_COUNT - 1));
			}

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

		// A WHOLE BODY DRIVES ITS OWN ARMS. Two chains on ONE actor rather than an
		// arm actor each: the engine allows four per actor, and the hands at the end
		// of them are already part of this mesh.
		if (s == RSLOT_BODY) wholeBody(pawn, a);

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
	// LINT-REACH: rs_armik_rt rs_armik_lf
	// LINT-SEATS: rs_arm_sock_rs rs_arm_sock_marine

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
	// WHICH CONTROLLER AN ARM BELONGS TO. 0 is the main hand, 1 the off hand. Kept in
	// one place so armTarget and drawnHand can never disagree about the pairing.
	private int armHand(int s)
	{
		bool main = (s == RSLOT_ARM_R);
		if (cvb("rs_body_arm_swap", false)) main = !main;

		// A WHOLE BODY'S _R BONES ARE DRAWN ON THE PLAYER'S LEFT, so its arms pair the
		// other way round. Observed directly once the chains were finally solving, in
		// the owner's words: "my left shoulder and arm crosses my body and is controlled
		// by my right controller, my right shoulder and arm crosses my body and is
		// controlled by my left controller." Both arms reaching the correct controllers
		// and still crossing is the signature of a swapped pair and nothing else.
		//
		// I TOOK THIS OUT ONCE AND IT WAS A MISTAKE. The reasoning was that the original
		// "arms crossed in an X" report came from a time when no chain solved at all, so
		// the X was the mesh's own rest pose and the swap was a guess against a broken
		// measurement. The first half of that was true and the conclusion still wrong:
		// the pairing was independently reversed, and removing it put the X back for a
		// different reason. Restored, and now resting on an observation instead.
		//
		// Not rs_body_arm_swap: that cvar is the PART rig's, it also decides which hand
		// mesh that rig wears, and the owner's ini pins it false. This is a property of
		// the whole-body meshes themselves, so it belongs in code where it cannot be
		// switched off by accident. It lives here rather than in armTarget so drawnHand
		// pairs identically -- two places deciding this once already cost a day.
		if (parts[RSLOT_BODY]) main = !main;
		return main ? 0 : 1;
	}

	// THE HAND ACTUALLY DRAWN ON THAT CONTROLLER -- which is no longer the same actor
	// the chain aims at. A whole body aims at a marker this rig places (armTarget
	// below), but the drawn hand still has to be found so it can be hidden, or
	// RS_WorldHands' glove is left sitting inside the body's own hand.
	private Actor drawnHand(int s)
	{
		int hand = armHand(s);
		bool main = (hand == 0);
		int slot = main ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF;
		if (handSlotIsForeign(slot))
		{
			Actor hd = dressedOn[hand];
			if (!hd) hd = Actor(ThinkerIterator.Create(main ? "RS_HandWorldMain" : "RS_HandWorldOff").Next());
			return hd;
		}
		return parts[slot];
	}

	private Actor armTarget(int s, out int sock)
	{
		sock = 0;
		bool main = (armHand(s) == 0);

		// AIM AT A TARGET WE MOVE OURSELVES, NOT AT THE CONTROLLER-FOLLOWING HAND.
		//
		// THIS IS THE BUG THAT MADE EVERY OTHER HAND FIX LOOK LIKE IT DID NOTHING, and it
		// is stated in the engine's own comment above TargetMatrix (model_reach.cpp:722):
		//
		//     "a model riding a controller or another model never reads it
		//      (ObjectToWorldMatrix SKIPS THE WORLD TRANSLATE)"
		//
		// RS_WorldHands' hands ride the controller through MODELDEF FollowMainHand, so the
		// controller placement happens inside the draw and their ObjectToWorldMatrix
		// deliberately leaves the world translate out. A reach chain aimed at one therefore
		// resolves its target to the ACTOR's position -- which for those hands never leaves
		// the pawn. The arm report proved it: both arms reported the identical target at
		// (144, -1392, -48), the player's own x/y, 41 units under his head. The arms were
		// reaching at his chest. That is the crossed X, and it is why the measured palm
		// offset, the pairing and absolute reach all changed nothing -- the target was never
		// at the controller to begin with.
		//
		// ZScript already knows where the controllers are: AttackPos and OffhandPos, which
		// calibrateArms has been reading all along. So the chain aims at a plain actor this
		// rig moves there every tic -- the same shape the foot targets use, and for the same
		// reason: a target we place is a target that is actually where we think it is.
		//
		// A SECOND REVERSAL USED TO SIT HERE AND IT IS GONE. It was put in to answer "my arms
		// are crossed in an X", and it could not have been the cause: at the time BOTH arms
		// were reaching the same point on the player's chest, so of course they crossed, and
		// swapping which arm got which identical target changed nothing. It was a guess made
		// against a broken measurement, and leaving it in would now genuinely cross the arms
		// -- the markers below are built straight from AttackPos and OffhandPos, so the plain
		// pairing is the correct one and rs_body_arm_swap remains the one place handedness
		// is decided.
		int hand = main ? 0 : 1;
		int slot = main ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF;

		Actor hd;
		string style;
		// A WHOLE BODY AIMS AT ITS OWN TARGET, kept on the controller by handTargets()
		// below. The part rig keeps the old behaviour: its arms are separate actors with a
		// measured wrist socket, and that pairing was tuned against the hand it can see.
		if (parts[RSLOT_BODY] && handTgt[hand])
		{
			style = cvs(main ? "rs_body_style_handmain" : "rs_body_style_handoff", "rs");
			return handTgt[hand];
		}
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
			style = cvs(main ? "rs_body_style_handmain" : "rs_body_style_handoff", "rs");
		}
		// Every hand wears the rigged hand's mesh now (the Quake hands are out), so sock stays 0.
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

	// THE WHOLE BODY'S TWO ARMS, AND ITS HEAD.
	//
	// The part rig needed, per arm: a separate actor, a shoulder seat, a wrist
	// socket measured per pairing, a reshaped hand stub and a decision about which
	// hand this arm reaches. None of that is here. The chain runs down joints this
	// mesh already owns, and it ends at a hand that is already attached -- so the
	// target is simply the controller, with no socket to measure and no seam.
	private void wholeBody(PlayerPawn pawn, Actor a)
	{
		for (int i = 0; i < 2; ++i)
		{
			bool right = (i == 0);
			int  slot  = right ? RSLOT_ARM_R : RSLOT_ARM_L;

			// DECLARED FIRST, ASSIGNED AFTER -- NOT DECLARED WITH A TERNARY.
			//
			// `Vector3 v = cond ? (a,b,c) : (d,e,f);` compiles and then aborts the VM
			// the first time the function runs: "REGT_ADDROF not implemented for
			// vectors". Initialising a vector local from a conditional makes the VM
			// take the vector's address, which it cannot do. It cost a live abort on
			// the owner's next load, past a clean -norun check, because a compile
			// never calls the function. placeArm below has always used this two-step
			// form, which is why it has always worked.
			// THE JOINT NAMES ARE THE BODY'S, NOT THE MARINE'S.
			//
			// These were hardcoded to bip_upperArm_R and friends, which is id's naming
			// and exists only on the Eternal marine. The Praetor is a ValveBiped rig,
			// so on him every one of those lookups would have missed and BOTH ARMS
			// WOULD HAVE HUNG DEAD -- compiling cleanly, drawing fine, simply never
			// bending. Two rig families, one table.
			bool valve = (cvs("rs_body_whole_style", "marine") == "praetor");
			Name up, mid, wrist, tuning;
			Vector3 outward, twistRef;
			if (right)
			{
				up    = valve ? 'ValveBiped.Bip01_R_UpperArm' : 'bip_upperArm_R';
				mid   = valve ? 'ValveBiped.Bip01_R_Forearm'  : 'bip_lowerArm_R';
				wrist = valve ? 'ValveBiped.Bip01_R_Hand'     : 'bip_hand_R';
				tuning = 'rs_armik_wb_rt';
				outward = (-1, 0, 0);
				// Measured on this skeleton at its 0.872 scale, by the same method as
				// the Slayer's: index minus pinky off the forearm, in model order.
				twistRef = (0.1929, 0.6177, -0.7624);
			}
			else
			{
				up    = valve ? 'ValveBiped.Bip01_L_UpperArm' : 'bip_upperArm_L';
				mid   = valve ? 'ValveBiped.Bip01_L_Forearm'  : 'bip_lowerArm_L';
				wrist = valve ? 'ValveBiped.Bip01_L_Hand'     : 'bip_hand_L';
				tuning = 'rs_armik_wb_lf';
				outward = (1, 0, 0);
				twistRef = (-0.1929, 0.6177, -0.7624);
			}

			// A TUNING PREFIX OF ITS OWN, rs_armik_wb_*, AND THAT IS THE POINT.
			//
			// The palm has to be where the controller is. The solver was stopping short of
			// it for a reason that is not reach at all: softStart defaults to 0.90, so past
			// ninety per cent of natural extension the arm DELIBERATELY EASES OFF and lets
			// the hand lag the target. That is the right look for a character animating
			// itself and exactly wrong for a hand the player is holding -- it guarantees
			// the palm is never quite where their hand is, and no amount of stretch fixes
			// it because it happens before the stretch cap is consulted.
			//
			// The whole body therefore gets its own tuning names with VR defaults: no soft
			// ease, and the full stretch the engine allows. The part rig keeps rs_armik_*
			// unchanged -- an arm that is a separate actor has different problems.
			//
			// NEW NAMES RATHER THAN NEW DEFAULTS, deliberately. rs_armik_rt_stretch_max is
			// already saved in the owner's ini at 1.25, and a `user` cvar in the ini beats
			// any default this package ships -- so changing the old ones would have reached
			// him as no change at all. A prefix he has never had cannot be stale.
			a.SetModelReachChain(i, up, mid, wrist, tuning);
			a.SetModelReachFrame(i, outward, (0, -1, 0), (0, 0, 1), twistRef);
			a.SetModelReachFollowJoint(i, 'None');

			int sock;
			Actor hd = armTarget(slot, sock);
			if (!hd) { a.ClearModelReachChain(i); continue; }

			// THE HAND WE REACH FOR MUST NOT ALSO BE DRAWN.
			//
			// This body has hands of its own, so RS_WorldHands' hand on the same
			// controller would be a second hand inside the first. It still has to
			// EXIST -- it is what holds, grabs and throws -- so it is hidden, never
			// destroyed. rs_handworld is not
			// the switch for this: that one destroys the actors (handworld.zs
			// Reconcile), which would take the grabbing with it AND delete the thing
			// the arm is reaching for.
			//
			// Done from HERE rather than in RS_WorldHands because this is the side
			// that knows a whole body is worn, and it needs no cvar written, no cvar
			// declared in two packages, and no change to a mod that may be absent.
			//
			// ASK drawnHand, NOT the chain's target. Those used to be the same actor and
			// are not any more: a whole body aims at a marker, and hiding the marker
			// hides nothing while leaving the glove on screen inside the body's hand.
			hideReachedHand(drawnHand(slot), true);
			// THE CHAIN ENDS AT THE WRIST; THE THING THAT MUST LAND ON YOUR HAND IS THE
			// PALM. Those are not the same point and the gap is a whole hand.
			//
			// The chain's end effector is the THIRD joint given to SetModelReachChain --
			// bip_hand_R, the WRIST (model_reach.cpp, pose.wrist = MatTranslation(gEnd)).
			// The aim point is the target's model ORIGIN, and on the RS hand that origin
			// is its PALM: HANDPALM_joint measured at (0, 0.001, 0.005). So with no
			// offset the body's WRIST is placed on the player's PALM and the hand carries
			// on past it by its own wrist-to-palm length -- a little over two inches,
			// both hands, every frame. Far enough to be wrong at every grab and close
			// enough to read as intended.
			//
			// SetModelReachEndOfs (engine 567fe71f8a) is the fix and it is the RIGHT
			// side to fix it on: the offset is a property of the rig being DRIVEN and is
			// stated in ITS units, so no conversion into the hand model's scale is
			// needed. That conversion is why the previous attempt failed -- the hand
			// mesh is authored at 100x with a 0.01 root-joint scale, and the (0, 1.47, 0)
			// that sat here was lifted from the part rig on a misreading. It was never a
			// palm-to-wrist step: the RS hand's own palm-to-wrist is 9.73 model units,
			// and the SetModelReachTargetJoint call beside it that seemed to corroborate
			// it is a different feature entirely (it turns a joint ON THE TARGET, and the
			// 70 is maxDeg). Deleted rather than tuned.
			//
			// MEASURED OFF EACH MESH, not guessed: the palm is the midpoint of the wrist
			// and the four finger bases, which is the same definition the RS hand's own
			// HANDPALM sits at. Right and left mirror in x exactly, as a symmetric rig
			// should.
			//   marine  1.927 units   praetor 2.009 units
			// They differ by 0.082 -- about 2.5 mm -- so this is NOT about the two bodies
			// disagreeing. It is that the number is knowable here and was not knowable on
			// the target side.
			//
			// MODEL ORDER, (file.x, file.z, file.y), CHECKED RATHER THAN ASSUMED: the
			// twistRef literals above were derived "index minus pinky, in model order",
			// so recomputing that from the mesh identifies the convention. Swizzled it
			// lands ~10 degrees off the working literal; unswizzled it is 154 degrees off,
			// which is backwards. These offsets are written in that same order.
			// Each branch assigns its own literal. A vector assigned from a ternary of
			// literals compiles and then aborts the VM on first run -- REGT_ADDROF not
			// implemented for vectors -- which has cost this rig a live abort once.
			Vector3 endOfs;
			if (valve)
			{
				if (right) endOfs = (-1.378, -0.938, -1.120);
				else       endOfs = ( 1.378, -0.938, -1.120);
			}
			else
			{
				if (right) endOfs = (-0.624, -1.376, -1.195);
				else       endOfs = ( 0.624, -1.376, -1.195);
			}
			a.SetModelReachEndOfs(i, endOfs.x, endOfs.y, endOfs.z);

			// ABSOLUTE REACH. The palm lands ON the controller, bones scaling to span
			// whatever distance it is at, instead of the solver easing off near full
			// extension and leaving the hand short. In VR the player's real hand is ground
			// truth: a stretched arm reads as odd, a hand that is not where their hand is
			// reads as broken. Mode 0 stays the default for every other caller.
			a.SetModelReachStretchMode(i, 1);

			// THE TARGET'S TWO DIRECTIONS ARE THE MARKER'S NOW, NOT THE RS HAND'S.
			//
			// These were (0,-1,0) and (1,0,0), measured in the RS hand MODEL's space back
			// when the chain aimed at that hand. The chain aims at a plain marker now, and
			// a marker has no model -- its matrix is position and facing only, built in the
			// renderer's axis order (MarkerMatrix, model_reach.cpp). So in its space:
			//
			//     +X  the way the controller POINTS      (render x = map x)
			//     +Y  UP                                 (render y = map z)
			//     +Z  across                             (render z = map y)
			//
			// Left as they were, fingerDir (0,-1,0) meant STRAIGHT DOWN, and fingerDir is
			// not decoration: the swivel reads it to decide where the elbow goes, and the
			// end aim below reads it to decide where the hand points. Both were being told
			// the fingers point at the floor.
			//
			// Fingers point the way the controller points; the roll reference is up. A roll
			// reference only has to be off the forward axis to pin the frame, so "up" is an
			// honest answer here rather than a fitted one.
			//
			// WHICH WAY IS UP FOR A HAND IS NOT HONEST TO ASSUME, hence rs_body_wrist_turn.
			//
			// The roll reference IS the wrist's roll. The end aim below lands the bone's
			// frame on the target's, so turning this vector about the pointing axis turns
			// the hand about its own wrist by exactly that much. Rotating (0,1,0) about +X
			// in quarter turns gives up, across, down, across the other way -- the four a
			// hand can plausibly sit at when a rig's idea of "up" disagrees with a
			// controller's.
			//
			// No engine call and no new field for this: it is the same reasoning as the
			// finger and lean signs. The axis comes off the geometry, the convention comes
			// off the owner's eyes, and a quarter turn found on screen in one keypress
			// beats a number guessed at from out here.
			Vector3 twistT;
			int qt = ((cvi("rs_body_wrist_turn", 0) % 360) + 360) % 360;
			if      (qt ==  90) twistT = (0,  0,  1);
			else if (qt == 180) twistT = (0, -1,  0);
			else if (qt == 270) twistT = (0,  0, -1);
			else                twistT = (0,  1,  0);
			a.SetModelReachTarget(i, hd, (0, 0, 0), (1, 0, 0), twistT, 'rs_arm_sock_whole');

			// AND THE WRIST ACTUALLY TURNS. The solve places the end joint and never
			// orients it -- align swivels the elbow, twist rolls the forearm, and neither
			// is the hand -- so until this existed the hand arrived at the controller and
			// then ignored entirely how the controller was HELD. Engine call added for
			// this; the frames it matches are the two declared just above and the rig's own
			// twistRef passed to SetModelReachFrame.
			// THE FOREARM TAKES MOST OF THE ROLL. Rendered off this rig: a 180 degree
			// wrist roll on the hand bone alone collapses the wrist to a POINT -- the
			// candy-wrapper pinch, because bip_lowerArm parents bip_hand directly with
			// no twist bone between them. Split with the forearm, the same roll is
			// clean. That is the "ugly as fuck" and it was never about the angle.
			a.SetModelReachEndAim(i, 1, 1.0, clamp(cvf("rs_body_wrist_roll_share", 0.6), 0.0, 1.0));
		}

		// ---- and the legs, on chains 2 and 3 -------------------------------
		// Set up beside the arms so the whole body's rig is established in one
		// place; the walk itself runs from WorldTick. Torn down when switched off
		// so the chains do not sit holding joints nothing is driving.
		bool legsOn = cvb("rs_legs_enabled", true);
		bool valveStyle = (cvs("rs_body_whole_style", "marine") == "praetor");
		if (legsOn)
		{
			if (!legs) legs = new("RS_VRLegs");
			legs.Setup(pawn, a, valveStyle);
		}
		else if (legs)
		{
			legs.Clear(pawn, a);
		}

		// YOUR OWN HEAD AND HELMET, OFF BY DEFAULT, BECAUSE YOU ARE INSIDE THEM.
		//
		// Surfaces 11..14 are the head group -- hair, face, teeth, eyes. Hidden by
		// pointing their surface skins at a transparent texture rather than by
		// dropping the mesh, so the model stays one file and everyone ELSE still
		// sees a marine with a head.
		//
		// Four calls rather than a local array: `string skins[4]` is C, not ZScript.
		// APPLIED ON THE FIRST TIC AND ON EVERY NEW BODY ACTOR, not only on a CHANGE.
		//
		// This once tested a remembered bool against the cvar with both starting
		// false, so the swap never fired and the head was never actually hidden -- it
		// only LOOKED correct, because the default and the remembered value agreed.
		// The owner spawned inside the marine's face. The state starts at -1 so the
		// first tic always applies, and a new actor (a level change) comes back with
		// its MODELDEF skins, so the actor is tracked too and not just the value --
		// and that actor test is what guarantees the first application.
		// THE COLOUR, on change only -- a dozen surfaces is not a per-tic cost worth
		// paying when armour changes a handful of times a level.
		string want = bodyColour(pawn);
		string bstyle = cvs("rs_body_whole_style", "marine");
		if (want != paintedAs || a != paintedOn)
		{
			paintedAs = want; paintedOn = a;
			paintBody(a, bstyle, want);
			paintHands(bstyle, want);
		}

		// THREE SWITCHES, NOT ONE. The visor, the helmet shell and your own face are
		// three different things to be inside, and one lumped switch meant asking for
		// either took both. 8 is the visor, 9 and 10 the shell and its interior,
		// 11..14 hair, face, teeth, eyes.
		bool head  = cvb("rs_body_show_face", true);
		bool helm  = cvb("rs_body_show_helmet", true);
		bool visor = cvb("rs_body_show_visor", true);
		int hstate = (head ? 1 : 0) | (helm ? 2 : 0) | (visor ? 4 : 0)
		           | (cvs("rs_body_whole_style", "marine") == "praetor" ? 8 : 0);
		if (hstate != wholeHeadState || a != wholeHeadOn)
		{
			wholeHeadState = hstate;
			wholeHeadOn    = a;
			// THE WORN BODY NEVER SHOWS ITS OWN HEAD ANY MORE. It is the head COPY
			// that draws it (syncHeadCopy), because only a separate actor can be
			// hidden from one viewpoint and drawn from the others. Leaving these
			// switched on by cvar as well would draw the head TWICE -- once in your
			// eyes and once in the mirror -- which is precisely the bug the copy
			// exists to avoid.
			//
			// Still switched here rather than done once at spawn: a body actor is
			// replaced on every style and colour change, and a fresh one arrives with
			// its MODELDEF skins, head included.
			//
			// EACH BODY HAS ITS OWN SURFACE NUMBERS. Measured off the meshes: the
			// Praetor's helmet is 3 and 4 and his visor 12 (surface 10 is named
			// "glass" but sits at chest height and belongs to the torso); the
			// marine's head runs 8..14.
			if (cvs("rs_body_whole_style", "marine") == "praetor")
			{
				headHide(a, 3); headHide(a, 4); headHide(a, 12);
			}
			else
			{
				headHide(a,  8); headHide(a,  9); headHide(a, 10); headHide(a, 11);
				headHide(a, 12); headHide(a, 13); headHide(a, 14);
			}
		}
	}

	// Hidden, not destroyed -- and put back exactly as it was when the whole body
	// is switched off. Alpha and RenderStyle only: nothing else about the hand is
	// touched, so it keeps holding whatever it was holding.
	private void hideReachedHand(Actor hd, bool hide)
	{
		if (!hd) return;
		if (hide)
		{
			hd.A_SetRenderStyle(0.0, STYLE_None);
		}
		else
		{
			hd.A_SetRenderStyle(1.0, STYLE_Normal);
		}
	}

	// THE HANDS COME BACK when the whole body is switched off mid-play. Without
	// this, turning it off leaves you with the part rig and two invisible hands.
	private void showReachedHands()
	{
		for (int i = 0; i < 2; ++i)
		{
			hideReachedHand(drawnHand((i == 0) ? RSLOT_ARM_R : RSLOT_ARM_L), false);
		}
	}


	// ---- what colour the body is ------------------------------------------
	//
	// GREEN by default, BLUE with armour on, and a RED copy breathing over the top
	// when you are nearly dead. The owner's rule, and the same one the part rig ran:
	// the colour is DECIDED, never chosen from a menu, because it is a readout.
	//
	// Applied by swapping the armour surfaces' skins rather than by swapping the
	// body class, so nothing respawns and nothing loses its interpolation mid-step.
	private string bodyColour(PlayerPawn pawn)
	{
		if (!pawn) return "green";
		int armour = pawn.CountInv("BasicArmor");
		return (armour > 0 && cvb("rs_body_armor_color", true)) ? "blue" : "green";
	}

	// The armour surfaces of each body, and the texture each one wears. Everything
	// not named here -- glass, visor, the head group -- keeps what MODELDEF gave it.
	private void paintBody(Actor a, string style, string colour)
	{
		string suffix = "_" .. colour .. ".png";
		if (style == "praetor")
		{
			skinIf(a,  0, "doomslayer_praetor_1003" .. suffix);
			skinIf(a,  1, "doomslayer_praetor_1015" .. suffix);
			skinIf(a,  2, "doomslayer_praetor_1014" .. suffix);
			skinIf(a,  5, "doomslayer_praetor_1006" .. suffix);
			skinIf(a,  6, "doomslayer_praetor_1007" .. suffix);
			skinIf(a,  7, "doomslayer_praetor_1005" .. suffix);
			skinIf(a,  8, "doomslayer_praetor_1003" .. suffix);
			skinIf(a,  9, "doomslayer_praetor_1002" .. suffix);
			skinIf(a, 11, "doomslayer_praetor_1004" .. suffix);
		}
		else
		{
			skinIf(a, 1, "doomslayer_torso_set3_skin" .. suffix);
			skinIf(a, 2, "doomslayer_shoulders_set3_skin" .. suffix);
			skinIf(a, 3, "doomslayer_arm_right_set3_skin" .. suffix);
			skinIf(a, 4, "doomslayer_arm_left_set3_skin" .. suffix);
			skinIf(a, 5, "doomslayer_legs_set3_skin" .. suffix);
			skinIf(a, 6, "doomslayer_legs_set3_skin" .. suffix);
		}
	}

	// His hands wear the suit too, or you get green armour and bronze gauntlets.
	private void paintHands(string style, string colour)
	{
		string suffix = "_" .. colour .. ".png";
		if (style == "praetor")
		{
			if (parts[RSLOT_HAND_MAIN]) { skinIf(parts[RSLOT_HAND_MAIN], 0, "doomslayer_praetor_1013" .. suffix);
			                              skinIf(parts[RSLOT_HAND_MAIN], 1, "doomslayer_praetor_1012" .. suffix); }
			if (parts[RSLOT_HAND_OFF])    skinIf(parts[RSLOT_HAND_OFF],  0, "doomslayer_praetor_1013" .. suffix);
		}
		else
		{
			if (parts[RSLOT_HAND_MAIN]) skinIf(parts[RSLOT_HAND_MAIN], 0, "doomslayer_arm_right_set3_skin" .. suffix);
			if (parts[RSLOT_HAND_OFF])  skinIf(parts[RSLOT_HAND_OFF],  0, "doomslayer_arm_left_set3_skin" .. suffix);
		}
	}

	private void skinIf(Actor a, int surface, string skin)
	{
		if (!a) return;
		string dir = (cvs("rs_body_whole_style", "marine") == "praetor") ? "models/praetor" : "models/marine";
		a.A_ChangeModel("", 0, "", "", surface, dir, skin, CMDL_USESURFACESKIN, 0, 0, "", "");
	}

	private string paintedAs;
	private Actor  paintedOn;

	// THE PATH IS A PARAMETER NOW, AND IT HAD TO BECOME ONE.
	//
	// This hardcoded "models/marine" while the Praetor's calls handed it PRAETOR skin
	// names -- so every one of those asked models/marine for a file that only exists
	// under models/praetor. Only the invisible.png half ever resolved, because that one
	// really does live under marine. So turning his helmet OFF worked and turning it ON
	// quietly did not, which is the worst shape a bug can take: half of it works, so
	// nobody suspects the mechanism.
	private void headSkinAt(Actor a, int surface, string path, string skin)
	{
		a.A_ChangeModel("", 0, "", "", surface, path, skin,
		                CMDL_USESURFACESKIN, 0, 0, "", "");
	}

	// The marine's, by far the commonest caller.
	private void headSkin(Actor a, int surface, string skin)
	{
		headSkinAt(a, surface, "models/marine", skin);
	}

	// INVISIBLE LIVES UNDER MARINE whoever is asking. One 1x1 transparent png is enough
	// for the package and there is no reason to ship a second copy per body.
	private void headHide(Actor a, int surface)
	{
		headSkinAt(a, surface, "models/marine", "invisible.png");
	}

	// No initialiser: ZScript does not allow one on a member. It does not need one
	// either -- wholeHeadOn starts null and the drawn actor never is, so the first
	// tic always applies regardless of what this happens to hold.
	private int wholeHeadState;
	private Actor wholeHeadOn;
	private bool wholeWas;

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
			tuning = right ? 'rs_armik_rt' : 'rs_armik_lf';
			outward  = right ? (-1, 0, 0) : (1, 0, 0);
			twistRef = right ? (0.1929, 0.6177, -0.7624) : (-0.1929, 0.6177, -0.7624);
		}
		else if (right)
		{
			up = 'arm_upper_rt'; mid = 'arm_lower_rt'; wrist = 'arm_hand_rt'; tuning = 'rs_armik_rt';
			outward = (-1, 0, 0);
			twistRef = (0.4117, 0.4096, -0.8141);
		}
		else
		{
			up = 'arm_upper_lf'; mid = 'arm_lower_lf'; wrist = 'arm_hand_lf'; tuning = 'rs_armik_lf';
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
		if (marine)
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
			// The LEFT arm is cut closer (0.45 map units behind the wrist, untucked) so its whole gold bracer
			// stays as a cuff over the wrist (owner, 2026-09-15: the left wrist "looks kinda rough" -- the 1.29
			// cut went through the bracer). Its sockets are that cut's: anatomical (0.80, -1.35), engine unchanged.
			else       p = anat ? (0.80, 1.47, -1.35) : (0.96, 1.47, 1.68);
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

	// ---- your own head, drawn for everyone but you ------------------------
	//
	// THE HEAD HAS TO EXIST AND YOU MUST NOT SEE IT. You are inside it, so a face
	// drawn at your eyes is a face you are looking out through -- but the mirror
	// wants it, and so does anyone else in co-op. Those are different VIEWPOINTS,
	// and a skin swap on the worn body is global, so it cannot answer a per-view
	// question at all.
	//
	// MF8_MASTERNOSEE is exactly the engine's answer and it ALREADY EXISTED: "don't
	// show object in first person if their master is the current camera" (actor.h).
	// Mastered to the pawn, this copy is skipped when the view belongs to the pawn
	// and drawn from every other viewpoint. No engine change -- worth checking for
	// before proposing one.
	//
	// Same mesh, complementary surfaces: the worn body keeps 8..14 invisible as it
	// always has, and this copy hides 0..7 and shows the head. The near-death breath
	// already draws a second copy of this model, so the cost is known and the shape
	// is proven.
	private Actor  headCopy;
	private string headCopyClass;

	private void syncHeadCopy(PlayerPawn pawn)
	{
		Actor b = parts[RSLOT_BODY];
		bool praetor = (cvs("rs_body_whole_style", "marine") == "praetor");
		bool head  = cvb("rs_body_show_face",   true);
		bool helm  = cvb("rs_body_show_helmet", true);
		bool visor = cvb("rs_body_show_visor",  true);

		// THE PRAETOR HAS NO FACE MESH -- he is always helmeted -- so "draw your own
		// face" has nothing to do on him and only helmet and visor decide whether he
		// needs a copy at all.
		bool want = praetor ? (helm || visor) : (head || helm || visor);
		string cls = praetor ? "RS_PartBodyPraetorHead" : "RS_PartBodyMarineHead";
		if (!b || !want)
		{
			if (headCopy) { headCopy.Destroy(); headCopy = null; }
			headCopyClass = "";
			return;
		}
		// Swapping body mid-play swaps which copy is right, so the class is tracked and
		// the old one thrown away -- exactly as the breath does when the torso changes.
		if (headCopy && headCopyClass != cls) { headCopy.Destroy(); headCopy = null; }

		if (!headCopy)
		{
			headCopyClass = cls;
			headCopy = Actor.Spawn(cls, pawn.Pos, NO_REPLACE);
			if (!headCopy) return;
			headCopy.A_ChangeModel("", 0, "", "", 0, "", "", 0, 0, 0, "", "");
			// THE TWO LINES THAT MAKE IT WORK. The master says whose view to hide
			// from; the flag says to do it. Without the master the flag does nothing
			// at all and the head is simply drawn in your eyes.
			headCopy.master = pawn;
			headCopy.bMASTERNOSEE = true;
			placeActor(pawn, headCopy, RSLOT_BODY);
			headCopy.ClearInterpolation();
		}
		if (praetor)
		{
			// Measured, not guessed: 3 and 4 are praetor_helmet_* at the top of the
			// mesh, 12 is praetor_visor_*. Everything else is body and is not in this
			// MODELDEF at all, so it draws nothing without being told to.
			if (helm)  { headSkinAt(headCopy, 3, "models/praetor", "doomslayer_praetor_1001.png");
			             headSkinAt(headCopy, 4, "models/praetor", "doomslayer_praetor_1011.png"); }
			else       { headHide(headCopy, 3); headHide(headCopy, 4); }
			if (visor) headSkinAt(headCopy, 12, "models/praetor", "doomslayer_praetor_1001_visor_solid.png");
			else       headHide(headCopy, 12);
		}
		else
		{
			if (visor) headSkin(headCopy, 8, "doomslayer_helmet_visor_set3_hq_skin.png"); else headHide(headCopy, 8);
			if (helm)  { headSkin(headCopy,  9, "doomslayer_helmet_set3_skin.png");
			             headSkin(headCopy, 10, "doomslayer_helmet_interior_set3_skin.png"); }
			else       { headHide(headCopy, 9); headHide(headCopy, 10); }
			if (head)  { headSkin(headCopy, 11, "doomslayer_hair.png");
			             headSkin(headCopy, 12, "doomslayer_head.png");
			             headSkin(headCopy, 13, "doomslayer_teeth.png");
			             headSkin(headCopy, 14, "doomslayer_eyes.png"); }
			else       { headHide(headCopy, 11); headHide(headCopy, 12);
			             headHide(headCopy, 13); headHide(headCopy, 14); }
		}
		placeActor(pawn, headCopy, RSLOT_BODY);
	}

	// THE PAWN'S OWN SPRITE IS NOT WANTED WHILE YOU ARE WEARING A BODY.
	//
	// It is the stock marine, drawn at the pawn's feet, and it interferes with the
	// body that has replaced it -- most visibly in the mirror, where the viewpoint is
	// the mirror camera rather than your eyes, so the engine's own "do not draw the
	// thing you are looking out of" rule does not apply and the sprite comes back.
	//
	// Tracked rather than set every tic: a render style write per tic on the pawn is
	// pointless churn, and remembering the state is what lets it be put back exactly
	// when the whole body comes off.
	//
	// NETPLAY, STATED PLAINLY: this writes the pawn's render style, and this rig runs
	// for players[consoleplayer] only -- so on each machine each player hides their
	// OWN pawn, and in co-op everyone would vanish for everyone. That is survivable
	// only because the body rig is already consoleplayer-only and no other player has
	// a body at all yet. When the body becomes per-player this must become a
	// non-replicated, render-only hide, not a playsim write. Flagged, not forgotten.
	private bool pawnHidden;

	private void syncPawnSprite(PlayerPawn pawn)
	{
		if (!pawn) return;
		bool want = (parts[RSLOT_BODY] != null) && cvb("rs_body_hide_pawn", true);
		if (want == pawnHidden) return;
		pawnHidden = want;
		if (want) pawn.A_SetRenderStyle(0.0, STYLE_None);
		else      pawn.A_SetRenderStyle(1.0, STYLE_Normal);
	}

	// ---- the mirror -------------------------------------------------------
	//
	// See the header of body_mirror.zs for why this is a panel and not a chase
	// camera. Short version: a chase camera in VR orbits when you turn your head,
	// and that is what makes people ill. A mirror moves nothing.
	//
	// Put up in front of you on a keypress, taken away on the next one.
	private Actor mirProp, mirCam;

	private void toggleMirror(PlayerPawn pawn)
	{
		if (mirProp || mirCam)
		{
			if (mirProp) mirProp.Destroy();
			if (mirCam)  mirCam.Destroy();
			mirProp = null; mirCam = null;
			Console.Printf("\c[Gold]RS_VRBody: mirror away.");
			return;
		}
		if (!pawn) return;

		double dist = clamp(cvf("rs_body_mirror_dist", 96.0), 32.0, 400.0);
		double yaw  = pawn.angle;
		Vector3 at  = (pawn.pos.X + cos(yaw) * dist,
		               pawn.pos.Y + sin(yaw) * dist,
		               pawn.pos.Z + cvf("rs_body_mirror_up", 34.0));

		// THE CAMERA STANDS OFF THE PANEL, and this is not a detail.
		//
		// Both were spawned at the same point, so the camera sat INSIDE its own quad --
		// and that quad is deliberately double sided, so the camera was staring at the
		// back of the very surface it paints. The panel and the scene behind it then win
		// the depth test in alternate frames, which is exactly "flickers like super fast,
		// grey texture and back to mirror". A few units toward the player puts the
		// camera clear of its own geometry.
		double back = clamp(cvf("rs_body_mirror_standoff", 8.0), 2.0, 48.0);
		Vector3 camAt = (at.X - cos(yaw) * back, at.Y - sin(yaw) * back, at.Z);

		mirProp = Actor.Spawn("RS_VRMirror", at);
		mirCam  = Actor.Spawn("RS_VRMirrorCam", camAt);
		if (!mirProp || !mirCam) { Console.Printf("\c[Red]RS_VRBody: mirror could not spawn."); return; }

		// The panel faces back down the line it was placed along, so it is square
		// to you the moment it appears.
		mirProp.angle = yaw + 180;
		mirCam.angle  = yaw + 180;
		TexMan.SetCameraToTexture(mirCam, "RSMIRROR", clamp(cvf("rs_body_mirror_fov", 70.0), 30.0, 140.0));
		Console.Printf("\c[Gold]RS_VRBody: mirror up. Press again to send it away.");
	}

	// The camera TRACKS you rather than staring straight ahead, so you stay in
	// frame while you walk about, crouch and lean -- which is the entire point of
	// having it. A true reflection would lose you the moment you stepped aside.
	private void tickMirror(PlayerPawn pawn)
	{
		if (!mirCam || !pawn) return;
		Vector3 head = pawn.HmdPos;
		if (head == (0, 0, 0)) head = (pawn.pos.X, pawn.pos.Y, pawn.pos.Z + pawn.Height * 0.8);
		Vector3 d = (head.X - mirCam.pos.X, head.Y - mirCam.pos.Y, head.Z - mirCam.pos.Z);
		double flat = sqrt(d.X * d.X + d.Y * d.Y);
		if (flat < 1.0) return;
		mirCam.angle = atan2(d.Y, d.X);
		mirCam.pitch = -atan2(d.Z, flat);
	}

	// ---- leaning: the spine actually bends --------------------------------
	//
	// THE BODY ALREADY MOVES WHEN YOU LEAN and that is not the same thing. Every seat
	// is measured off HmdPos, so ducking or leaning slides the whole marine along with
	// your head -- rigid, like a statue on rails. What is missing is the BEND: a person
	// leaning pivots at the waist, and their feet stay where they were.
	//
	// So the lean is the gap between where your head IS and where it would be if you
	// were standing straight over your own feet. The pawn is that plumb line: it does
	// not move when you lean in room scale, your head does. Resolve the difference into
	// the body's own axes and it is forward/back and side lean directly.
	//
	// THE AXES ARE MEASURED, exactly as the fingers' hinge was, and this rig is as clean
	// as it gets -- bip_spine_0, _1 and _2 all report local Z along the spine at +1.00
	// and local Y across the shoulders at +1.00, to two decimals, with X the remainder:
	//
	//     local Y  the shoulder axis  -> leaning FORWARD and BACK turns about it
	//     local X  forward            -> leaning SIDEWAYS turns about it
	//     local Z  up the spine       -> twist, left alone here
	//
	// Spread over the three spine bones rather than hinging one, because a spine bends
	// as a curve and a single joint bending 30 degrees is a person snapping in half.
	// Both signs are sliders for the same reason the fingers' was: the axis is geometry
	// and I can measure it, the direction is a convention I cannot see from out here.

	private void tickLean(PlayerPawn pawn)
	{
		Actor b = parts[RSLOT_BODY];
		if (!b || !cvb("rs_body_lean", true)) return;
		bool praetor = (cvs("rs_body_whole_style", "marine") == "praetor");

		// Your head against your own plumb line, in the body's axes.
		double dx = pawn.HmdPos.X - pawn.pos.X;
		double dy = pawn.HmdPos.Y - pawn.pos.Y;
		double fx = cos(mBodyYaw), fy = sin(mBodyYaw);
		double rx = sin(mBodyYaw), ry = -cos(mBodyYaw);
		double fwd  = dx * fx + dy * fy;
		double side = dx * rx + dy * ry;

		// Map units of head travel that count as a full lean, then degrees per bone.
		double span = MAX(1.0, cvf("rs_body_lean_span", 14.0));
		double maxD = cvf("rs_body_lean_max", 26.0);
		double sgnF = cvf("rs_body_lean_sign_fwd", 1.0);
		double sgnS = cvf("rs_body_lean_sign_side", 1.0);
		double dur  = cvf("rs_body_lean_ease", 3.0);

		// SPREAD OVER HOWEVER MANY SPINE BONES THIS RIG HAS -- four on the Praetor, three
		// on the marine. Dividing by the count keeps the TOTAL bend the same on both, so
		// the slider means one thing regardless of who is worn.
		int    bones = praetor ? 4 : 3;
		double leanF = clamp(fwd  / span, -1.0, 1.0) * maxD * sgnF;
		double leanS = clamp(side / span, -1.0, 1.0) * maxD * sgnS;

		// WHAT YOU ARE CARRYING, ADDED HERE rather than written separately. The lean and
		// the load are the same three bones turning about the same axes, so they are
		// summed by one writer -- the same rule that keeps the gun's sag inside the
		// recoil expression instead of fighting it every tic.
		//
		// A heavy gun held out in front pulls you FORWARD, and a person carrying it
		// leans BACK against that to stay over their feet. So the load is subtracted
		// from the forward lean, not added to it. Held one-handed it also pulls you
		// toward that side, so the imbalance between the hands rolls the spine.
		if (cvb("rs_body_weight_lean", true))
		{
			weightServiceFind();
			double rt = heldLbs(pawn, 0);            // main hand
			double lf = heldLbs(pawn, 1);            // off hand
			double wspan = MAX(1.0, cvf("rs_body_weight_span", 18.0));
			double wmax  = cvf("rs_body_weight_max", 9.0);
			leanF -= clamp((rt + lf) / wspan, 0.0, 1.0) * wmax * sgnF;
			leanS += clamp((rt - lf) / wspan, -1.0, 1.0) * wmax * 0.5 * sgnS;
		}

		double pitchDeg = leanF / bones;
		double rollDeg  = leanS / bones;

		// THE AXES ARE THIS RIG'S, MEASURED, and the two rigs disagree -- which is the
		// whole reason this is a table and not a constant. Against the shoulder line the
		// marine's spine bones read local Y at +1.00; the Praetor's read local Z at
		// +1.00. So forward/back turns about Y on one and Z on the other, and the
		// sideways axis is whichever of the remaining two is forward.
		if (praetor)
		{
			Vector3 axF = (0, 0, 1), axS = (0, 1, 0);
			leanBone(b, 'ValveBiped.Bip01_Spine',  axF, axS, pitchDeg, rollDeg, dur);
			leanBone(b, 'ValveBiped.Bip01_Spine1', axF, axS, pitchDeg, rollDeg, dur);
			leanBone(b, 'ValveBiped.Bip01_Spine2', axF, axS, pitchDeg, rollDeg, dur);
			leanBone(b, 'ValveBiped.Bip01_Spine4', axF, axS, pitchDeg, rollDeg, dur);
		}
		else
		{
			Vector3 axF = (0, 1, 0), axS = (1, 0, 0);
			leanBone(b, 'bip_spine_0', axF, axS, pitchDeg, rollDeg, dur);
			leanBone(b, 'bip_spine_1', axF, axS, pitchDeg, rollDeg, dur);
			leanBone(b, 'bip_spine_2', axF, axS, pitchDeg, rollDeg, dur);
		}
	}

	// One spine bone: forward/back about the shoulder axis, sideways about forward.
	// Silent on a bone this rig does not carry, for the same reason curlFinger is.
	private void leanBone(Actor b, Name j, Vector3 axFwd, Vector3 axSide, double pitchDeg, double rollDeg, double dur)
	{
		if (!b || b.GetBoneIndex(j) < 0) return;
		Quat q = Quat.AxisAngle(axFwd, pitchDeg) * Quat.AxisAngle(axSide, rollDeg);
		b.SetNamedBoneRotation(j, q, SB_ADD, dur);
	}

	// ---- the body's own fingers -------------------------------------------
	//
	// EACH HAND HAS 22 JOINTS AND NOTHING HAS EVER POSED THEM. RS_WorldHands poses the
	// GLOVE's fingers out of a 1705-frame pose library baked into hand_left_poses.iqm,
	// and a whole body HIDES that glove -- so the posing went with it and the body's
	// own fingers have been rigid since the day it shipped. The rig was never the
	// problem: thumb, index, middle, ring and pinky, three segments each, both hands.
	//
	// THE GLOVE'S POSES CANNOT BE COPIED, for two separate reasons. They are animation
	// FRAMES, and this body has one frame and zero frame channels -- no animation at
	// all to hold them in. And ZScript cannot read another model's animated joint
	// rotations anyway; the bone getters answer the bind pose plus explicit offsets,
	// not what an animation is doing. So the fingers are DRIVEN, not copied.
	//
	// THE HINGE IS MEASURED, NOT GUESSED. Every finger bone on this rig runs down its
	// own local -Z -- all five fingers, both segments, to three decimals -- and the
	// knuckle spread from index to pinky lands on local X at -0.94 to -0.995 with Y at
	// essentially zero. So local X is the hinge, and it is the hinge for the whole hand.
	// Quat.AxisAngle states that axis outright rather than going through Euler angles,
	// so there is no yaw/pitch/roll convention to be wrong about.
	//
	// WHICH WAY IT BENDS IS A SLIDER, DELIBERATELY. The axis is geometry and I can
	// measure it; the SIGN is a convention I cannot see from here, and fingers that
	// bend backwards are worse than fingers that do not bend at all. rs_body_finger_sign
	// flips the whole hand in one move, in the headset, without a rebuild.
	//
	// Safe against the arm solve: the chain owns the upper arm, forearm and WRIST only.
	// Fingers hang under the wrist, so nothing here fights the solver -- and when the
	// wrist turns, the fingers ride it, which is what a wrist turning means.
	const FING_A0 = 65.0;	// knuckle, degrees at full curl
	const FING_A1 = 75.0;	// middle -- a real hand closes most here, so these differ
	const FING_A2 = 55.0;	// tip

	private Service gripSv;
	private int     gripSvWait;

	// The SAME arbiter the holsters ask, as a READER. Not a second grip system: it
	// owns the answer, this only wants to know it. Absent (RS_WorldHands not loaded)
	// simply means the hands never read as holding, and the fingers rest.
	// ---- what you are carrying, and what it does to your back -------------
	//
	// THE GUN SAGS IN THE HAND (RS_VR_Reload's rig.zs, one writer, about the grip) and
	// THE BODY TAKES THE LOAD. Those are the two halves and they are deliberately in
	// different packages: the gun's turn belongs beside its recoil, and the spine
	// belongs here beside the lean. Neither may move a hand -- the arm chains run
	// absolute stretch, so the wrist lands on the controller no matter what, because
	// the player's real hand is ground truth.
	//
	// Reached BY STRING, never by class name. A hard reference to a class in another
	// pk3 broke the whole game three separate times across three folder layouts.
	private Service wgtSv;
	private int     wgtSvWait;

	private void weightServiceFind()
	{
		if (wgtSv) return;
		if (wgtSvWait > 0) { wgtSvWait--; return; }
		ServiceIterator it = ServiceIterator.Find("RS_WeaponWeightService");
		Service sv;
		while (sv = it.Next())
		{
			if (sv.GetInt("weapon.weight.hello", "", 0, 0, null) == 1) { wgtSv = sv; break; }
		}
		if (!wgtSv) wgtSvWait = 350;
	}

	// Pounds in that hand, or 0 for "do not apply weight".
	//
	// ASKS `has` FIRST, AND THAT IS THE WHOLE TRAP. 80 of 155 guns state no weight at
	// all -- plasma, the BFG, the Unmaker, most of HacX -- because inventing eighty
	// numbers to fill a column would have been worse than leaving it empty. The double
	// answers 0.0 for those, and 0.0 read as "light" would make every energy weapon
	// stand you bolt upright while the ballistic ones bend you over.
	private double heldLbs(PlayerPawn pawn, int hand)
	{
		if (!wgtSv || !pawn) return 0;
		if (wgtSv.GetInt("weapon.weight.has", "", hand, 0, pawn) != 1) return 0;
		double lbs = wgtSv.GetDouble("weapon.weight.lbs", "", hand, 0, pawn);
		return lbs > 0 ? lbs : 0;
	}

	private void gripServiceFind()
	{
		if (gripSv) return;
		if (gripSvWait > 0) { gripSvWait--; return; }
		ServiceIterator it = ServiceIterator.Find("RS_GripArbiter");
		Service sv;
		while (sv = it.Next())
		{
			if (sv.GetInt("grip.hello", "", 0, 0, null, 'RS_VRBody') == 1) { gripSv = sv; break; }
		}
		if (!gripSv) gripSvWait = 350;
	}

	// IS THIS HAND CLOSED AROUND SOMETHING?
	//
	// ASKS THE POSE SERVICE, NOT THE GRIP ARBITER, and that is the whole fix for "hands
	// occasionally grip". `grip.held` answers a question that reads almost the same and
	// is not it: "some mod has a CLAIM on this hand" -- and a claim is a LEASE that dies
	// after 70 tics unless its owner keeps renewing. Holding a gun does not necessarily
	// renew anything, so the fingers opened and closed as the lease lapsed and was
	// retaken. Intermittent, impossible to reproduce on demand, and exactly what he saw.
	//
	// pose.holding asks RS_Held, which actually knows. The arbiter stays as a FALLBACK
	// for an RS_WorldHands older than that key: a stale claim is a worse answer than a
	// fresh one, and a far better answer than none.
	private Service poseSv;
	private int     poseSvWait;

	private void poseServiceFind()
	{
		if (poseSv) return;
		if (poseSvWait > 0) { poseSvWait--; return; }
		ServiceIterator it = ServiceIterator.Find("RS_HandPoseService");
		Service sv;
		while (sv = it.Next())
		{
			if (sv.GetInt("pose.hello", "", 0, 0, null, 'RS_VRBody') == 1) { poseSv = sv; break; }
		}
		if (!poseSv) poseSvWait = 350;
	}

	private bool handHolds(PlayerPawn pawn, int hand)
	{
		poseServiceFind();
		if (poseSv)
		{
			int h = poseSv.GetInt("pose.holding", "", hand, 0, pawn, 'RS_VRBody');
			if (h >= 0) return h == 1;   // -1 is "cannot say" -- fall through to the claim
		}
		if (!gripSv) return false;
		return gripSv.GetInt("grip.held", "", hand, 0, pawn, 'RS_VRBody') == 1;
	}

	// One finger, three segments, curled about the measured hinge. The axis is a
	// parameter because the two rigs DO NOT SHARE ONE: the marine hinges on local X,
	// the Praetor on local Z. Each measured off its own skeleton, neither assumed from
	// the other -- they are different rigs from different games and the only reason to
	// expect them to agree would be hope.
	//
	// SILENT ON A BONE THAT IS NOT THERE. A caller can legitimately hand this a rig
	// without the joint: an RS glove worn on a Praetor body is exactly that, and so is
	// any body variant with a simpler hand. Checking beats finding out at runtime.
	private void curlFinger(Actor b, Vector3 axis, Name j0, Name j1, Name j2, double curl, double sign, double dur)
	{
		if (!b || b.GetBoneIndex(j0) < 0) return;
		b.SetNamedBoneRotation(j0, Quat.AxisAngle(axis, sign * FING_A0 * curl), SB_ADD, dur);
		b.SetNamedBoneRotation(j1, Quat.AxisAngle(axis, sign * FING_A1 * curl), SB_ADD, dur);
		b.SetNamedBoneRotation(j2, Quat.AxisAngle(axis, sign * FING_A2 * curl), SB_ADD, dur);
	}

	// THE PRAETOR'S FIVE, ON THE ACTOR THAT ACTUALLY DRAWS THAT HAND.
	//
	// His fingers are not on his body. praetor_body.iqm carries the entire 83-joint
	// ValveBiped skeleton -- both hands and all fifteen finger joints a side -- and NO
	// hand geometry at all. The meshes are separate actors riding that same skeleton:
	// praetor_hand_rt.iqm on the main hand, _lf on the off hand (MODELDEF). So the
	// bones have to be turned THERE or nothing is seen to move, which is also why the
	// body-actor path below would have posed thin air for him.
	//
	// ValveBiped numbers fingers 0 thumb, 1 index, 2 middle, 3 ring, 4 pinky, each with
	// two more joints suffixed 1 and 2.
	private void curlPraetorHand(Actor h, bool rightMesh, double curl, double sign, double dur, double thumb)
	{
		Vector3 ax = (0, 0, 1);		// measured: knuckle spread lands on local Z, +0.83..+0.99
		if (rightMesh)
		{
			curlFinger(h, ax, 'ValveBiped.Bip01_R_Finger1', 'ValveBiped.Bip01_R_Finger11', 'ValveBiped.Bip01_R_Finger12', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_R_Finger2', 'ValveBiped.Bip01_R_Finger21', 'ValveBiped.Bip01_R_Finger22', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_R_Finger3', 'ValveBiped.Bip01_R_Finger31', 'ValveBiped.Bip01_R_Finger32', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_R_Finger4', 'ValveBiped.Bip01_R_Finger41', 'ValveBiped.Bip01_R_Finger42', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_R_Finger0', 'ValveBiped.Bip01_R_Finger01', 'ValveBiped.Bip01_R_Finger02', curl * thumb, sign, dur);
		}
		else
		{
			curlFinger(h, ax, 'ValveBiped.Bip01_L_Finger1', 'ValveBiped.Bip01_L_Finger11', 'ValveBiped.Bip01_L_Finger12', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_L_Finger2', 'ValveBiped.Bip01_L_Finger21', 'ValveBiped.Bip01_L_Finger22', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_L_Finger3', 'ValveBiped.Bip01_L_Finger31', 'ValveBiped.Bip01_L_Finger32', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_L_Finger4', 'ValveBiped.Bip01_L_Finger41', 'ValveBiped.Bip01_L_Finger42', curl, sign, dur);
			curlFinger(h, ax, 'ValveBiped.Bip01_L_Finger0', 'ValveBiped.Bip01_L_Finger01', 'ValveBiped.Bip01_L_Finger02', curl * thumb, sign, dur);
		}
	}

	private void tickFingers(PlayerPawn pawn)
	{
		Actor b = parts[RSLOT_BODY];
		if (!b || !cvb("rs_body_fingers", true)) return;
		bool praetor = (cvs("rs_body_whole_style", "marine") == "praetor");

		gripServiceFind();

		double sign = cvf("rs_body_finger_sign", -1.0);
		double dur  = cvf("rs_body_finger_ease", 3.0);
		double grip = cvf("rs_body_finger_curl", 1.0);
		double rest = cvf("rs_body_finger_rest", 0.15);
		double thmb = cvf("rs_body_finger_thumb", 0.6);

		// THE PRAETOR IS DRIVEN BY HAND SLOT, THE MARINE BY ARM SLOT, and that is not an
		// inconsistency. His hand MESHES are fixed: main draws the right hand, off draws
		// the left (MODELDEF), so which mesh gets which curl follows the controller that
		// mesh rides, never the arm pairing. The marine's fingers are bones on one body,
		// so his follow the arm that owns them.
		if (praetor)
		{
			for (int h = 0; h < 2; ++h)
			{
				Actor hp = parts[h == 0 ? RSLOT_HAND_MAIN : RSLOT_HAND_OFF];
				if (!hp) continue;
				curlPraetorHand(hp, h == 0, handHolds(pawn, h) ? grip : rest, sign, dur, thmb);
			}
			return;
		}

		for (int i = 0; i < 2; ++i)
		{
			bool right = (i == 0);
			// The SAME pairing the arms use, so a hand never closes on the controller
			// its own arm is not reaching. armHand is the one place that decides this.
			int hand = armHand(right ? RSLOT_ARM_R : RSLOT_ARM_L);
			double curl = handHolds(pawn, hand) ? grip : rest;
			Vector3 ax = (1, 0, 0);		// measured on this rig: knuckle spread lands on local X

			if (right)
			{
				curlFinger(b, ax, 'bip_index_0_R',  'bip_index_1_R',  'bip_index_2_R',  curl, sign, dur);
				curlFinger(b, ax, 'bip_middle_0_R', 'bip_middle_1_R', 'bip_middle_2_R', curl, sign, dur);
				curlFinger(b, ax, 'bip_ring_0_R',   'bip_ring_1_R',   'bip_ring_2_R',   curl, sign, dur);
				curlFinger(b, ax, 'bip_pinky_0_R',  'bip_pinky_1_R',  'bip_pinky_2_R',  curl, sign, dur);
				// THE THUMB IS NOT ON THE OTHERS' HINGE and the measurement says so:
				// it reads +0.48 on X where the fingers read -0.99, because a thumb is
				// rotated out of the hand's plane by design. Same axis at a reduced
				// angle is an approximation, and an honest one -- a real thumb needs its
				// own measured hinge, which is a separate job with the owner watching.
				curlFinger(b, ax, 'bip_thumb_0_R',  'bip_thumb_1_R',  'bip_thumb_2_R',  curl * thmb, sign, dur);
			}
			else
			{
				curlFinger(b, ax, 'bip_index_0_L',  'bip_index_1_L',  'bip_index_2_L',  curl, sign, dur);
				curlFinger(b, ax, 'bip_middle_0_L', 'bip_middle_1_L', 'bip_middle_2_L', curl, sign, dur);
				curlFinger(b, ax, 'bip_ring_0_L',   'bip_ring_1_L',   'bip_ring_2_L',   curl, sign, dur);
				curlFinger(b, ax, 'bip_pinky_0_L',  'bip_pinky_1_L',  'bip_pinky_2_L',  curl, sign, dur);
				curlFinger(b, ax, 'bip_thumb_0_L',  'bip_thumb_1_L',  'bip_thumb_2_L',  curl * thmb, sign, dur);
			}
		}
	}

	// THE BODY'S OWN ARM, SHOULDER TO WRIST, IN MAP UNITS -- measured off the three
	// bones the chain actually drives, on the body that is actually worn. -1 when the
	// rig does not carry them.
	//
	// The right arm only: a rig with different-length arms is a broken rig, and asking
	// twice would only invite a disagreement nobody would know what to do with.
	//
	// This reads the ANIMATED pose, not the solved one. The reach chain writes its
	// result inside the draw, downstream of everything the bone getters can see, so
	// what comes back here is the arm's own length before the solver stretches it --
	// which is exactly the question. If it ever starts returning the stretched length
	// the ratio below collapses to 1.00 and says so rather than lying.
	private double wholeArmSpan(Actor b)
	{
		if (!b) return -1;
		bool valve = (cvs("rs_body_whole_style", "marine") == "praetor");
		Name up, mid, wrist;
		if (valve)
		{
			up    = 'ValveBiped.Bip01_R_UpperArm';
			mid   = 'ValveBiped.Bip01_R_Forearm';
			wrist = 'ValveBiped.Bip01_R_Hand';
		}
		else
		{
			up    = 'bip_upperArm_R';
			mid   = 'bip_lowerArm_R';
			wrist = 'bip_hand_R';
		}
		if (b.GetBoneIndex(up) < 0 || b.GetBoneIndex(mid) < 0 || b.GetBoneIndex(wrist) < 0) return -1;
		Vector3 ps, pe, pw, ax, ay;
		[ps, ax, ay] = b.GetNamedBonePosition(up);
		[pe, ax, ay] = b.GetNamedBonePosition(mid);
		[pw, ax, ay] = b.GetNamedBonePosition(wrist);
		return (pe - ps).Length() + (pw - pe).Length();
	}

	// ARM SIZE FROM YOUR OWN REACH (plan 4b idea 2). Arms straight out to the
	// sides: the span between the hands, less the shoulders the body draws, halved,
	// is one arm from shoulder to palm. The Slayer's is 20.147 at size 1 (bones
	// 8.849 + 8.694, wrist to palm 2.604). Shoulder height is reported, never
	// changed -- the torso is yours.
	//
	// IT USED TO DO NOTHING AT ALL ON A WHOLE BODY. The measurement was right and
	// then it wrote rs_bp_armright_scale / rs_bp_armleft_scale -- the PART RIG's
	// arm-actor sizes. A whole body has no arm parts, so on the marine and the
	// Praetor this command measured you correctly and then threw the answer away.
	//
	// A whole body's arms cannot be resized on their own: they are bones in one
	// mesh, and the only length lever it has is rs_body_whole_height, which scales
	// the WHOLE model. So this does not write it. That slider means "how tall he is
	// against how tall you are", and silently driving a height from an arm
	// measurement would break the thing it is for, on a body the owner has already
	// fitted. It works the number out and hands it over instead.
	//
	// Nothing is lost by reporting rather than writing: the arm chains run in
	// absolute stretch mode (SetModelReachStretchMode 1), so the palm lands on the
	// controller at any body size. What the ratio buys is LOOK -- a body whose arms
	// are close to yours barely stretches, and one that is far off rubber-bands.
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

		Console.Printf("\c[Gold]RS_VRBody: hands %.1f apart, so each arm is %.1f shoulder to palm.", span, reach);

		Actor b = parts[RSLOT_BODY];
		if (b)
		{
			double armLen = wholeArmSpan(b);
			if (armLen <= 0.01)
			{
				Console.Printf("\c[Red]  This body's arm bones could not be read, so there is nothing to compare you to.");
			}
			else
			{
				double h     = cvf("rs_body_whole_height", 1.0); if (h <= 0.05) h = 1.0;
				double ratio = reach / armLen;
				Console.Printf("\c[Gold]  The body's own arm is %.1f, so it stretches to %.0f%% of its length to reach you.",
					armLen, ratio * 100.0);
				Console.Printf("\c[Gold]  rs_body_whole_height %.2f would match them exactly -- it is %.2f now.", h * ratio, h);
				Console.Printf("\c[Gold]  Not set for you: that is his HEIGHT as well as his arms, so it is yours to choose.");
			}
		}
		else
		{
			// The part rig, unchanged: its arms ARE separate actors, so they can be sized.
			double size = clamp(reach / 20.147, 0.7, 1.5);
			setf("rs_bp_armright_scale", size);
			setf("rs_bp_armleft_scale",  size);
			Console.Printf("\c[Gold]  Arm size set to %.2f.", size);
		}

		double shoulderZ = pawn.HmdPos.Z + su;
		double handsZ    = (m.Z + o.Z) * 0.5;
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
		// GATED, because it ARMS ITSELF. This sits in a tic path and fires whenever the
		// head pitch moves ten degrees or the fade state flips -- so in a headset, just
		// LOOKING AROUND writes console lines for the rest of the session, with no switch
		// to stop it. PRINT_NONOTIFY keeps it out of the player's view but not out of the
		// log. That is the same shape as the diagnostic that crashed the owner's game on
		// 2026-09-19: the fault was not that it was noisy, it was that nothing had to ask
		// for it. A diagnostic must be unable to arm itself.
		if (cvb("rs_body_diag", false)
			&& (!lookLogged || abs(pitchNow - lookLogPitch) >= 10.0 || stateNow != lookLogState))
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
		// WHICHEVER BODY IS WORN. This used to look only at the torso SLOT, which a
		// whole body leaves empty -- so the breath was silently dead the moment the
		// whole body went in, and near-death read exactly like full health.
		//
		// (A stray `wholeHeadOn = null` also sat in this early return, re-applying
		// every head and colour skin EVERY TIC in whole-body mode. It belongs in
		// WorldLoaded, where a new actor really does need its skins back, and that is
		// where it now is.)
		int slot = parts[RSLOT_BODY] ? RSLOT_BODY : RSLOT_TORSO;
		if (!parts[slot])
		{
			if (breath) breath.Destroy();
			breath = null; breathClass = ""; breathAlpha = 0.0; breathPhase = 0.0;
			return;
		}

		string worn = partClass[slot];
		string want = "RS_PartTorsoRed";
		if (slot == RSLOT_BODY)
			want = (worn.IndexOf("Praetor") >= 0) ? "RS_PartBodyPraetorRed" : "RS_PartBodyMarineRed";
		else if (worn.IndexOf("TorsoMarine") >= 0) want = "RS_PartTorsoMarineRed";
		else if (worn.IndexOf("Vest") >= 0)        want = "RS_PartVestRed";
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
			placeActor(pawn, breath, parts[RSLOT_BODY] ? RSLOT_BODY : RSLOT_TORSO);
			breath.ClearInterpolation();
		}
		placeActor(pawn, breath, parts[RSLOT_BODY] ? RSLOT_BODY : RSLOT_TORSO);
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
		else if (s == RSLOT_BODY)              style = cvs("rs_body_whole_style", "marine");
		else                                   style = cvs("rs_body_style_" .. kind, "");
		string want  = lookup(kind, style);

		// "BODY OFF" MEANS THE BODY IS NOT DRAWN. IT DOES NOT MEAN YOU LOSE YOUR HOLSTERS.
		//
		// This used to wipe EVERY slot, holsters included, so switching the body off
		// took your guns off your hips with it. That was never right and it gets worse
		// the moment there is more than one body to choose from: a holster is where
		// YOUR gun hangs, anchored to your own heading, and it belongs to you rather
		// than to whichever mesh you happen to be wearing -- or to none.
		//
		// So the switch empties only what the body actually DRAWS. Holsters and the
		// pouch have their own switch, rs_body_holsters, which is the one that should
		// decide whether you have them.
		if (!cvb("rs_body_enabled", true)
		    && !(s >= RSLOT_HOLSTER_0 && s <= RSLOT_HOLSTER_8))
			want = "";

		// THE WHOLE BODY AND THE PART RIG ARE ALTERNATIVES, NEVER BOTH.
		//
		// Wearing both would draw two torsos and four arms, and the second set
		// would be the one you notice. So the gate is here, at the single place a
		// slot decides what it holds, rather than scattered through placement:
		// one cvar chooses which rig you are running and the other empties.
		//
		// HOLSTERS ARE NOT PART OF THIS. They hang off your body whichever rig
		// draws it, the owner has nine of them tuned, and nothing below touches
		// them -- only the slots the whole body actually replaces.
		if (cvb("rs_body_whole", true))
		{
			// THE HANDS ARE HIS, AND THE ENGINE PINS THEM.
			//
			// The hand slot holds the marine's own hand model, so it is placed on the
			// controller through the HAND FRAME -- exact, every frame, whatever the
			// arm is doing -- and the arm then reaches IT. The whole-body mesh had
			// that backwards: with the hand inside the body mesh the drawn hand went
			// wherever the arm's IK solve landed, which is near the controller only
			// while the arm can reach. That threw away the engine work whose entire
			// purpose is a hand that is exactly where your hand is.
			//
			// This outranks handSlotIsForeign deliberately. RS_WorldHands' hand is
			// still spawned, still holding and grabbing, and still what the reach
			// chain aims at; it is only hidden (see wholeBody), so nothing draws twice.
			// THE HANDS FOLLOW THE BODY -- WHEN THE BODY HAS SEPARATE ONES.
			//
			// A body whose hands are PART OF THE MESH registers none, and then no
			// hand actor is spawned at all: his hands are already on the end of his
			// arms and a second pair would be two pairs. The Eternal marine is that
			// case, by the owner's call -- he was split at the wrists so his hands
			// could be pinned to the controllers, and splitting him made him worse,
			// so he is one mesh again.
			//
			// The Praetor still registers hands, and that is a different thing: his
			// arrived as their own bodyparts from the author. Nothing of his was cut.
			//
			// THE TRADE, stated plainly because it is the owner's to revisit: a hand
			// inside the mesh cannot be pinned. The engine pins an ACTOR. So his
			// hands go where his ARMS put them -- near your controller when the arm
			// can reach, and not when it cannot.
			if (s == RSLOT_HAND_MAIN || s == RSLOT_HAND_OFF)
			{
				string bstyle = cvs("rs_body_whole_style", "marine");
				want = lookup(s == RSLOT_HAND_MAIN ? "handmain" : "handoff", bstyle);
			}
			else if (s != RSLOT_BODY && wholeBodyReplaces(s)) want = "";
		}
		else if (s == RSLOT_BODY) want = "";
		// ...UNLESS THE WHOLE BODY IS SUPPLYING THE HAND. This line runs AFTER the
		// gate above and was wiping the marine's hands to nothing every tic, so they
		// never spawned at all -- the gate's own comment claimed it outranked this
		// check and it did not, because this is further down.
		//
		// "Foreign" means RS_WorldHands owns the hand SLOT, and normally that is the
		// right answer: do not draw a second hand on a controller that already has
		// one. With a whole body it is the wrong answer, because RS_WorldHands' hand
		// is HIDDEN (wholeBody) and the visible hand is supposed to be his.
		if (handSlotIsForeign(s) && !(cvb("rs_body_whole", true)
		    && (s == RSLOT_HAND_MAIN || s == RSLOT_HAND_OFF)))
			want = "";
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

	// HOLSTERS ARE POSABLE PER BODY, AND THAT MEANS TWO LAYERS, NOT ONE.
	//
	// A holster seat that is right on the Eternal marine is wrong on the Praetor --
	// different height, different shoulder width, different hip. So the whole holster
	// layout belongs to the BODY, not to the player, and switching body must switch it.
	//
	// There are two layers to carry and only one of them was ever saved:
	//   THE SEAT   sFwd/sSide/sUp/yaw/pitch/roll/scale -- where the holster sits on you.
	//              Written by script into FollowBodyOfs. Already in the profile.
	//   THE FIT    rs_bp_hol<N>_* -- how the holster's MESH sits in its own slot.
	//              Read by the RENDERER every frame through PlacementPrefix, which is
	//              exactly why those sliders move while a menu is open and the seat's
	//              cannot: script does not run behind a menu and the renderer does.
	//              NINETY cvars, and every one of them was shared across all bodies.
	//
	// Both go in the profile now and the profile is named for the body. Tune the marine,
	// switch to the Praetor, tune that, switch back: each keeps its own.
	private string profileName()
	{
		string st = cvs("rs_body_whole_style", "marine");
		if (st == "") st = "marine";
		return "vrbody_" .. st;
	}

	// The ten fit values every holster has, in one place so save and load cannot
	// disagree about the list -- which is the usual way a save/load pair rots.
	static const String FIT_KEY[] = {
		"_ofs_x", "_ofs_y", "_ofs_z", "_yaw", "_pitch", "_roll",
		"_scale", "_scale_x", "_scale_y", "_scale_z" };

	private void saveProfile(string name)
	{
		level.JSONProfileBegin();
		for (int h = 0; h < 9; ++h)
		{
			string pre = HOLSTER_PREFIX[h];
			for (int k = 0; k < FIT_KEY.Size(); ++k)
			{
				let c = CVar.FindCVar(pre .. FIT_KEY[k]);
				if (c) level.JSONProfileSetDouble(pre .. FIT_KEY[k], c.GetFloat());
			}
		}
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
		for (int h = 0; h < 9; ++h)
		{
			string pre = HOLSTER_PREFIX[h];
			for (int k = 0; k < FIT_KEY.Size(); ++k)
			{
				let c = CVar.FindCVar(pre .. FIT_KEY[k]);
				// Absent key -> the cvar is LEFT ALONE rather than zeroed. A profile
				// written before the fit was stored has none of these, and zeroing a
				// holster's size because an old file is silent about it would throw
				// away tuning the owner did by hand.
				if (c) c.SetFloat(level.JSONProfileGetDouble(pre .. FIT_KEY[k], c.GetFloat()));
			}
		}
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
			if (!editMode && wasHolding) saveProfile(profileName());
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
		if (e.Name ~== "rs_body_mirror")       { toggleMirror(pawn);  return; }
		if (e.Name ~== "rs_body_save")  { saveProfile(profileName()); return; }
		if (e.Name ~== "rs_body_load")  { loadProfile(profileName()); return; }
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
		handTargets(pawn);
		tickFingers(pawn);
		tickLean(pawn);
		tickMirror(pawn);
		syncPawnSprite(pawn);
		syncHeadCopy(pawn);
		diagBurst(pawn);
		pumpProfile();
		pumpEdit();
		updateBodyYaw(pawn);
		tickLegs(pawn);
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
		// SWITCHING THE WHOLE BODY OFF MID-PLAY GIVES THE HANDS BACK. The body hides
		// the hand it reaches for; without this you would drop back to the part rig
		// and be left holding two invisible hands. Checked on the edge only.
		bool wholeNow = cvb("rs_body_whole", true);
		if (wholeWas && !wholeNow) showReachedHands();
		wholeWas = wholeNow;

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
