// ==========================================================================
// RS_VRBody -- THE MIRROR.
//
// You cannot see your own body. You are inside its head: the legs are under
// you, the back is behind you, and craning your neck to check whether a knee
// bent is both awkward and a bad way to judge anything. Every leg, lean and
// finger feature in this package has been shipped blind for exactly that
// reason.
//
// So: a panel you walk up to and look at, showing you from the front.
//
// WHY NOT A THIRD-PERSON CAMERA. GZDoom already has chasecam (chase_dist,
// r_utility.cpp), and nothing in the VR path handles it. Its offset rides your
// VIEW DIRECTION, so turning your head swings the camera through an arc rather
// than pivoting at your neck -- your inner ear reports a head turn and your eyes
// report a sideways sweep. That mismatch is what makes people ill, and it is the
// same rule that got the recoil view jolt cancelled: NOTHING WE COMPUTE MAY MOVE
// THE CAMERA. A mirror moves nothing at all. Your head still drives your view.
//
// IT IS A MONITOR, NOT A REFLECTION. A true mirror would need the viewpoint
// reflected through the panel's plane; this one simply stands where the panel is
// and looks back at you, and it TRACKS you so you stay in frame while you walk,
// crouch and lean. For checking a body that is strictly better than a reflection,
// which would lose you out of shot the moment you stepped aside.
//
// ON DEMAND ONLY. A camera texture renders the entire scene a second time, and
// in VR the scene is already being drawn twice. This is a tool you switch on to
// look at something and switch off again -- never something left running.
// ==========================================================================

// The viewpoint. Draws nothing itself; it exists to be a camera.
class RS_VRMirrorCam : Actor
{
	Default
	{
		+NOINTERACTION;
		+NOBLOCKMAP;
		+NOGRAVITY;
		+INVISIBLE;
		RenderStyle "None";
		Radius 1;
		Height 1;
	}
}

// The panel itself: one quad wearing the camera texture.
class RS_VRMirror : Actor
{
	Default
	{
		+NOINTERACTION;
		+NOBLOCKMAP;
		+NOGRAVITY;
		+BRIGHT;
		Radius 1;
		Height 1;
	}
	States
	{
	Spawn:
		TRSO A -1;
		Stop;
	}
}
