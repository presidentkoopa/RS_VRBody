// ============================================================================
// LEGS THAT STEP, AND A CROUCH THAT COMES FREE WITH THEM.
//
// WHAT THIS IS. Two reach chains down the worn body's legs, aimed at two foot
// targets this file walks around the world. The body already runs chains 0 and 1
// down the arms; the engine allows four (REACH_CHAINS, model_reach.cpp:102), so
// the legs take 2 and 3 and the budget is exactly spent.
//
// WHY CROUCH AND LEAN NEED NOTHING ELSE. The body is seated off the headset
// (slotWorldAt: HmdPos plus the slot's seat), so when the player physically
// crouches the hips come down. Today the whole marine sinks with them and the
// legs drive through the floor, because nothing holds the feet. Plant the feet
// and the SAME motion bends the knees instead -- a crouch is hips-down-with-
// feet-still, which is what leg IK already means. Leaning is the same trick
// sideways: the hips move, the feet stay, the legs angle. Neither needed a
// system of its own; they needed the feet to stop being furniture.
//
// THE ONE THING THAT SELLS WALKING is not the swing, it is that a PLANTED FOOT
// DOES NOT SLIDE. So a planted foot's target is simply not moved -- it is a free
// actor standing in the world, and leaving it alone is the whole mechanism. This
// is why the targets are actors rather than a position recomputed from the body
// each tic: anything recomputed from the body inherits the body's motion, which
// is exactly the slide.
//
// PAWN-KEYED, DELIBERATELY. RS_VRBodyRig.WorldTick still reads
// players[consoleplayer], so today only the local player has a body at all. This
// file takes a pawn and indexes its state by player number anyway, so that when
// the rig is made per-player the legs are already right rather than needing the
// same archaeology RS_Held needed. Checking that the CONSUMER is local is not
// enough; the writer has to be right too.
// ============================================================================

// The target a leg chain reaches for. No model, no collision, nothing but a
// position -- the same shape the arm rig's wrist targets use.
class RS_VRFootTarget : Actor
{
	Default
	{
		+NOGRAVITY;
		+NOBLOCKMAP;
		+NOINTERACTION;
		+NOTONAUTOMAP;
		+INVISIBLE;
		Radius 1;
		Height 1;
	}
}

// PLAY SCOPE, EXPLICITLY. A bare `class` is DATA scope, and every call this makes
// -- SetModelReachChain, Spawn, SetOrigin, Destroy -- is a play function. Without
// the marker it fails at load with "Can't call play function ... from data context",
// which is a compile error rather than a silent one, but only because these happen
// to be native calls; a data-scope object quietly holding play state is worse.
class RS_VRLegs play
{
	// ---- rig geometry, MEASURED, and why these are constants ---------------
	//
	// Hip half-spacing and hip height in each body's own model units, measured
	// off the meshes: marine bip_hip_R at (-4.226, -0.086, 33.270), Praetor
	// ValveBiped.Bip01_R_Thigh at (-3.484, 0, 34.670).
	//
	// They are constants HERE because ZScript cannot ask a model where a joint
	// is -- the engine has exactly one getter and it is for drive values
	// (model_reach.cpp:1528, "No posed joint is readable"). That is survey item
	// 1 in Engine docs/VR_BODY_IK_PLAN.md, and when it lands these two lines
	// become a measurement and any new body works without editing this file.
	const HIP_HALF_MARINE  = 4.226;
	const HIP_HALF_PRAETOR = 3.484;
	const LEG_LEN_MARINE   = 28.72;   // hip z 33.270 down to foot z 4.554
	const LEG_LEN_PRAETOR  = 29.35;   // 34.670 down to 5.318

	// ---- the step ----------------------------------------------------------
	// A foot steps when the body has walked far enough from where it is planted.
	// Below this the feet simply stay put, which is what standing still is.
	const STRIDE_TRIGGER = 11.0;    // map units of drift before a foot must move
	const STEP_TICS      = 7.0;     // ~0.2s at 35Hz
	const STEP_ARC       = 3.2;     // how high the swinging foot lifts
	const LEAD           = 0.16;    // how far ahead of the body a step is placed,
	                                // per unit of speed -- a step lands where the
	                                // body is GOING, not where it has been

	// ---- per player, per foot ----------------------------------------------
	// Flat MAXPLAYERS*2 with an index helper, the same shape and for the same
	// reason as RS_Held: a two-dimensional array reads worse and can be
	// mis-indexed by transposing two subscripts without the compiler caring.
	static int IX(int pnum, int foot) { return pnum * 2 + foot; }

	Actor   tgt[MAXPLAYERS * 2];
	Vector3 plant[MAXPLAYERS * 2];      // where a planted foot is standing
	bool    planted[MAXPLAYERS * 2];
	Vector3 stepFrom[MAXPLAYERS * 2];
	Vector3 stepTo[MAXPLAYERS * 2];
	double  stepT[MAXPLAYERS * 2];      // 0..1 through a swing, < 0 = not stepping
	bool    started[MAXPLAYERS];

	private static double cvf(String n, double d)
	{
		let c = CVar.FindCVar(n);
		return c ? c.GetFloat() : d;
	}

	private static bool cvb(String n, bool d)
	{
		let c = CVar.FindCVar(n);
		return c ? c.GetBool() : d;
	}

	private static String cvs(String n, String d)
	{
		let c = CVar.FindCVar(n);
		return c ? c.GetString() : d;
	}

	// The floor under a point, honouring slopes and whatever sector it is over
	// rather than assuming the player's own. A foot placed ahead of the body on a
	// stair has to land on the STAIR.
	private static double groundAt(Vector3 p)
	{
		Sector sec = Level.PointInSector((p.x, p.y));
		if (!sec) return p.z;
		return sec.floorplane.ZatPoint((p.x, p.y));
	}

	// ---- setup: the two chains --------------------------------------------
	//
	// Joint names per rig family, the same table the arms use. Hardcoding id's
	// names would leave the Praetor's legs hanging dead -- compiling cleanly,
	// drawing fine, never bending -- which is exactly what happened to the arms
	// once already.
	void Setup(PlayerPawn pawn, Actor body, bool valve)
	{
		if (!pawn || !body) return;
		int pnum = pawn.PlayerNumber();
		if (pnum < 0 || pnum >= MAXPLAYERS) return;

		for (int f = 0; f < 2; ++f)
		{
			bool right = (f == 0);
			Name hip, knee, foot, tuning;
			// The side vector is set HERE, in the if/else, and NOT by a ternary
			// further down. A vector assigned from a ternary of LITERALS compiles
			// and then aborts the VM the first time the function runs -- REGT_ADDROF
			// not implemented for vectors. Declaring first and assigning from a
			// ternary is NOT the fix; the fix is that each branch assigns its own
			// literal, which is what the arm rig does and why the arm rig works.
			Vector3 side;
			if (right)
			{
				hip    = valve ? 'ValveBiped.Bip01_R_Thigh' : 'bip_hip_R';
				knee   = valve ? 'ValveBiped.Bip01_R_Calf'  : 'bip_knee_R';
				foot   = valve ? 'ValveBiped.Bip01_R_Foot'  : 'bip_foot_R';
				tuning = 'rs_legik_rt';
				side   = (-1, 0, 0);
			}
			else
			{
				hip    = valve ? 'ValveBiped.Bip01_L_Thigh' : 'bip_hip_L';
				knee   = valve ? 'ValveBiped.Bip01_L_Calf'  : 'bip_knee_L';
				foot   = valve ? 'ValveBiped.Bip01_L_Foot'  : 'bip_foot_L';
				tuning = 'rs_legik_lf';
				side   = (1, 0, 0);
			}

			int ch = 2 + f;      // chains 0 and 1 are the arms
			body.SetModelReachChain(ch, hip, knee, foot, tuning);

			// THE POLE POINTS FORWARD, because a knee bends forward and an elbow
			// does not. The arm rig passes outward/down/back and the solver builds
			// its pole from all three; for a leg the whole pole is "forward", which
			// on these meshes is -Y in model space -- the toe joint sits at y
			// -4.168 against the foot's +1.001, so the toes, and therefore the
			// front of the body, are -Y.
			//
			// DECLARED THEN ASSIGNED. `Vector3 v = cond ? (a,b,c) : (d,e,f);`
			// compiles and then aborts the VM the first time it runs -- REGT_ADDROF
			// not implemented for vectors. It cost a live abort on this rig once.
			Vector3 fwd;
			fwd = (0, -1, 0);
			Vector3 up;
			up = (0, 0, 1);
			body.SetModelReachFrame(ch, fwd, side, up, up);
			body.SetModelReachFollowJoint(ch, 'None');

			if (!tgt[IX(pnum, f)])
			{
				tgt[IX(pnum, f)] = Actor.Spawn("RS_VRFootTarget", pawn.pos);
				planted[IX(pnum, f)] = false;
				stepT[IX(pnum, f)] = -1.0;
			}
			if (tgt[IX(pnum, f)])
				body.SetModelReachTarget(ch, tgt[IX(pnum, f)], (0, 0, 0),
				                         (0, -1, 0), (1, 0, 0), 'rs_leg_sock');
		}
		started[pnum] = true;
	}

	void Clear(PlayerPawn pawn, Actor body)
	{
		if (!pawn) return;
		int pnum = pawn.PlayerNumber();
		if (pnum < 0 || pnum >= MAXPLAYERS) return;
		for (int f = 0; f < 2; ++f)
		{
			if (body) body.ClearModelReachChain(2 + f);
			if (tgt[IX(pnum, f)]) { tgt[IX(pnum, f)].Destroy(); tgt[IX(pnum, f)] = null; }
			planted[IX(pnum, f)] = false;
			stepT[IX(pnum, f)] = -1.0;
		}
		started[pnum] = false;
	}

	// ---- the walk ----------------------------------------------------------
	//
	// bodyOrigin is where the worn model's own origin sits in the world -- the
	// rig's slotWorldAt for the body slot -- because that origin is at the
	// model's FEET (the marine's mesh runs z 0.002 .. 64.687), so the floor under
	// it is the floor the feet stand on.
	void Tick(PlayerPawn pawn, Vector3 bodyOrigin, double bodyYaw, double scale, bool valve)
	{
		if (!pawn) return;
		int pnum = pawn.PlayerNumber();
		if (pnum < 0 || pnum >= MAXPLAYERS || !started[pnum]) return;

		double half = (valve ? HIP_HALF_PRAETOR : HIP_HALF_MARINE) * scale;
		double trig = cvf("rs_legs_stride", STRIDE_TRIGGER);
		double rate = 1.0 / MAX(1.0, cvf("rs_legs_steptics", STEP_TICS));
		double arc  = cvf("rs_legs_arc", STEP_ARC);
		double lead = cvf("rs_legs_lead", LEAD);

		double fx = cos(bodyYaw), fy = sin(bodyYaw);
		double rx = sin(bodyYaw), ry = -cos(bodyYaw);

		// Where the body is going, so a step lands ahead of it rather than under
		// where it just was. Speed is the pawn's, which is playsim state and the
		// same on every machine.
		Vector3 vel = pawn.Vel;
		double speed = (vel.x * vel.x + vel.y * vel.y) > 0 ? sqrt(vel.x * vel.x + vel.y * vel.y) : 0;

		// A STRIDE HAS TO KEEP UP, AND AT SPEED IT DID NOT.
		//
		// The swing took a FIXED number of tics and a stride started after a FIXED amount
		// of drift, both tuned at walking pace. Run, and the body covers far more ground
		// during those same seven tics than the foot is travelling, so every foot lands
		// behind where it was aimed and is instantly out of position again -- which reads
		// exactly as the owner described it: "they do nicely when taking baby steps but
		// moving at speed is like hovering with dangly legs".
		//
		// Two things scale, because a person running does BOTH: the legs swing FASTER and
		// the strides get LONGER. Scaling only the rate gives a sprinting mince; scaling
		// only the stride gives slow-motion lunges.
		//
		// Referenced to rs_legs_runspeed, map units per tic, about a Doom run. Clamped so
		// a swing can never take fewer than two tics -- below that the foot teleports and
		// the arc is invisible.
		double refSpd = MAX(1.0, cvf("rs_legs_runspeed", 9.0));
		double fast   = clamp(speed / refSpd, 0.0, 1.5);
		trig *= 1.0 + fast * cvf("rs_legs_stride_gain", 0.85);
		double stepT2 = MAX(2.0, cvf("rs_legs_steptics", STEP_TICS) / (1.0 + fast * cvf("rs_legs_rate_gain", 1.30)));
		rate = 1.0 / stepT2;

		// JUMPING: THE FEET COME WITH YOU.
		//
		// Every foot target below is placed on the FLOOR (groundAt). That is right for
		// walking and wrong the moment you leave the ground: the body rises, the targets
		// stay down there, and the legs stretch after them -- and because these chains
		// reach ABSOLUTELY they will succeed, so it reads as a marine growing stilts
		// rather than as a marine jumping.
		//
		// Airborne, the feet hang under the hips with a little tuck, and neither foot is
		// planted or mid-step. Landing drops straight back into the step machine with
		// both feet unplanted, so the next stride re-plants them where they actually
		// landed instead of snapping back to wherever they took off from.
		//
		// bOnMobj is in the test because a pawn standing on another actor is on the
		// ground while its Z sits well above the floor; velocity alone would call that
		// a jump and tuck the legs up under a marine who is simply standing on a crate.
		bool airborne = (pawn.pos.z > pawn.floorz + 1.0) && !pawn.bOnMobj;
		if (airborne && cvb("rs_legs_jump", true))
		{
			double legLen = (valve ? LEG_LEN_PRAETOR : LEG_LEN_MARINE) * scale;
			double tuck   = clamp(cvf("rs_legs_jump_tuck", 0.78), 0.2, 1.0);
			for (int f = 0; f < 2; ++f)
			{
				int i = IX(pnum, f);
				if (!tgt[i]) continue;
				double sideJ = (f == 0) ? -half : half;
				tgt[i].SetOrigin((bodyOrigin.x + sideJ * rx,
				                  bodyOrigin.y + sideJ * ry,
				                  bodyOrigin.z - legLen * tuck), true);
				planted[i] = false;
				stepT[i]   = -1.0;
			}
			return;
		}

		// A foot is in the air at most one at a time. Both swinging is a jump, and
		// a jump is not a walk -- without this the body drops into a bunny-hop the
		// moment the stride trigger fires for both feet on the same tic.
		bool anySwing = false;
		for (int f = 0; f < 2; ++f)
			if (stepT[IX(pnum, f)] >= 0) anySwing = true;

		for (int f = 0; f < 2; ++f)
		{
			int i = IX(pnum, f);
			if (!tgt[i]) continue;
			double side = (f == 0) ? -half : half;      // foot 0 is the right leg

			// Where this foot WANTS to be: under its hip, led by the body's motion,
			// on whatever floor is there.
			Vector3 want;
			want = (bodyOrigin.x + rx * side + vel.x * lead * 35.0,
			        bodyOrigin.y + ry * side + vel.y * lead * 35.0,
			        bodyOrigin.z);
			want.z = groundAt(want);

			if (stepT[i] >= 0)
			{
				// SWINGING. Lerp across, lift over an arc, land.
				stepT[i] += rate;
				if (stepT[i] >= 1.0)
				{
					plant[i] = stepTo[i];
					planted[i] = true;
					stepT[i] = -1.0;
					tgt[i].SetOrigin(plant[i], false);
				}
				else
				{
					double t = stepT[i];
					Vector3 p;
					p = (stepFrom[i].x + (stepTo[i].x - stepFrom[i].x) * t,
					     stepFrom[i].y + (stepTo[i].y - stepFrom[i].y) * t,
					     stepFrom[i].z + (stepTo[i].z - stepFrom[i].z) * t);
					p.z += sin(t * 180.0) * arc;         // degrees: ZScript sin takes them
					tgt[i].SetOrigin(p, false);
				}
				continue;
			}

			if (!planted[i])
			{
				// First tic, or after a teleport: put the foot down where it belongs
				// rather than stepping to it from wherever it was.
				plant[i] = want;
				planted[i] = true;
				tgt[i].SetOrigin(plant[i], false);
				continue;
			}

			// PLANTED. The target is NOT touched -- that is the whole anti-slide.
			// Only the decision to leave is made here.
			Vector3 d;
			d = (want.x - plant[i].x, want.y - plant[i].y, 0);
			double drift = sqrt(d.x * d.x + d.y * d.y);

			// A big vertical move means the floor changed under us (a lift, a
			// teleport, a fall) and the foot must go now rather than stretch.
			bool floorGone = abs(want.z - plant[i].z) > 24.0;

			if ((drift > trig && !anySwing) || floorGone)
			{
				stepFrom[i] = plant[i];
				stepTo[i]   = want;
				stepT[i]    = 0.0;
				planted[i]  = false;
				anySwing    = true;
			}
		}
	}
}
