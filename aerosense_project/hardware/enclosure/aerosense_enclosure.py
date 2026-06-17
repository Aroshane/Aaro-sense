"""
AeroSense Sensor Payload Enclosure — FreeCAD Python Script
Run inside FreeCAD: Macro > Execute Macro > select this file
Outputs: aerosense_enclosure_base.stl + aerosense_enclosure_lid.stl

Enclosure specs:
  - 70 mm (L) × 55 mm (W) × 28 mm (H) total
  - Wall thickness: 2.0 mm
  - Bottom vents for airflow to sensors
  - Sealed lid with press-fit snap clips
  - 4× M3 brass insert bosses (for PCB mounting)
  - 1× boom mount tab on one side (for CF tube)
  - Print in PETG at 0.2 mm layer height, 4 perimeters
"""

import FreeCAD as App
import Part
import Mesh
import math
import os

doc = App.newDocument("AeroSense_Enclosure")

# ── Dimensions ────────────────────────────────────────────────────────────────
L     = 70.0   # outer length (mm)
W     = 55.0   # outer width
H_base= 22.0   # base height (holds PCB + sensors below)
H_lid =  8.0   # lid height
wall  =  2.0   # wall thickness
floor =  2.0   # floor thickness
pcb_standoff = 4.0  # PCB sits 4 mm above floor (on bosses)

inner_L = L - 2*wall
inner_W = W - 2*wall

# ── Helper: rounded box ───────────────────────────────────────────────────────
def rounded_box(length, width, height, radius=2.0):
    """Create a rounded-corner box centred at origin."""
    box = Part.makeBox(length, width, height,
                       App.Vector(-length/2, -width/2, 0))
    # fillet the 4 vertical edges
    edges = [e for e in box.Edges
             if abs(e.Length - height) < 0.1]
    if edges:
        try:
            box = box.makeFillet(radius, edges)
        except Exception:
            pass  # fillet failed silently — plain box still valid
    return box

# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — BASE
# ═════════════════════════════════════════════════════════════════════════════

# Outer shell
outer = rounded_box(L, W, H_base, radius=2.5)

# Inner cavity (subtracted from outer)
cavity = Part.makeBox(inner_L, inner_W, H_base - floor,
                      App.Vector(-inner_L/2, -inner_W/2, floor))

base_shell = outer.cut(cavity)

# ── Ventilation slots (bottom face) ─────────────────────────────────────────
# 6 slots, 4 mm wide × 20 mm long, arranged in 2 rows
vent_slots = []
slot_w = 4.0
slot_l = 20.0
slot_h = floor + 0.1  # punch through floor

for row, y_off in enumerate([-8.0, 8.0]):
    for col, x_off in enumerate([-18.0, 0.0, 18.0]):
        slot = Part.makeBox(slot_w, slot_l, slot_h,
                            App.Vector(x_off - slot_w/2,
                                       y_off - slot_l/2,
                                       -0.05))
        vent_slots.append(slot)

for s in vent_slots:
    base_shell = base_shell.cut(s)

# ── M3 Boss pillars (PCB mounting, 4 corners) ────────────────────────────────
boss_r_outer = 4.0
boss_r_inner = 1.6   # M3 brass insert bore
boss_h       = pcb_standoff + floor
boss_positions = [
    (-L/2 + wall + 5,  -W/2 + wall + 5),
    ( L/2 - wall - 5,  -W/2 + wall + 5),
    (-L/2 + wall + 5,   W/2 - wall - 5),
    ( L/2 - wall - 5,   W/2 - wall - 5),
]

for (bx, by) in boss_positions:
    outer_cyl = Part.makeCylinder(boss_r_outer, boss_h,
                                   App.Vector(bx, by, 0))
    inner_cyl = Part.makeCylinder(boss_r_inner, boss_h + 0.1,
                                   App.Vector(bx, by, -0.05))
    boss = outer_cyl.cut(inner_cyl)
    base_shell = base_shell.fuse(boss)

# ── Snap-fit clip receivers (on top rim, 2 per long side) ────────────────────
# Simple rectangular notches that lid clips snap into
clip_w = 6.0
clip_h = 3.0
clip_d = 1.5

clip_positions_x = [-15.0, 15.0]  # on long (L) sides

for cx in clip_positions_x:
    # Front wall notch
    notch_f = Part.makeBox(clip_w, clip_d + 0.1, clip_h,
                            App.Vector(cx - clip_w/2,
                                       -W/2 - 0.05,
                                       H_base - clip_h))
    base_shell = base_shell.cut(notch_f)
    # Rear wall notch
    notch_r = Part.makeBox(clip_w, clip_d + 0.1, clip_h,
                            App.Vector(cx - clip_w/2,
                                       W/2 - clip_d,
                                       H_base - clip_h))
    base_shell = base_shell.cut(notch_r)

# ── Cable exit hole (right side, for sensor harness) ─────────────────────────
cable_hole = Part.makeCylinder(5.0, wall + 0.2,
                                App.Vector(L/2 - wall - 0.1, 0,
                                           floor + pcb_standoff + 3),
                                App.Vector(1, 0, 0))
base_shell = base_shell.cut(cable_hole)

# ── Boom mount tab (left side, for CF tube) ──────────────────────────────────
tab_l = 12.0
tab_w = 10.0
tab_h = 8.0
tab = Part.makeBox(tab_l, tab_w, tab_h,
                   App.Vector(-L/2 - tab_l + wall,
                               -tab_w/2,
                               H_base/2 - tab_h/2))
# M10 tube hole through tab
tube_hole = Part.makeCylinder(5.1, tab_l + 0.2,
                               App.Vector(-L/2 - tab_l + wall - 0.1,
                                          0,
                                          H_base/2),
                               App.Vector(1, 0, 0))
tab = tab.cut(tube_hole)
base_shell = base_shell.fuse(tab)

# Add base to document
base_obj = doc.addObject("Part::Feature", "Enclosure_Base")
base_obj.Shape = base_shell

# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — LID
# ═════════════════════════════════════════════════════════════════════════════

lid_outer = rounded_box(L, W, H_lid, radius=2.5)

# Inner recess (lid sits over top rim of base, 1 mm overlap)
lid_inner_L = inner_L + 0.4   # slight clearance
lid_inner_W = inner_W + 0.4
lid_cavity  = Part.makeBox(lid_inner_L, lid_inner_W, H_lid,
                            App.Vector(-lid_inner_L/2,
                                       -lid_inner_W/2,
                                       wall))
lid_shell = lid_outer.cut(lid_cavity)

# ── Snap-fit clips on lid (match base notches) ────────────────────────────────
for cx in clip_positions_x:
    # Front clip
    clip_f = Part.makeBox(clip_w - 0.4, clip_d, clip_h - 0.5,
                           App.Vector(cx - (clip_w-0.4)/2,
                                      -W/2 + wall,
                                      0.5))
    lid_shell = lid_shell.fuse(clip_f)
    # Rear clip
    clip_r = Part.makeBox(clip_w - 0.4, clip_d, clip_h - 0.5,
                           App.Vector(cx - (clip_w-0.4)/2,
                                      W/2 - wall - clip_d,
                                      0.5))
    lid_shell = lid_shell.fuse(clip_r)

# ── GPS antenna window (clear PETG patch over GPS module) ────────────────────
# Just a thinned-out area (0.8 mm) for GPS signal — don't cut through
# Thin patch is printed with 0 top/bottom layers for transparency/RF transparency
# (handled in slicer, not in geometry)

lid_obj = doc.addObject("Part::Feature", "Enclosure_Lid")
lid_obj.Shape = lid_shell

# Move lid above base for visibility
lid_obj.Placement.Base.z = H_base + 5

# ═════════════════════════════════════════════════════════════════════════════
# EXPORT STL FILES
# ═════════════════════════════════════════════════════════════════════════════

doc.recompute()

out_dir = os.path.expanduser("~/aerosense_enclosure/")
os.makedirs(out_dir, exist_ok=True)

base_path = out_dir + "aerosense_enclosure_base.stl"
lid_path  = out_dir + "aerosense_enclosure_lid.stl"

Mesh.export([base_obj], base_path)
Mesh.export([lid_obj],  lid_path)

print(f"✅ Exported base STL: {base_path}")
print(f"✅ Exported lid  STL: {lid_path}")
print()
print("Print settings (both parts):")
print("  Material  : PETG")
print("  Layer h   : 0.20 mm")
print("  Infill    : 25% gyroid")
print("  Perimeters: 4")
print("  Supports  : Base needs supports for cable hole; Lid is support-free")
print("  Bed temp  : 70°C | Nozzle: 240°C")
print()
print("Post-print:")
print("  1. Press M3 brass inserts into boss holes with soldering iron (200°C)")
print("  2. Test PCB fit before final assembly")
print("  3. Apply thin bead of silicone to lid rim for weather sealing")
