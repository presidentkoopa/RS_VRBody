# VR Body tools

The scripts used for the VR Body, the HUD panels and the hands, copied from the working scratch folder on
2026-09-14. Scripts only: their outputs are ignored (see .gitignore).

- `body/` -- arm cutting and rigging, IK and body-yaw mockups, shoulder measurements, tint, the marine
  model checks, the reach-marker menu lint.
- `fingers/` -- `hand_iqm.py` (reads our 22-joint hand IQM), the Pistolet grip measurements, the
  finger-contact mockup (`solve.py`) and `render.py` (Blender 5.1: `blender -b --python render.py -- SCENE.json`).
- `ermac/` -- Ermac's glove onto our hand: export, align, weight transfer and IQM write (`build_ermac_iqm.py`),
  his hand2 poses fitted to our skeleton (`fit_ermac_poses.py`), the contact sheet, and
  `build_left_poses.py` (the RS hand with the same pose frames).
- `lib/` -- copies of the shared tools these import. The originals live in `E:/DOOMWork/tools`, which the
  scripts still put on their path.

Most scripts still read from and write beside their own folder, and name absolute source paths
(`E:/DOOMWork/_old/...` for Ermac's hand2.md3). Ermac's (iAmErmac) glove and poses come from Rusted Legacy (MIT).
