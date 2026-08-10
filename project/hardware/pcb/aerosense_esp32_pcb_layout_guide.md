# AeroSense ESP32-S3 Carrier Board — PCB Layout Guide
Version 2.0 | 2-layer FR4 | JLCPCB fabrication

This guide details the specifications, routing constraints, component placement, and manufacturing guidelines for the **AeroSense ESP32-S3 Carrier Board**. This board acts as a companion hub routing power and signals between the ESP32-S3 DevKit, environmental sensors, Pixhawk autopilot, and LoRa telemetry module.

---

## Board Specifications

| Parameter         | Value                        | Note |
|-------------------|------------------------------|------|
| Board size        | 65 mm × 50 mm                | Fits standard enclosure mounting holes |
| Layers            | 2 (Top Cu + Bottom Cu)       | Cost-effective standard |
| Substrate         | FR4, 1.6 mm thickness        | High rigidity for flight vibrations |
| Copper weight     | 1 oz (35 µm) both layers     | Standard weight |
| Min trace width   | 0.25 mm (signal), 0.8 mm (power) | Ensures reliable signal and power |
| Min clearance     | 0.25 mm                      | standard clearance |
| Via drill         | 0.3 mm min, 0.6 mm annular   | Standard vias |
| Surface finish    | HASL lead-free               | Easy soldering and eco-friendly |
| Solder mask       | Matte Green (both sides)     | Dual-side masking |
| Silkscreen        | White (top side only)        | Easy component alignment and labeling |
| Target weight     | ≤ 8 g bare PCB               | Minimal contribution to payload weight |

---

## Layer Stack

```
Top silkscreen    — Component labels, pin numbers, board boundaries
Top solder mask   — Openings over component pads
Top copper (F.Cu) — Component pads, SPI/I2C/UART trace routing, 3.3V power rails
Core FR4 1.6mm    — Isolating substrate
Bottom copper (B.Cu) — Solid Ground (GND) flood, minimal signal routing
Bottom solder mask — Bottom protective layer
```

---

## Component Placement Strategy

### 1. Left Section — Power & Analog Inputs
*   **J1 (Power Input):** Place a 2-pin vertical JST-XH connector at the bottom-left edge for easy BEC 5V input connection.
*   **Resistor Divider (R1, R2):** Place the 1.8 kΩ ($R_{top}$) and 3.3 kΩ ($R_{bottom}$) resistors close to the MQ-135 connector to minimize analog trace length to the ESP32-S3.
*   **Decoupling Capacitors (C1, C2):** Place a 10 µF electrolytic or SMD capacitor near J1 and a 100 nF ceramic capacitor near the ESP32-S3 5V pin.

### 2. Center — ESP32-S3 DevKit Footprint
*   **J2 (ESP32-S3 DevKit Footprint):** Two rows of 22-pin female headers (2.54mm pitch) separated by a width of **0.9 inches (22.86mm)** to allow the DevKit to plug in directly.
*   Orient the DevKit with the USB-C ports facing the top edge for convenient programming and logging access.

### 3. Right Section — Sensor & Telemetry Interfaces
Use vertical JST-XH connectors for reliability under high-vibration quadcopter environments:
*   **J3 (BME280 Climate Sensor):** 4-pin JST-XH (VCC 3.3V, GND, GPIO22 SCL, GPIO21 SDA) placed at the center-right.
*   **J4 (PMS5003 Particle Sensor):** 4-pin JST-XH (VCC 5V, GND, GPIO26 RX2, GPIO27 TX2) placed at the top-right.
*   **J5 (MQ-135 Gas Sensor):** 3-pin or 4-pin JST-XH (VCC 5V, GND, AO Out) placed at the bottom-left, routing AO through the resistor divider.
*   **J6 (Autopilot MAVLink Feed):** 3-pin JST-XH (GPIO33 RX1, GPIO25 TX1, GND) placed at the bottom-right for flight controller connection.
*   **J7 (LoRa SX1276 Ra-02):** 8-pin female header or JST-XH connector placed at the right edge, matching SPI pin configurations.
*   **J8 (MicroSD Card SPI, Optional):** 6-pin female header placed next to J7 for local data caching.

---

## Pinout and Schematic Mapping

```
                 +-------------------+
                 |     ESP32-S3      |
                 |      DevKit       |
                 +-------------------+
                   | 3.3V   GND |
                   | GPIO21 GPIO22 | ---> I2C Bus (BME280 + 4.7k Pull-ups)
                   | GPIO26 GPIO27 | ---> UART2 (PMS5003 Laser Particle)
                   | GPIO33 GPIO25 | ---> UART1 (Pixhawk MAVLink Telemetry)
                   | GPIO34        | <--- Analog IN (MQ-135 Divider Junction)
                   | SPI Pins      | ---> SPI Bus (LoRa Ra-02 & SD Card CS pins)
                 +-------------------+
```

### 1. I2C Bus Pull-Ups
Include pads for two **4.7 kΩ pull-up resistors (R3, R4)** between the SDA (GPIO21) / SCL (GPIO22) lines and the 3.3V rail.

### 2. MQ-135 Analog Resistor Divider Configuration
To step down the MQ-135 5.0V output voltage to a safe 3.23V maximum for ESP32 ADC pin GPIO34:
```
J5 (MQ-135 AO) ----> [ R1: 1.8 kΩ ] ----> ESP32 GPIO34 (ADC1_CH6)
                                     |
                                 [ R2: 3.3 kΩ ]
                                     |
                                    GND
```

### 3. SPI Bus Pin Sharing
The SPI Bus is shared between the LoRa SX1276 and the MicroSD Card Module:
*   **SCK:** GPIO18
*   **MISO:** GPIO19
*   **MOSI:** GPIO23
*   **LoRa CS (NSS):** GPIO5
*   **SD Card CS:** GPIO15

---

## Routing & Electrical Integrity Rules

1.  **Power Rails:** Route the 5V BEC output and 3.3V regulator/out tracks using at least **0.8 mm** to **1.0 mm** trace widths.
2.  **Signal Traces:** Use **0.25 mm** widths for SPI, I2C, and UART. Keep signal paths as short as possible (< 60 mm).
3.  **Cross-talk Prevention:** Do not run high-frequency SPI lines (10 MHz SCK) parallel to the sensitive MQ-135 analog trace (GPIO34) or I2C lines. Maintain a clearance of at least **1.5 mm** or run a ground guard trace between them.
4.  **Ground Plane:** Devote the entire bottom layer (B.Cu) to a solid ground pour (GND flood). Avoid running signal traces on the bottom layer. If required, route them in short vertical segments and return immediately to the top layer.
5.  **Via Stitching:** Add GND via stitching (0.3mm drill, 0.6mm annular) around the board perimeter every **10 mm** to tie the top and bottom ground fills, minimizing EMI.

---

## Mounting Holes

Four standard M3 mounting holes are located at the board corners, exactly matching the FreeCAD enclosure bosses (spaced 56.0 mm on the X-axis and 41.0 mm on the Y-axis):
*   **H1 (Bottom-Left):** (4.5 mm, 4.5 mm) from bottom-left origin
*   **H2 (Bottom-Right):** (60.5 mm, 4.5 mm)
*   **H3 (Top-Left):** (4.5 mm, 45.5 mm)
*   **H4 (Top-Right):** (60.5 mm, 45.5 mm)

Use `MountingHole_3.2mm_M3_Pad` footprint with isolated annular copper connected to the bottom GND pour to provide mechanical and electrical shielding.

---

## Design Rule Check (DRC) Settings (JLCPCB Standard)

Configure KiCad's DRC parameters before exporting Gerber files:
*   **Minimum Trace Clearance:** 0.2 mm
*   **Minimum Track Width:** 0.2 mm
*   **Minimum Via Drill Size:** 0.3 mm
*   **Minimum Via Outer Diameter:** 0.6 mm
*   **Copper to Edge Clearance:** 0.3 mm min

Ensure **0 DRC errors** and **0 warnings** before production.

---

## Gerber Export & Ordering

1.  **Layers to Export:**
    *   `F.Cu.gbr` (Top copper)
    *   `B.Cu.gbr` (Bottom copper)
    *   `F.Mask.gbr` (Top solder mask)
    *   `B.Mask.gbr` (Bottom solder mask)
    *   `F.Silkscreen.gbr` (Top silkscreen)
    *   `Edge.Cuts.gbr` (Board edge outline)
    *   `NPTH_drill.drl` & `PTH_drill.drl` (Excellon drill files)
2.  **Export Settings:**
    *   **Format:** Gerber X2
    *   **Drill Origin:** Absolute (keep drill files synced with copper layers)
    *   **Silkscreen Settings:** Subtract soldermask from silkscreen
3.  Zip the output files into `aerosense_esp32_pcb_v2.0.zip` and upload to JLCPCB (select 2-layer, 1.6mm thickness, lead-free HASL finish).

---

## Bill of Materials (BOM)

| Ref  | Value       | Footprint                    | Qty | Purpose / Description |
|------|-------------|------------------------------|-----|-----------------------|
| J1   | 2-pin JST   | JST_XH_B2B-XH-A_Vertical     | 1   | 5V BEC Power Input |
| J2   | 2x22 Female | PinSocket_1x22_P2.54_Vert    | 2   | ESP32-S3 DevKit Socket |
| J3   | 4-pin JST   | JST_XH_B4B-XH-A_Vertical     | 1   | BME280 Climate Module |
| J4   | 4-pin JST   | JST_XH_B4B-XH-A_Vertical     | 1   | PMS5003 Particle Sensor |
| J5   | 3-pin JST   | JST_XH_B3B-XH-A_Vertical     | 1   | MQ-135 Gas Sensor |
| J6   | 3-pin JST   | JST_XH_B3B-XH-A_Vertical     | 1   | Pixhawk MAVLink Telemetry |
| J7   | 8-pin Socket| PinSocket_1x08_P2.54_Vert    | 1   | LoRa SX1276 Ra-02 RF Module |
| J8   | 6-pin Socket| PinSocket_1x06_P2.54_Vert    | 1   | MicroSD Card SPI Module |
| R1   | 1.8 kΩ      | R_0805_2012Metric            | 1   | Resistor Divider (Top) |
| R2   | 3.3 kΩ      | R_0805_2012Metric            | 1   | Resistor Divider (Bottom) |
| R3   | 4.7 kΩ      | R_0805_2012Metric            | 1   | I2C SDA Pull-Up Resistor |
| R4   | 4.7 kΩ      | R_0805_2012Metric            | 1   | I2C SCL Pull-Up Resistor |
| C1   | 10 µF       | CP_Radial_D5.0mm_P2.00mm     | 1   | Power Filter Capacitor |
| C2   | 100 nF      | C_0805_2012Metric            | 1   | Decoupling Capacitor |
| H1-H4| M3 Spacer   | MountingHole_3.2mm_M3_Pad    | 4   | Enclosure Mount Holes |
