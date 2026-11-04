# Wrist Camera Hardware Files

See the [hardware assembly guide](../docs/hardware-assembly-zh.md) for assembly instructions. This directory contains printable parts, editable models, and all scenes and meshes needed to generate the assembly illustrations. No CAD files outside this repository are required.

## Files

| File | Purpose | Units |
| --- | --- | --- |
| [cad/recessed_camera_plate.stl](cad/recessed_camera_plate.stl) | Print the one-piece wrist mount, including the camera plate and board holder | mm |
| [cad/recessed_camera_plate.step](cad/recessed_camera_plate.step) | Edit the mount's solid geometry | mm |
| [simulation/assembled.xml](simulation/assembled.xml) | MuJoCo scene of the completed assembly | m |
| [simulation/exploded.xml](simulation/exploded.xml) | Exploded scene showing how the components fit together | m |
| [simulation/meshes/](simulation/meshes/) | Visualization meshes for the wrist, gripper, and camera PCB; not for printing | m |
| [simulation/sources.json](simulation/sources.json) | Mesh sources, upstream versions, and SHA-256 hashes | — |
| [tools/render_assembly.py](tools/render_assembly.py) | Regenerate annotated assembly illustrations | — |

The STL bounding box is **155.15 × 91.20 × 66.63 mm**, with 17,428 triangles. SHA-256:

```text
3066b0534c5af87d29cd663e8b8c51f703b38d5f54dba6f3886f1b89e5cc6539
```

The STEP file contains editable solid geometry without a parametric modeling history. The MuJoCo scenes reference the same printable STL through a relative path and convert millimeters to meters with `scale=".001 .001 .001"`. After modifying the STL, render the scenes again to update the mount geometry in the illustrations.

## Viewing and Rendering the Assembly

Create a separate environment for the hardware tools from the repository root:

```bash
python3 -m venv hardware/.venv
hardware/.venv/bin/python -m pip install -r hardware/requirements-render.txt
```

On a graphical desktop, open either scene to rotate and zoom the view:

```bash
hardware/.venv/bin/python -m mujoco.viewer --mjcf=hardware/simulation/exploded.xml
hardware/.venv/bin/python -m mujoco.viewer --mjcf=hardware/simulation/assembled.xml
```

Render the documentation illustrations on Linux:

```bash
MUJOCO_GL=egl hardware/.venv/bin/python hardware/tools/render_assembly.py
```

A working EGL / OpenGL environment is required. The script uses `fc-match` to locate a Noto Sans CJK font; you can also set `WRIST_CAM_FONT` to a local font file. If EGL is unavailable, install OSMesa and set `MUJOCO_GL=osmesa`.

The outputs are the [assembled view](../docs/assets/hardware/assembled.png) and [exploded view](../docs/assets/hardware/exploded.png). Annotation positions match the script's fixed camera view; update them if you change the view.

## Model Notes

- The mount uses the original printable STL geometry. The camera, board, and fasteners are simplified visualization models. In the physical assembly, the board is secured in its holder with small spots of hot-melt glue; the glue and ribbon cable are not modeled.
- The exploded view separates parts by translation to explain their relationships; it is not a robot motion trajectory. The scenes illustrate geometry and have not been used to validate assembly dynamics or load capacity.
- Fastener models show location and axis only; choose lengths based on the physical parts. The assembled view does not establish collision clearance. Verify that the original gripper and wrist mounting faces sit flush during installation.

## Third-Party Model Sources

The eight wrist and gripper visualization meshes have been checked individually against the upstream [UFACTORY xarm_ros](https://github.com/xArm-Developer/xarm_ros) files and match their contents. File names, pinned upstream commits, and hashes are recorded in [sources.json](simulation/sources.json). The original license is retained in [UFACTORY BSD 3-Clause](licenses/UFACTORY-BSD-3-Clause.txt). It applies to those third-party meshes and does not replace the license notices for other project files.
