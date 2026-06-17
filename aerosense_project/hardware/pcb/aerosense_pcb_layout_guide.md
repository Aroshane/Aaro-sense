# AeroSense Carrier Board — PCB Layout Guide
Version 1.0 | 2-layer FR4 | JLCPCB fabrication

---

## Board Specifications

| Parameter         | Value                        |
|-------------------|------------------------------|
| Board size        | 65 mm × 50 mm                |
| Layers            | 2 (Top Cu + Bottom Cu)       |
| Substrate         | FR4, 1.6 mm thickness        |
| Copper weight     | 1 oz (35 µm) both layers     |
| Min trace width   | 0.2 mm (signal), 0.5 mm (power) |
| Min clearance     | 0.2 mm                       |
| Via drill         | 0.3 mm min, 0.6 mm annular   |
| Surface finish    | HASL lead-free               |
| Solder mask       | Green (both sides)           |
| Silkscreen        | White (top side)             |
| Target weight     | ≤ 8 g bare PCB               |

---

## Layer Stack

```
Top silkscreen   — component labels, board outline
Top solder mask  — openings over pads
Top copper (F.Cu)— signal routing + component pads
Core FR4 1.6mm
Bottom copper (B.Cu) — GND pour (full flood)
Bottom solder mask
Bottom silkscreen — (optional: mounting info)
```

---

## Component Placement Strategy

### Top-left quadrant — Power section
- J1 (JST power input) at board edge for easy cable routing
- U1 (AMS1117-3.3) adjacent to J1
- C1 (10µF) close to U1 input pin (<3 mm)
- C2 (22µF) close to U1 output pin (<3 mm)
- LED1 + R4 near board edge for visibility

### Centre — RPi Zero 2W GPIO header
- J2 (40-pin header) centred on board
- Leave 3 mm clearance on all sides for Pi overhang
- Pi will overhang the top edge — account for SDS011 fan clearance

### Right side — Sensor connectors
- J3 (SDS011) — top-right, facing outward (cable exits right)
- J4 (BME680) — below J3
- J5 (ADS1115) — below J4
- J6 (GPS) — bottom-right
- J7 (LoRa) — bottom-right, near SPI GPIO pins

### Pull-up resistors
- R1, R2 (I2C pull-ups) — between J2 GPIO2/3 pins and J4/J5 connectors
- R3 (LoRa reset) — between J2 GPIO25 and J7

### ESD protection
- D1 — inline on SDS011 UART traces (between J2 and J3)
- D2 — inline on GPS UART traces (between J2 and J6)

---

## Routing Rules

### Power traces (J1 → U1 → sensors)
- 5V rail: 1.0 mm trace minimum (up to 1.5 A load)
- 3.3V rail: 0.8 mm trace (up to 800 mA)
- GND: 1.0 mm trace or use copper pour (preferred)

### Signal traces
- UART lines (SDS011, GPS): 0.3 mm, keep short (<50 mm)
- I2C lines (SDA, SCL): 0.3 mm, route together, equal length
- SPI lines (LoRa): 0.3 mm, route away from UART traces
- Keep analog (MQ-135 AOUT) trace away from SPI clock lines

### Critical routing rules
1. Do NOT route SPI signals parallel to I2C for more than 10 mm
2. Place a ground via stitch row between UART and SPI zones
3. Keep 2 mm clearance between 5V power traces and signal traces
4. Pour GND flood on B.Cu — connect to GND net, 0.3 mm clearance
5. Add 4× via stitching around board perimeter (every 10 mm)

---

## Mounting Holes

Four M3 holes, one at each corner:
- H1: (3, 3) mm from board origin
- H2: (62, 3) mm
- H3: (3, 47) mm
- H4: (62, 47) mm

Use MountingHole_3.2mm_M3_Pad_Via footprint (connected to GND pour).
These align with the 3D-printed enclosure M3 brass insert positions.

---

## Design Rule Check (DRC) Targets (JLCPCB standard)

| Rule                  | Value      |
|-----------------------|------------|
| Min trace width       | 0.127 mm   |
| Min clearance         | 0.127 mm   |
| Min via drill         | 0.3 mm     |
| Min via annular ring  | 0.13 mm    |
| Min hole size (PTH)   | 0.2 mm     |
| Min silkscreen width  | 0.153 mm   |
| Copper to board edge  | 0.3 mm min |

Run DRC in KiCad (Inspect → Design Rules Checker) before generating Gerbers.
Target: 0 errors, 0 warnings.

---

## Gerber Export Settings (for JLCPCB)

File layers to export:
- F.Cu.gbr       (Top copper)
- B.Cu.gbr       (Bottom copper)
- F.Mask.gbr     (Top solder mask)
- B.Mask.gbr     (Bottom solder mask)
- F.Silkscreen.gbr
- Edge.Cuts.gbr  (Board outline)
- drill.drl      (Excellon drill file)

Export settings:
- Format: Gerber X2
- Drill origin: Absolute
- Subtract soldermask from silkscreen: YES
- Use drill/place file origin: YES

ZIP all files and upload to jlcpcb.com → 2-layer order.
Estimated cost: ~$2 USD for 5 boards (standard 2-layer, green).

---

## BOM for PCB Assembly

| Ref  | Value       | Footprint                    | Qty |
|------|-------------|------------------------------|-----|
| U1   | AMS1117-3.3 | SOT-223-3_TabPin2            | 1   |
| C1   | 10µF 10V    | C_0805_2012Metric            | 1   |
| C2   | 22µF 10V    | C_0805_2012Metric            | 1   |
| R1   | 4.7kΩ       | R_0402_1005Metric            | 1   |
| R2   | 4.7kΩ       | R_0402_1005Metric            | 1   |
| R3   | 10kΩ        | R_0402_1005Metric            | 1   |
| R4   | 1kΩ         | R_0402_1005Metric            | 1   |
| D1   | PRTR5V0U2X  | SOT-363_SC-70-6              | 1   |
| D2   | PRTR5V0U2X  | SOT-363_SC-70-6              | 1   |
| LED1 | Green LED   | LED_0402_1005Metric          | 1   |
| J1   | JST-XH 2pin | JST_XH_B2B-XH-A_Vertical     | 1   |
| J2   | 40-pin hdr  | PinHeader_2x20_P2.54mm_Vert  | 1   |
| J3   | JST-XH 4pin | JST_XH_B4B-XH-A_Vertical     | 1   |
| J4   | JST-XH 4pin | JST_XH_B4B-XH-A_Vertical     | 1   |
| J5   | JST-XH 5pin | JST_XH_B5B-XH-A_Vertical     | 1   |
| J6   | JST-XH 4pin | JST_XH_B4B-XH-A_Vertical     | 1   |
| J7   | JST-XH 8pin | JST_XH_B8B-XH-A_Vertical     | 1   |
| H1-4 | M3 hole    | MountingHole_3.2mm_M3_Pad    | 4   |
