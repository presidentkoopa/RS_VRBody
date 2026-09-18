// ============================================================================
// EMPTY HANDS.
//
// What "nothing in this hand" means to the engine: the player's fist, seated in
// that hand's weapon slot. The holsters need it to empty a hand they have just
// taken a gun out of.
//
// A COPY of RS_WorldHands' RS_HandFist (rs_fist.zs), same logic, under its own
// class name so the two load side by side. Copied rather than called because a
// hard reference to a class in another pk3 is fatal and global when that pk3 is
// absent or loads later (see handSlotIsForeign in body_rig.zs) -- and the body
// suite has to load on its own. When the hands merge into this package, the two
// become one and this copy goes away.
// ============================================================================

class RS_EmptyHand play
{
	// A Fist subclass, anything with "fist" in its name, or whatever replaces Fist
	// in DECORATE -- Brutal Doom's melee is "Melee_Attacks : ... Replaces Fist",
	// which the name test alone never finds.
	static bool IsFist(class<Actor> cls)
	{
		if (cls == null)
			return false;
		if (cls is 'Fist')
			return true;
		string cn = cls.GetClassName();
		cn = cn.MakeLower();
		if (cn.IndexOf("fist") >= 0)
			return true;

		class<Actor> repl = Actor.GetReplacement((class<Actor>)("Fist"));
		return repl != null && repl == cls;
	}

	// A fist that can go into THIS hand. MoveWeaponToHand's first guard is
	//     if (weap.bNoHandSwitch && weap.bOffhandWeapon != (hand == 1)) return;
	// and fists carry +WEAPON.NOHANDSWITCH, so a fist labelled for the other side
	// is refused SILENTLY -- the "offhand never lets go of the gun" bug.
	static Weapon FindFist(PlayerPawn pawn, bool offhand)
	{
		Weapon spare = null;
		Weapon otherHandWeapon = offhand ? pawn.player.ReadyWeapon : pawn.player.OffhandWeapon;
		class<Actor> fistClass = null;

		for (Inventory item = pawn.Inv; item != null; item = item.Inv)
		{
			let w = Weapon(item);
			if (w == null || !IsFist(w.GetClass()))
				continue;

			if (w.bOffhandWeapon == offhand)
				return w;

			fistClass = w.GetClass();
			// Never the one seated in the other hand -- that instance is busy.
			if (spare == null && w != otherHandWeapon)
				spare = w;
		}

		if (spare != null)
		{
			// bOffhandWeapon is the engine's live "which hand last held me", not a
			// fixed label (MoveWeaponToHand writes it every seat), so a fist never
			// yet drawn reads false for both. Label it for where it is going.
			spare.bOffhandWeapon = offhand;
			if (spare.SisterWeapon != null && spare.SisterWeapon != otherHandWeapon)
				spare.SisterWeapon.bOffhandWeapon = offhand;
			return spare;
		}

		// ONE FIST FOR TWO HANDS (Brutal Doom's classic set, confirmed in headset
		// 2026-08-28): clone it. Spawn + AttachToOwner, not GiveInventory -- giving
		// a class already owned tops up the existing instance and never produces a
		// second one a hand could hold.
		if (fistClass != null)
		{
			let fresh = Weapon(Actor.Spawn(fistClass, pawn.Pos, NO_REPLACE));
			if (fresh != null)
			{
				fresh.AttachToOwner(pawn);
				fresh.bOffhandWeapon = offhand;
				// Not sister-linked to the other hand's fist: SisterWeapon means the
				// same hand's other form, and a cross-hand link relabels the other
				// hand on every raise.
				return fresh;
			}
			Console.Printf("\cgRS_VRBody: recognised %s as a fist but could not spawn a second one",
				fistClass.GetClassName());
		}

		Console.Printf("\cgRS_VRBody: no fist-class weapon in inventory for the %s hand",
			offhand ? "off" : "main");
		return null;
	}
}
