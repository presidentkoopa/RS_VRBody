// ============================================================================
// PHYSICAL HOLSTERS.
//
// The nine holster slots in body_rig.zs are real seats on the body, dragged into
// place in placement mode. This makes them hold guns:
//
//   STOW  grip while holding a real weapon, hand inside an EMPTY holster: the gun
//         leaves the hand at once and settles into the holster with a fade.
//   DRAW  grip empty-handed inside an OCCUPIED holster: the gun comes with your
//         hand immediately, drawn in the controller's frame at headset rate. Pull
//         far enough and it goes live in the hand. Let go first and it is back
//         where it was.
//
// The pull is PATH LENGTH, so a curved draw off an angled chest slot counts the
// same as a straight pull off a hip -- and it is measured relative to the
// holster, so walking with the grip held does not draw anything.
//
// Every position comes from RS_VRBodyRig.SlotWorld()/BodyYaw(): the seat the
// holster mesh itself sits on. Drag a holster in placement mode and its catch
// volume and the gun in it go with it -- there is one table of holster positions.
//
// The store/draw plumbing -- the grip claim and its hysteresis, the switch
// guards, the hand relabel, instant switch, rollback, the drift-back reconcile,
// the lifecycle release -- is RS_VR_Unified's RS_Holsters.zs, mechanism for
// mechanism. Each guard is there because its absence cost a session.
// ============================================================================

// The stored gun's display. One per holster, parked by RS_VRBodyHolsters.
//
// It does not know the weapon. It asks the engine what the gun looks like --
// whichever class this instance's model resolves against, on whichever frame
// carries a model -- and wears that via A_ChangeModel. No weapon pack is named.
class RS_VRHolsterProp : Actor
{
	Default
	{
		// LOAD-BEARING. Actor's default "Normal" carries STYLEF_Alpha1, and the
		// renderer throws Alpha away for it -- the fade renders as nothing and then
		// a pop. RS_HolsterProp lost a session to exactly this.
		RenderStyle "Translucent";

		+NOBLOCKMAP
		+NOGRAVITY
		+NOINTERACTION
		+DONTSPLASH
		+NOTONAUTOMAP
		+NOTELEPORT
		Radius 1;
		Height 1;
	}

	States { Spawn: TNT1 A -1; Stop; }

	const FADE_STEP     = 0.125;   // ~8 tics either way
	const POP_TICS      = 6;
	const POP_OVERSHOOT = 1.35;

	// The size presets, as a bounding radius in map units against the model's
	// own measured one (GetModelBoundsHint).
	const SIZE_SMALL  = 3.0;
	const SIZE_MEDIUM = 4.4;
	const SIZE_LARGE  = 6.0;

	// A weapon with no model anywhere shows its pickup sprite, which is authored
	// for the floor.
	const SPRITE_SCALE = 0.5;

	Weapon       shownWeapon;
	class<Actor> shownClass;
	// The class A_ChangeModel was given; null means no model, the sprite shows.
	class<Actor> boundClass;

	// Measured off the model, not guessed. Mirroring is a per-model authoring
	// choice with no relationship to hand, so one global flip is right for only
	// part of any arsenal.
	bool   mirrored;
	double bakedAngleOffset;
	double bakedPitchOffset;
	double bakedRollOffset;
	bool   boundsFound;
	double measuredRadius;

	// What was drawing in the hand at the moment it was stowed -- for a weapon
	// whose model is not on its Ready frame. Trusted only for that weapon.
	Weapon   hintFor;
	SpriteID hintSprite;
	int      hintFrame;

	// 0 on the body; 1/2 riding that controller mid-draw. FollowHandMode's own
	// numbering, so the zero default is the right one.
	int followHand;

	private double fadeAlpha;
	private bool   fadeVisible;
	private double baseScale;
	private int    popTicsRemaining;
	private bool   pendingClear;

	override void BeginPlay()
	{
		Super.BeginPlay();
		// The borrowed MODELDEF opts into actor yaw only -- a weapon in a hand is
		// posed by the psprite path -- so without this the pitch and roll written
		// below are discarded by the renderer.
		ForceModelAngles = true;
		// The trims on the fits page. The RENDERER reads these, so they move the
		// gun while the menu is open; script never writes them.
		PlacementPrefix = 'rs_bp_stored';
	}

	void SetHint(Weapon w, SpriteID spr, int frm)
	{
		hintFor    = w;
		hintSprite = spr;
		hintFrame  = frm;
	}

	// WHAT THE GUN LOOKED LIKE IN THE HAND, when that was a separate actor.
	//
	// A gun drawn as a thing in the room -- RS_VR_PistolTest's cards, and every
	// gun built that way after it -- is an invisible weapon (TNT1 views, no
	// model) plus a separate actor riding the controller. The weapon has
	// nothing to copy, so without this the holster hung an empty space.
	//
	// Kept as class, sprite and frame, never the actor itself: the gun's own
	// system destroys that actor the moment the gun leaves the hand.
	Weapon       bodyFor;
	class<Actor> bodyClass;
	SpriteID     bodySprite;
	int          bodyFrame;

	void SetBody(Weapon w, Actor body)
	{
		bodyFor   = w;
		bodyClass = null;
		if (!body) return;
		bodyClass  = body.GetClass();
		bodySprite = body.sprite;
		bodyFrame  = body.frame;
	}

	private bool HasModelFor(class<Actor> cls, int spr, int frm)
	{
		bool found;
		bool mir;
		double a;
		double p;
		double r;
		[found, mir, a, p, r] = level.GetModelOrientationHint(cls, spr, frm);
		return found;
	}

	// What a stored gun turned out to look like -- including NOTHING, which in
	// a headset is indistinguishable from the holster not working at all.
	private static void traceShow(Weapon w, String what)
	{
		let c = CVar.GetCVar("rs_body_holster_debug", players[consoleplayer]);
		if (c && !c.GetBool()) return;
		Console.Printf("[HOLSTER] stored %s %s", w.GetClassName(), what);
	}

	// Show a weapon, or null to fade out.
	void ShowWeapon(Weapon w)
	{
		class<Actor> wantClass = null;
		if (w) wantClass = level.GetActorModelClass(w);
		if (w == shownWeapon && wantClass == shownClass)
			return;
		shownWeapon = w;
		shownClass  = wantClass;

		if (!w)
		{
			pendingClear = true;   // Tick clears the model once the fade-out ends
			SetVisible(false);
			return;
		}

		class<Actor> own = w.GetClass();
		if (!wantClass) wantClass = own;

		// WHICH FRAME CARRIES THE MODEL. The first (class, sprite, frame) the
		// engine resolves wins: the Ready frame (the idle held pose), then what was
		// on screen in the hand at stow time, then the pickup. Tried against the
		// class this instance resolves to, then against the weapon's own class.
		State ready = w.FindState("Ready");
		State spawn = w.FindState("Spawn");
		boundClass = null;
		for (int pass = 0; pass < 2 && boundClass == null; ++pass)
		{
			class<Actor> c = wantClass;
			if (pass == 1)
			{
				if (own == wantClass) break;
				c = own;
			}
			if (ready && HasModelFor(c, ready.sprite, ready.Frame))
			{
				sprite = ready.sprite; frame = ready.Frame; boundClass = c;
			}
			else if (hintFor == w && HasModelFor(c, hintSprite, hintFrame))
			{
				sprite = hintSprite; frame = hintFrame; boundClass = c;
			}
			else if (spawn && HasModelFor(c, spawn.sprite, spawn.Frame))
			{
				sprite = spawn.sprite; frame = spawn.Frame; boundClass = c;
			}
		}

		// THE GUN'S BODY, when the weapon itself had no model -- see SetBody.
		// Body placement outranks the borrowed MODELDEF's FollowMainHand
		// (models.cpp: the hand path only runs when the body path did not), so
		// the gun hangs in the holster rather than jumping back to the hand.
		if (!boundClass && bodyFor == w && bodyClass && HasModelFor(bodyClass, bodySprite, bodyFrame))
		{
			sprite = bodySprite; frame = bodyFrame; boundClass = bodyClass;
		}

		if (boundClass)
		{
			bool found;
			[found, mirrored, bakedAngleOffset, bakedPitchOffset, bakedRollOffset]
				= level.GetModelOrientationHint(boundClass, sprite, frame);
			[boundsFound, measuredRadius] = level.GetModelBoundsHint(boundClass, sprite, frame);
			A_ChangeModel(boundClass.GetClassName());
			traceShow(w, String.Format("is drawn with the %s model", boundClass.GetClassName()));
		}
		else
		{
			// A sprite-only weapon: its pickup sprite is what it looks like in the
			// world, so that is what hangs in the holster.
			mirrored = false;
			bakedAngleOffset = 0.0;
			bakedPitchOffset = 0.0;
			bakedRollOffset  = 0.0;
			boundsFound = false;
			if (!spawn)
			{
				traceShow(w, "has no model and no Spawn state -- NOTHING to see in the holster");
				SetVisible(false);
				return;
			}
			sprite = spawn.sprite;
			frame  = spawn.Frame;
			if (spawn.sprite == GetSpriteIndex("TNT1"))
				traceShow(w, "has no model and an invisible pickup sprite -- NOTHING to see in the holster");
			else
				traceShow(w, "has no model -- hanging its pickup sprite instead");
		}

		pendingClear = false;
		popTicsRemaining = POP_TICS;
		SetVisible(true);
		SolveScale();
	}

	// Recomputed every tic by the manager, so a size change reaches a gun that is
	// already in a holster.
	void SolveScale()
	{
		if (!boundClass)
		{
			baseScale = SPRITE_SCALE;
			return;
		}

		// AS HELD. A weapon's model is authored for the HUD path, where one model
		// unit is vr_vunits_per_meter * 0.01 map units (0.34 at the default 34);
		// the world path is one to one. Matching it keeps the gun the size it is in
		// your hand, so it does not change size as you draw it.
		double asHeld = 0.34;
		let vu = CVar.GetCVar("vr_vunits_per_meter", players[consoleplayer]);
		if (vu && vu.GetFloat() > 0.001) asHeld = vu.GetFloat() * 0.01;

		double target = 0.0;
		let sz = CVar.GetCVar("rs_body_holster_size", players[consoleplayer]);
		int mode = sz ? sz.GetInt() : 0;
		if (mode == 1)      target = SIZE_SMALL;
		else if (mode == 2) target = SIZE_MEDIUM;
		else if (mode == 3) target = SIZE_LARGE;

		if (target > 0.0 && boundsFound && measuredRadius > 0.0)
			baseScale = target / measuredRadius;
		else
			baseScale = asHeld;
	}

	// The Scale Tick will draw at THIS tic, settle-pop included. The manager
	// centres the gun with it, so it has to be the same number Tick writes.
	double DrawScale()
	{
		if (followHand != 0) return 1.0;
		if (popTicsRemaining <= 0) return baseScale;
		double t = 1.0 - ((popTicsRemaining * 1.0) / POP_TICS);
		return baseScale * (POP_OVERSHOOT - ((POP_OVERSHOOT - 1.0) * t));
	}

	// 0 = sits on the body. 1/2 = rides that controller.
	void SetFollowHand(int mode)
	{
		if (mode == followHand) return;
		followHand     = mode;
		FollowHandMode = mode;
		FollowHandOfs  = (0, 0, 0);
		if (mode != 0)
		{
			// In the hand it is drawn the way a held gun is: the controller's frame
			// with the HUD's own 0.01, the weapon's own placement, no holster
			// angles. 'None' is read by the renderer as "use the MODELDEF's".
			// Off the holster too: FollowActor outranks FollowHandMode.
			FollowActor      = null;
			FollowBodyMode   = 0;
			PlacementPrefix  = 'None';
			Angle = 0.0;
			Pitch = 0.0;
			Roll  = 0.0;
			fadeVisible      = true;
			popTicsRemaining = 0;
		}
		else
		{
			PlacementPrefix = 'rs_bp_stored';
		}
	}

	// The draw completed and the real gun is in the hand -- this one goes at once
	// rather than fading out over it.
	void HideNow()
	{
		SetFollowHand(0);
		FollowActor = null;
		fadeAlpha   = 0.0;
		fadeVisible = false;
		Alpha       = 0.0;
		bINVISIBLE  = true;
		ClearModelStateFrames();
		sprite = GetSpriteIndex("TNT1");
		frame  = 0;
		pendingClear = false;
		shownWeapon  = null;
		shownClass   = null;
		boundClass   = null;
	}

	// TRANSLUCENT ONLY WHILE FADING -- the torso's rule (body_rig.zs, the look-down
	// fade), for the same reason. A model drawn in any style but Normal goes to the
	// translucent pass (hw_sprites.cpp, the `modelframe && RenderStyle !=
	// DefaultRenderStyle()` test), which draws with the depth mask OFF
	// (HWDrawInfo::RenderTranslucent) and back-face culling ON (BeginDrawModel).
	// With no depth write a gun's own triangles land in index order, so a far part
	// paints over a near one: the stowed gun looked see-through while the same
	// mesh in the hand (WM_Prop, "Normal") was solid. Alpha 1 in Translucent is
	// still the translucent pass, so full opacity alone never fixed it.
	// The Default stays "Translucent": the fade starts from zero on that style.
	private void ApplyFadeStyle(double a)
	{
		if (a >= 0.999) A_SetRenderStyle(1.0, STYLE_Normal);
		else            A_SetRenderStyle(a, STYLE_Translucent);
	}

	void SetVisible(bool show)
	{
		fadeVisible = show;
		if (show) bINVISIBLE = false;
	}

	override void Tick()
	{
		Super.Tick();

		if (followHand != 0)
		{
			fadeAlpha  = 1.0;
			bINVISIBLE = false;
			ApplyFadeStyle(1.0);
			Scale = (1.0, 1.0);
			return;
		}

		if (fadeVisible)
		{
			fadeAlpha += FADE_STEP;
			if (fadeAlpha > 1.0) fadeAlpha = 1.0;
		}
		else
		{
			fadeAlpha -= FADE_STEP;
			if (fadeAlpha < 0.0) fadeAlpha = 0.0;
			if (fadeAlpha <= 0.0)
			{
				bINVISIBLE = true;
				if (pendingClear)
				{
					ClearModelStateFrames();
					sprite = GetSpriteIndex("TNT1");
					frame = 0;
					boundClass = null;
					pendingClear = false;
				}
			}
		}
		ApplyFadeStyle(fadeAlpha);

		double s = DrawScale();
		Scale = (s, s);
		if (popTicsRemaining > 0) popTicsRemaining--;
	}
}

// The trigger and the table. Console player only, like every lane of this rig.
class RS_VRBodyHolsters : EventHandler
{
	const CLAIM_HYSTERESIS   = 1.4;   // exit radius multiplier
	const FAST_SWAP_COOLDOWN = 4;     // instant switch: pure debounce
	const SLOW_SWAP_COOLDOWN = 20;    // a default lower is 16 tics; 12 was too short
	const STUCK_TICS         = 70;    // ~2s, well past any healthy lower/raise

	Array<Weapon>           contents;   // by (slot - RSLOT_HOLSTER_0); null = empty
	Array<RS_VRHolsterProp> props;

	// Per hand, 0 main / 1 off. Slots are RSLOT_* numbers, -1 for none -- seeded
	// in OnRegister, because an int's zero default is a real slot number.
	int     claimSlot[2];
	int     drawSlot[2];
	double  drawAccum[2];
	Vector3 drawLastRel[2];
	bool    prevGrip[2];
	int     lastSwapTic[2];

	// The tic this handler started a switch that did not settle inside the call.
	// Only OUR switches are ever forced along; see recoverStuckSwitch.
	int ourSwitchTic;

	Actor worldHand[2];
	private bool ready;
	private bool warnedNoFist;

	override void OnRegister()
	{
		for (int h = 0; h < 2; ++h)
		{
			claimSlot[h]   = -1;
			drawSlot[h]    = -1;
			lastSwapTic[h] = -1000;
		}
	}

	private void ensure()
	{
		if (ready) return;
		int n = RSLOT_HOLSTER_8 - RSLOT_HOLSTER_0 + 1;
		contents.Resize(n);
		props.Resize(n);
		for (int i = 0; i < n; ++i) { contents[i] = null; props[i] = null; }
		ready = true;
	}

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

	private bool instant() { return cvb("rs_body_holster_instant", true); }
	private int swapCooldown() { return instant() ? FAST_SWAP_COOLDOWN : SLOW_SWAP_COOLDOWN; }

	private static Weapon handWeapon(PlayerPawn pawn, int hand)
	{
		return (hand == 0) ? pawn.player.ReadyWeapon : pawn.player.OffhandWeapon;
	}

	private static bool isEmpty(Weapon w)
	{
		return w == null || RS_EmptyHand.IsFist(w.GetClass());
	}

	private static void unflag(Weapon w)
	{
		w.bNoAutoSwitchTo = w.Default.bNoAutoSwitchTo;
		w.bHolsterHidden  = false;
	}

	private RS_VRHolsterProp propFor(int ci, PlayerPawn pawn)
	{
		if (!props[ci])
			props[ci] = RS_VRHolsterProp(Actor.Spawn("RS_VRHolsterProp", pawn.Pos, NO_REPLACE));
		return props[ci];
	}

	// WHERE THE HAND IS -- the palm bone of RS_WorldHands' hand when it is loaded,
	// the controller otherwise. Reached by name, so this pk3 still loads without it.
	// A reach measured from somewhere other than the drawn hand fails silently.
	private Vector3 handPoint(PlayerPawn pawn, int hand)
	{
		Vector3 c = (hand == 0) ? pawn.AttackPos : pawn.OffhandPos;

		Actor hd = worldHand[hand];
		if (!hd)
		{
			Name nm = (hand == 0) ? 'RS_HandWorldMain' : 'RS_HandWorldOff';
			if (!Object.FindClass(nm)) return c;
			String cls = (hand == 0) ? "RS_HandWorldMain" : "RS_HandWorldOff";
			ThinkerIterator it = ThinkerIterator.Create(cls);
			hd = Actor(it.Next());
			worldHand[hand] = hd;
			if (!hd) return c;
		}

		// A hand wearing this rig's Quake mesh has no skeleton: its origin is the
		// palm, and asking for the bone prints "Could not find bone" every call.
		Vector3 hb = (0, 0, 0);
		let ps = ServiceIterator.Find("RS_HandPoseService").Next();
		if (!ps || ps.GetInt("pose.bones", "", hand, 0, null, 'RS_VRBody') != 0)
			hb = hd.TransformByNamedBone('HANDPALM_joint', (0, 0, 0));
		Vector3 pw, pf, pu;
		[pw, pf, pu] = hd.ModelPointToWorld(hb.x, hb.y, hb.z);
		// An unpublished pose loads identity, which puts the palm at the map origin.
		if ((pw - pawn.Pos).Length() <= 120) c = pw;
		return c;
	}

	// ANOTHER LANE HAS THIS HAND. A claimed subject (a magazine, a slide, a carried
	// barrel) or a grab target means the squeeze is theirs. A holster only wins
	// when there is nothing else the grip could mean -- RS_GrabHandler's own rule,
	// read off the engine fields so neither package names the other.
	// THE ACTOR DRAWING THIS HAND'S GUN. Found by what it IS DOING -- riding
	// this controller (FollowHandMode) and wearing a model -- never by a class
	// name, so the next gun system is found the same way this one is. The hand
	// mesh rides the controller too and is skipped. Once per stow, so a walk of
	// every actor is affordable here and nowhere else.
	private Actor findBodyOnHand(PlayerPawn pawn, int hand)
	{
		ThinkerIterator it = ThinkerIterator.Create("Actor");
		Actor a;
		while (a = Actor(it.Next()))
		{
			if (a == pawn || a.FollowHandMode != hand + 1) continue;
			if (a is 'RS_VRHolsterProp') continue;
			String cn = a.GetClassName();
			cn = cn.MakeLower();
			if (cn.IndexOf("hand") >= 0) continue;
			if (!level.GetActorModelClass(a)) continue;
			return a;
		}
		return null;
	}


	private static bool handFree(PlayerPawn pawn, int hand)
	{
		int  claim = (hand == 0) ? pawn.GripClaimMain : pawn.GripClaimOff;
		bool grab  = (hand == 0) ? pawn.GrabClaimMain : pawn.GrabClaimOff;
		return claim == GRIPSUBJ_None && !grab;
	}

	// Would a squeeze of this hand do something at this holster right now?
	private bool actionable(PlayerPawn pawn, int hand, int s)
	{
		if (drawSlot[1 - hand] == s) return false;   // the other hand is drawing it
		Weapon stored = contents[s - RSLOT_HOLSTER_0];
		return isEmpty(handWeapon(pawn, hand)) ? stored != null : stored == null;
	}

	// ---- the claim ------------------------------------------------------------
	//
	// HolsterClaim* tells the engine's grip arbiter this hand's grip means
	// "holster": it outranks stabilize and the shift layer, and RS_WorldHands
	// stands its grab down for it. Raised only where a squeeze would actually
	// act, so an empty hand resting at an empty holster keeps its grip's other
	// meanings. Written every tic -- a claim not restated has been withdrawn.
	private void updateClaims(PlayerPawn pawn, RS_VRBodyRig rig)
	{
		for (int hand = 0; hand < 2; ++hand)
		{
			int prev = claimSlot[hand];
			claimSlot[hand] = -1;

			if (drawSlot[hand] >= 0) { claimSlot[hand] = drawSlot[hand]; continue; }
			if (!handFree(pawn, hand)) continue;

			Vector3 hp = handPoint(pawn, hand);
			double r = isEmpty(handWeapon(pawn, hand)) ? reachDraw() : reachStore();

			// HYSTERESIS, and the held slot is tested FIRST with its widened radius.
			// Scanned in slot order instead, a neighbour's plain radius would steal
			// the claim from a holster the hand never left, and a hand resting on
			// a boundary would flip the grip's meaning many times a second.
			if (prev >= 0 && actionable(pawn, hand, prev)
				&& (hp - rig.SlotWorld(pawn, prev)).Length() < r * CLAIM_HYSTERESIS)
			{
				claimSlot[hand] = prev;
				continue;
			}

			double best = r;
			for (int s = RSLOT_HOLSTER_0; s <= RSLOT_HOLSTER_8; ++s)
			{
				if (!actionable(pawn, hand, s)) continue;
				double d = (hp - rig.SlotWorld(pawn, s)).Length();
				if (d < best) { best = d; claimSlot[hand] = s; }
			}
		}

		// TRACE: coming into and going out of a holster's reach.
		for (int hand = 0; hand < 2; ++hand)
		{
			if (claimSlot[hand] == tracedClaim[hand]) continue;
			if (claimSlot[hand] >= 0)
				dbg(String.Format("%s hand in reach of %s -- %s", handName(hand), slotLabel(claimSlot[hand]),
					contents[claimSlot[hand] - RSLOT_HOLSTER_0] ? "full: grip and pull to draw" : "empty: grip to put the gun away"));
			else
				dbg(String.Format("%s hand out of holster reach", handName(hand)));
			tracedClaim[hand] = claimSlot[hand];
		}

		bool m = claimSlot[0] >= 0;
		bool o = claimSlot[1] >= 0;

		// A light tap on FINDING one, never on leaving -- the cue that makes blind
		// reach possible.
		if (m && !pawn.HolsterClaimMain) level.VRHaptic(0, 0.35, 25.0);
		if (o && !pawn.HolsterClaimOff)  level.VRHaptic(1, 0.35, 25.0);

		pawn.HolsterClaimMain = m;
		pawn.HolsterClaimOff  = o;
	}

	// ---- the trace ------------------------------------------------------------
	//
	// Every step between "grip at a holster" and "gun in hand" can fail with no
	// sign: the grip owned by another system, the hand out of reach, a weapon
	// switch still in flight, let go before pulling far enough, the gun refused.
	// From inside a headset those all look the same -- nothing happens -- so
	// each one says its own name in the log. On by default; rs_body_holster_debug
	// 0 silences it.
	int tracedClaim[2];

	private bool dbgOn() { return cvb("rs_body_holster_debug", true); }
	private void dbg(String msg) { if (dbgOn()) Console.Printf("[HOLSTER] %s", msg); }
	private static String handName(int hand) { return hand == 0 ? "main" : "off"; }
	private static String slotLabel(int s)
	{
		// INSIDE THE FUNCTION, NOT AT CLASS SCOPE. A STATIC function cannot see a
		// class-level `static const` array -- it compiles to "Unknown identifier",
		// which took the whole load down on 2026-09-11. A function-local one is
		// fine and is what RS_WorldHands' rs_grab.zs has always used.
		static const String NAMES[] = {
			"hip left", "hip right", "head left", "head right",
			"pectoral left", "pectoral right", "hip left 2", "hip right 2", "pouch" };

		int i = s - RSLOT_HOLSTER_0;
		if (i < 0 || i >= NAMES.Size()) return "no holster";
		return "the " .. NAMES[i] .. " holster";
	}

	// RENAMED from rs_body_holster_seat_radius / _draw_radius (default 6) on
	// 2026-09-11 with a smaller default, because a saved ini outranks a CVARINFO
	// default forever: a new default under the old name would never arrive.
	private double reachStore() { return cvf("rs_body_holster_reach_store", 4.0); }
	private double reachDraw()  { return cvf("rs_body_holster_reach_draw",  4.0); }

	// A grip at no holster: say which holster was nearest and exactly why the
	// grip did nothing there.
	private void explainPress(PlayerPawn pawn, RS_VRBodyRig rig, int hand)
	{
		Vector3 hp = handPoint(pawn, hand);
		int near = -1;
		double nd = 1e9;
		for (int t = RSLOT_HOLSTER_0; t <= RSLOT_HOLSTER_8; ++t)
		{
			double d = (hp - rig.SlotWorld(pawn, t)).Length();
			if (d < nd) { nd = d; near = t; }
		}
		if (near < 0) return;

		Weapon held   = handWeapon(pawn, hand);
		bool   empty  = isEmpty(held);
		Weapon stored = contents[near - RSLOT_HOLSTER_0];
		double r = empty ? reachDraw() : reachStore();

		String why;
		if (!handFree(pawn, hand))
			why = String.Format("the grip belongs to something else (GripClaim %d, GrabClaim %d) -- a holster only takes a grip nothing else wants",
				hand == 0 ? pawn.GripClaimMain : pawn.GripClaimOff,
				(hand == 0 ? pawn.GrabClaimMain : pawn.GrabClaimOff) ? 1 : 0);
		else if (nd >= r)
			why = String.Format("out of reach -- %.1f away, reach is %.1f", nd, r);
		else if (empty && !stored)
			why = "empty hand at an empty holster -- nothing to draw";
		else if (!empty && stored)
			why = "full hand at a full holster -- nowhere to put it";
		else if (drawSlot[1 - hand] == near)
			why = "the other hand is drawing from it";
		else
			why = "no holster claimed this tic";

		String holding = "nothing";
		if (held) holding = held.GetClassName();
		dbg(String.Format("%s grip near %s did nothing: %s. Hand holds %s.",
			handName(hand), slotLabel(near), why, holding));
	}


	private void withdraw(PlayerPawn pawn)
	{
		pawn.HolsterClaimMain = false;
		pawn.HolsterClaimOff  = false;
		for (int h = 0; h < 2; ++h)
		{
			claimSlot[h] = -1;
			drawSlot[h]  = -1;
			// Keep tracking the button, so a grip held through a pause does not
			// read as a fresh press when this resumes.
			prevGrip[h] = (h == 0) ? pawn.GripHeldMain : pawn.GripHeldOff;
		}
	}

	// ---- switching ---------------------------------------------------------------

	// A HAND WITH A SWITCH IN FLIGHT IS NOT A TRUSTWORTHY WITNESS: ReadyWeapon still
	// names the gun being put away, and acting on it restarts a DropWeapon that is
	// already running. And PendingWeapon is ONE field both hands share, so with
	// instant switch off the other hand has to wait out the lower too.
	private bool switchSettled(PlayerPawn pawn, int hand)
	{
		if (pawn.player.PendingWeapon != WP_NOCHANGE) return false;
		int cd = swapCooldown();
		if (level.time - lastSwapTic[hand] < cd) return false;
		if (!instant() && level.time - lastSwapTic[1 - hand] < cd) return false;
		return true;
	}

	// MoveWeaponToHand under a transient CF_INSTANTWEAPSWITCH, so the lower and
	// raise resolve inside the call. exactInstance, because this deals in
	// INSTANCES -- a matched pair, a second fist of the class seated opposite --
	// and the class test turns those into a silent no-op hand switch.
	private void moveWeaponInstant(PlayerPawn pawn, Weapon w, int hand)
	{
		if (instant())
		{
			bool wasSet = (pawn.player.cheats & CF_INSTANTWEAPSWITCH) != 0;
			pawn.player.cheats |= CF_INSTANTWEAPSWITCH;
			pawn.MoveWeaponToHand(w, hand, true);
			if (!wasSet) pawn.player.cheats &= ~CF_INSTANTWEAPSWITCH;

			// Still pending after an instant switch means the weapon's own state
			// chain aborted mid-transition ("Recursive weapon state loop ...
			// aborted at depth 65"). Recover now rather than in two seconds.
			if (pawn.player.PendingWeapon != WP_NOCHANGE) pawn.BringUpWeapon();
		}
		else
		{
			pawn.MoveWeaponToHand(w, hand, true);
		}

		ourSwitchTic = (pawn.player.PendingWeapon != WP_NOCHANGE) ? Max(level.time, 1) : 0;
	}

	// The backstop for a switch of OURS that stopped moving. BringUpWeapon is the
	// engine's own recovery: it drives the psprite straight to the pending
	// weapon's ready state, routing round whatever chain broke. Held fire keeps a
	// switch pending legitimately, so it restarts the clock.
	private void recoverStuckSwitch(PlayerPawn pawn)
	{
		if (ourSwitchTic <= 0) return;
		if (pawn.player.PendingWeapon == WP_NOCHANGE) { ourSwitchTic = 0; return; }
		if (pawn.player.cmd.buttons & (BT_ATTACK | BT_ALTATTACK | BT_OFFHANDATTACK | BT_OFFHANDALTATTACK))
		{
			ourSwitchTic = Max(level.time, 1);
			return;
		}
		if (level.time - ourSwitchTic > STUCK_TICS)
		{
			pawn.BringUpWeapon();
			ourSwitchTic = 0;
		}
	}

	// A holstered gun is still in inventory, so the table drifts: an ammo pickup
	// re-arms it (CheckWeaponSwitch), the wheel selects it, it is dropped or
	// promoted into another class. GATED ON THE SWITCH HAVING SETTLED -- for the
	// ticks a gun spends lowering, ReadyWeapon is still the gun being put away,
	// and reconciling then empties every holster the tic after it was filled.
	private void reconcile(PlayerPawn pawn)
	{
		if (pawn.player.PendingWeapon != WP_NOCHANGE) return;
		if (level.time - Max(lastSwapTic[0], lastSwapTic[1]) < swapCooldown()) return;

		let rw = pawn.player.ReadyWeapon;
		let ow = pawn.player.OffhandWeapon;
		for (int i = 0; i < contents.Size(); ++i)
		{
			let w = contents[i];
			if (!w) continue;
			int s = RSLOT_HOLSTER_0 + i;
			if (drawSlot[0] == s || drawSlot[1] == s) continue;

			// POINTER equality: a same-class gun in the other hand is not this one.
			if (w == rw || w == ow || w.Owner != pawn || RS_EmptyHand.IsFist(w.GetClass()))
			{
				unflag(w);
				contents[i] = null;
			}
		}
	}

	// ---- store / draw ------------------------------------------------------------

	private void stow(PlayerPawn pawn, int hand, int s, Weapon held)
	{
		int ci = s - RSLOT_HOLSTER_0;

		// What is on screen in that hand this instant, for the prop's model lookup.
		let psp = pawn.player.FindPSprite(hand == 0 ? PSP_WEAPON : PSP_OFFHANDWEAPON);
		let p = propFor(ci, pawn);
		if (p && psp) p.SetHint(held, psp.Sprite, psp.Frame);
		// The actor drawing this gun, if it is drawn as a thing in the room.
		// Now, before the hand is emptied: its system tears it down after.
		Actor body = findBodyOnHand(pawn, hand);
		if (p) p.SetBody(held, body);
		dbg(body ? String.Format("%s is drawn by %s -- the holster will show that", held.GetClassName(), body.GetClassName())
				 : String.Format("%s has no separate body on the %s hand -- the holster uses the weapon's own model", held.GetClassName(), handName(hand)));

		let fist = RS_EmptyHand.FindFist(pawn, hand != 0);
		if (!fist)
		{
			// Refused loudly, and before anything is committed -- the old failure was
			// a store that filed the gun away and then never emptied the hand.
			if (!warnedNoFist)
			{
				warnedNoFist = true;
				Console.Printf("\cgRS_VRBody: nothing to empty the %s hand into -- not stowed", hand == 0 ? "main" : "off");
			}
			return;
		}

		// One weapon, one holster.
		for (int i = 0; i < contents.Size(); ++i)
			if (contents[i] == held) contents[i] = null;
		contents[ci] = held;

		moveWeaponInstant(pawn, fist, hand);

		// DID IT ACTUALLY LEAVE THE HAND? MoveWeaponToHand fails silently, and a gun
		// flagged bHolsterHidden while still in the hand can never fire again.
		if (handWeapon(pawn, hand) == held && pawn.player.PendingWeapon == WP_NOCHANGE)
		{
			contents[ci] = null;
			Console.Printf("\cgRS_VRBody: %s did not leave the %s hand -- not stowed",
				held.GetClassName(), hand == 0 ? "main" : "off");
			return;
		}

		// Out of the auto-switch and cycle paths while it is stowed: without these
		// an ammo pickup re-arms it, and weapnext lands on it.
		held.bNoAutoSwitchTo = true;
		held.bHolsterHidden  = true;

		lastSwapTic[hand] = level.time;
		level.VRHaptic(hand, 0.45, 30.0);
	}

	private void beginDraw(PlayerPawn pawn, RS_VRBodyRig rig, int hand, int s)
	{
		drawSlot[hand]    = s;
		drawAccum[hand]   = 0.0;
		drawLastRel[hand] = handPoint(pawn, hand) - rig.SlotWorld(pawn, s);
		level.VRHaptic(hand, 0.25, 15.0);
	}

	private void pullTick(PlayerPawn pawn, RS_VRBodyRig rig, int hand, bool gripNow)
	{
		int s = drawSlot[hand];
		Weapon w = contents[s - RSLOT_HOLSTER_0];

		// Let go early and nothing happened -- the prop goes back on the body.
		if (!gripNow || !w)
		{
			if (w) dbg(String.Format("%s hand let go after pulling %.1f of %.1f -- %s stays in %s",
				handName(hand), drawAccum[hand], cvf("rs_body_holster_pull_dist", 8.0), w.GetClassName(), slotLabel(s)));
			drawSlot[hand] = -1;
			return;
		}

		Vector3 rel = handPoint(pawn, hand) - rig.SlotWorld(pawn, s);
		drawAccum[hand]  += (rel - drawLastRel[hand]).Length();
		drawLastRel[hand] = rel;

		if (drawAccum[hand] < cvf("rs_body_holster_pull_dist", 8.0)) return;
		// Keep it in the hand until a switch in flight settles, rather than
		// starting a second one on top of it.
		if (pawn.player.PendingWeapon != WP_NOCHANGE) return;

		completeDraw(pawn, hand, s, w);
	}

	private void completeDraw(PlayerPawn pawn, int hand, int s, Weapon w)
	{
		int ci = s - RSLOT_HOLSTER_0;
		contents[ci]   = null;
		drawSlot[hand] = -1;

		// ANY HAND DRAWS FROM ANY HOLSTER. bOffhandWeapon is the engine's "which
		// hand last held me", and MoveWeaponToHand silently refuses a NOHANDSWITCH
		// weapon labelled for the other side -- so label it for the hand reaching.
		bool off = (hand == 1);
		Weapon other = handWeapon(pawn, 1 - hand);
		if (w.bOffhandWeapon != off)
		{
			w.bOffhandWeapon = off;
			if (w.SisterWeapon && w.SisterWeapon != other)
				w.SisterWeapon.bOffhandWeapon = off;
		}
		unflag(w);

		moveWeaponInstant(pawn, w, hand);

		// Refused anyway: back in the holster, nothing lost.
		if (instant() && handWeapon(pawn, hand) != w && pawn.player.PendingWeapon == WP_NOCHANGE)
		{
			contents[ci] = w;
			w.bNoAutoSwitchTo = true;
			w.bHolsterHidden  = true;
			Console.Printf("\cgRS_VRBody: %s would not go into the %s hand -- left in the holster",
				w.GetClassName(), hand == 0 ? "main" : "off");
			return;
		}

		lastSwapTic[hand] = level.time;
		if (props[ci]) props[ci].HideNow();
		level.VRHaptic(hand, 0.5, 35.0);
		dbg(String.Format("%s drawn into the %s hand", w.GetClassName(), handName(hand)));
	}

	private void handTick(PlayerPawn pawn, RS_VRBodyRig rig, int hand)
	{
		// The RAW button. GripContext latches once anything claims a subject, so
		// it cannot show a press edge.
		bool gripNow = (hand == 0) ? pawn.GripHeldMain : pawn.GripHeldOff;
		bool pressed = gripNow && !prevGrip[hand];
		prevGrip[hand] = gripNow;

		if (drawSlot[hand] >= 0) { pullTick(pawn, rig, hand, gripNow); return; }
		if (!pressed) return;

		// The holster the hand was in at the moment of the press, from this tic's
		// claim pass -- not a second proximity test that could disagree with it.
		int s = claimSlot[hand];
		if (s < 0) { if (dbgOn()) explainPress(pawn, rig, hand); return; }
		if (!switchSettled(pawn, hand))
		{
			dbg(String.Format("%s grip at %s ignored: %s", handName(hand), slotLabel(s),
				pawn.player.PendingWeapon != WP_NOCHANGE ? "a weapon switch is still in flight" : "still inside the swap cooldown"));
			return;
		}

		Weapon held   = handWeapon(pawn, hand);
		Weapon stored = contents[s - RSLOT_HOLSTER_0];
		if (!isEmpty(held) && !stored)
		{
			dbg(String.Format("%s hand puts %s into %s", handName(hand), held.GetClassName(), slotLabel(s)));
			stow(pawn, hand, s, held);
		}
		else if (isEmpty(held) && stored)
		{
			dbg(String.Format("%s hand takes hold of %s in %s -- keep gripping and pull %.1f to draw it",
				handName(hand), stored.GetClassName(), slotLabel(s), cvf("rs_body_holster_pull_dist", 8.0)));
			beginDraw(pawn, rig, hand, s);
		}
	}

	// ---- the props -----------------------------------------------------------------
	//
	// Oriented by the SLOT's own seat angles, so the gun sits the way its holster
	// does, then the model's own baked angles are cancelled out so every weapon
	// lands at the same intended pose. Centred by level.GetModelWorldOffset, which
	// replays the renderer's own matrix -- hand-derived versions of this were wrong
	// twice, because RenderModel negates pitch before rotating.
	private void updateProps(PlayerPawn pawn, RS_VRBodyRig rig)
	{
		double by = rig.BodyYaw();
		double fx = cos(by), fy = sin(by);
		double rx = sin(by), ry = -cos(by);
		double stretch = level.info ? level.info.pixelstretch : 1.0;

		// The renderer multiplies the baked offset by the placement scale too, so
		// the centring has to be told about it. Read, never written.
		double placeScale = cvf("rs_bp_stored_scale", 1.0);
		if (placeScale <= 0.0) placeScale = 1.0;

		for (int s = RSLOT_HOLSTER_0; s <= RSLOT_HOLSTER_8; ++s)
		{
			int ci = s - RSLOT_HOLSTER_0;
			let p = propFor(ci, pawn);
			if (!p) continue;

			p.ShowWeapon(contents[ci]);

			int pulledBy = (drawSlot[0] == s) ? 1 : ((drawSlot[1] == s) ? 2 : 0);
			if (pulledBy != 0)
			{
				// In the hand at headset rate. The world position follows too, so the
				// actor is never culled away from where it is drawn.
				p.SetFollowHand(pulledBy);
				p.SetOrigin(handPoint(pawn, pulledBy - 1), true);
				continue;
			}

			p.SetFollowHand(0);
			p.SolveScale();

			// INSIDE THE HOLSTER MESH when there is one (AActor::FollowActor). The
			// renderer seats the gun in the holster's own drawn frame every frame,
			// so it moves AND turns with the holster however the holster is moved:
			// the placement drag, the seat sliders, or a holster page's live
			// sliders with the menu open. The holster's seat and fit rotation are
			// already in that frame, so the gun's angles here are only its own
			// model's baked quirks cancelled out. With no holster mesh (style
			// "none") it hangs on the body directly, in world angles.
			Actor holster = rig.parts[s];
			bool riding = holster != null;

			double ang = (p.mirrored ? 180.0 : 0.0) - p.bakedAngleOffset;
			double pit = -p.bakedPitchOffset;
			double rol = -p.bakedRollOffset;
			if (!riding)
			{
				ang += by + rig.sYaw[s];
				pit += rig.sPitch[s];
				rol += rig.sRoll[s];
			}
			p.Angle = ang;
			p.Pitch = pit;
			p.Roll  = rol;

			// The model's baked offset, cancelled, so the gun sits ON the seat
			// rather than wherever its HUD-tuned MODELDEF Offset throws it.
			Vector3 cancel = (0, 0, 0);
			if (p.boundClass)
			{
				bool ok;
				double dx, dy, dz;
				double sc = p.DrawScale() * placeScale;
				[ok, dx, dy, dz] = level.GetModelWorldOffset(p.boundClass, p.sprite, p.frame, stretch,
					ang, pit, rol, sc, sc);
				if (ok) cancel = (-dx, -dy, -dz);
			}

			Vector3 at = rig.SlotWorld(pawn, s);
			if (riding)
			{
				p.FollowActor     = holster;
				p.FollowActorSlot = -1;
				p.FollowActorOfs  = cancel;   // the holster's frame: X forward, Y left, Z up
				p.FollowBodyMode  = 0;
				// Its own position only decides whether it is drawn at all.
				p.SetOrigin(at, true);
				continue;
			}

			p.FollowActor = null;
			at += cancel;
			p.SetOrigin(at, true);

			// And the same point in the body's frame for the renderer, which seats
			// it at draw rate -- the same channel the holster mesh rides.
			Vector3 rel = at - pawn.HmdPos;
			p.FollowBodyOfs  = (rel.X * fx + rel.Y * fy, rel.X * rx + rel.Y * ry, rel.Z);
			p.FollowBodyYaw  = by;
			p.FollowBodyMode = 2;
		}
	}

	// ---- lifecycle ---------------------------------------------------------------
	//
	// This handler is rebuilt per map; the WEAPONS travel with the player. A gun
	// that crosses an exit still flagged bHolsterHidden, with nothing on the new
	// map that remembers stowing it, is un-fireable and unreachable for the rest
	// of the run. So everything is handed back whenever the table stops knowing.

	private void releaseAll()
	{
		for (int i = 0; i < contents.Size(); ++i)
		{
			if (contents[i]) unflag(contents[i]);
			contents[i] = null;
		}
		drawSlot[0] = -1;
		drawSlot[1] = -1;
	}

	private void hideProps()
	{
		for (int i = 0; i < props.Size(); ++i)
		{
			if (!props[i]) continue;
			props[i].SetFollowHand(0);
			props[i].ShowWeapon(null);
		}
	}

	override void WorldTick()
	{
		PlayerPawn pawn = players[consoleplayer].mo;
		if (!pawn) return;
		ensure();

		let rig = RS_VRBodyRig(EventHandler.Find("RS_VRBodyRig"));

		// SWITCHED OFF IS EMPTIED, NOT FROZEN. A gun left in a holster nothing will
		// draw from is invisible and unselectable; hand them all back to inventory.
		if (!rig || !cvb("rs_body_holsters", true) || !cvb("rs_body_enabled", true))
		{
			withdraw(pawn);
			releaseAll();
			hideProps();
			return;
		}

		// The rig sizes its seat tables on its own first tick. Reading them before
		// that is an out-of-bounds abort, whatever order the handlers run in.
		if (rig.sFwd.Size() <= RSLOT_HOLSTER_8) { withdraw(pawn); return; }

		recoverStuckSwitch(pawn);
		reconcile(pawn);

		// Placement mode moves holsters; it does not use them. Dead hands do nothing.
		bool acting = pawn.health > 0 && pawn.player.playerstate == PST_LIVE && !rig.EditModeOn();
		if (acting)
		{
			updateClaims(pawn, rig);
			handTick(pawn, rig, 0);
			handTick(pawn, rig, 1);
		}
		else
		{
			withdraw(pawn);
		}

		updateProps(pawn, rig);
	}

	// THE PAWN TRAVELS, THIS HANDLER DOES NOT. The claim fields live on the pawn
	// and the engine never clears them, so they are withdrawn here too.
	override void WorldUnloaded(WorldEvent e)
	{
		let pawn = players[consoleplayer].mo;
		if (pawn) withdraw(pawn);
		releaseAll();
	}

	override void WorldLoaded(WorldEvent e)
	{
		// A save restores contents[] itself; those guns are legitimately stowed.
		if (e.IsSaveGame) return;

		// The backstop for anything WorldUnloaded could not reach: a gun stowed by
		// an older build, or on the first map of a session.
		let pawn = players[consoleplayer].mo;
		if (!pawn) return;
		for (Inventory item = pawn.Inv; item != null; item = item.Inv)
		{
			let w = Weapon(item);
			if (w && w.bHolsterHidden) unflag(w);
		}
	}

	override void PlayerDied(PlayerEvent e)
	{
		if (e.PlayerNumber != consoleplayer) return;
		let pawn = players[consoleplayer].mo;
		if (pawn) withdraw(pawn);
		releaseAll();
	}

	// A new pawn with a new inventory: the old props describe a corpse's guns.
	override void PlayerRespawned(PlayerEvent e)
	{
		if (e.PlayerNumber != consoleplayer) return;
		releaseAll();
		for (int i = 0; i < props.Size(); ++i)
		{
			if (props[i]) props[i].Destroy();
			props[i] = null;
		}
	}
}
