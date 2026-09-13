// ============================================================================
// A HOLSTER'S PAGE LIGHTS THAT HOLSTER.
//
// Opening "Holster 3" sets rs_body_hl3 to 1; leaving it sets it back to 0. The
// holster's highlight copy (body_rig.zs, syncHolsterHighlights) names that cvar
// as its VisibleCVar, which the RENDERER reads every frame it draws. That is
// the only reason this can work: while this menu is open the game is paused and
// no play-side script runs -- which is also why the in-reach glow cannot do it.
//
// One class for all nine pages. The holster ID is the last character of the
// page's own MENUDEF name (RS_VRBodyHol0 .. RS_VRBodyHol8), so a page cannot
// light the wrong holster by being given the wrong number.
// ============================================================================

class RS_HolsterPageMenu : OptionMenu
{
    // Name literals, one per holster ID -- no text-to-name conversion anywhere.
    static const Name GATES[] = {
        'rs_body_hl0', 'rs_body_hl1', 'rs_body_hl2', 'rs_body_hl3', 'rs_body_hl4',
        'rs_body_hl5', 'rs_body_hl6', 'rs_body_hl7', 'rs_body_hl8' };

    private int id;

    override void Init(Menu parent, OptionMenuDescriptor desc)
    {
        Super.Init(parent, desc);
        String nm = desc.mMenuName;
        id = nm.Mid(nm.Length() - 1).ToInt();
        if (id < 0 || id >= GATES.Size()) id = -1;
        SetGate(1.0);
    }

    // Leaving the page -- back out, or the whole menu closing -- destroys it.
    override void OnDestroy()
    {
        SetGate(0.0);
        Super.OnDestroy();
    }

    private void SetGate(double v)
    {
        if (id < 0) return;
        let c = CVar.FindCVar(GATES[id]);
        if (c) c.SetFloat(v);
    }
}
