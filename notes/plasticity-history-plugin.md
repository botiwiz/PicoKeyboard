# Plasticity "editable history" plugin — conversation backup (2026-10-30)

Request: a Plasticity plugin that gives Fusion 360-style editable, non-destructive timeline steps.

Findings:
- No public plugin SDK or scripting API for Plasticity was found. Bridges exist only for Blender and Cinema 4D.
- Plasticity is a direct modeler by design. Its FAQ contrasts it with feature-tree, history-based CAD.
- 2026.2 adds a Studio-only Constraint System. Constraints are not saved with the file yet.
- A history timeline needs hooks into every command and kernel replay. An outside plugin can't add that.

Options discussed:
1. Use Plasticity 2026.2 constraints and keep many saved versions (manual "history").
2. Blender bridge plus a non-destructive modifier stack or Geometry Nodes for the editable parts.
3. Use a parametric tool for the parts that need a history: Fusion, Onshape, FreeCAD, Shapr3D (has history), or CadQuery/build123d scripts.
4. Ask the Plasticity developers for this as a feature.

Status: waiting for the user to choose a direction.

---
# QuadRemesher → Blender port request (2026-11-01)

- Inspected QuadRemesher_1.0.1_Maya2022_Win.zip. The remeshing algorithm is in the closed binaries `xremesh.exe` / `xremeshlib.dll`, gated by a license manager. `QuadRemesher.py` is only a Maya UI wrapper.
- EULA §2 forbids reverse engineering, translating, modifying, and creating derivative works. So the package was not ported.
- Exoside sells an official Blender version of QuadRemesher.
- Offered instead: an original Blender retopo addon using QuadriFlow (built into Blender) and/or Instant Meshes (BSD).

Status: waiting for the user to choose.
