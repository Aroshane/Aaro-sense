# 🛸 AeroSense — Quadcopter 3D Pollution Mapper (ESP32-S3 Port)

A self-contained sensor payload for a quadcopter that logs and maps environmental pollution in 3D coordinate space (latitude / longitude / altitude).

---

## Project Structure

```
project/
├── firmware/                  ← Dual-firmware options (MicroPython & Arduino C++)
│   ├── main.py                ← MicroPython async payload loop & networking
│   ├── config.json            ← MicroPython pin maps, WiFi setup, calibration
│   ├── bme280.py              ← MicroPython I2C BME280 driver
│   ├── vl53l1x.py             ← MicroPython I2C VL53L1X ToF driver
│   ├── sdcard.py              ← MicroPython SPI SD card driver
│   └── aerosense_esp32/
│       └── aerosense_esp32.ino ← Production Arduino C++ firmware (optimized 0xCA float packing)
│
├── Ground/
│   ├── ground_control_app/    ← React (Vite) Ground Control Station Web App
│   ├── ground_station/
│   │   ├── aerosense_api.py   ← Flask GCS REST API Server (runs AI, serves files)
│   │   ├── aerosense_ground.py ← UDP socket / LoRa RX + InfluxDB & SQLite writer
│   │   └── simulate_flight.py ← Live flight telemetry simulator
│   └── aerosense_ground/
│       └── aerosense_ground.ino ← Arduino Nano ground receiver radio code
│
├── dashboard/
│   └── aerosense_dashboard.py ← Plotly Dash 3D web dashboard (reads SQLite DB)
│
├── ai_prediction/
│   └── aerosense_predict.py   ← Machine learning models for future ground-level PM2.5 forecasting
│
├── hardware/
│   ├── pcb/
│   │   ├── aerosense_payload.kicad_sch
│   │   └── aerosense_esp32_pcb_layout_guide.md ← PCB layout & fab guide
│   └── enclosure/
│       └── aerosense_enclosure.py
│
├── mission/
│   ├── aerosense_mission.py        ← ArduPilot waypoint generator
│   └── aerosense_mission.waypoints ← Pre-generated waypoints
│
└── docs/
    └── WIRING_ESP32.md        ← ESP32-S3 Wiring Reference (Current)
```

---

## Hardware Required (Current Revision)

By routing GPS telemetry directly from the Pixhawk/ArduPilot flight controller via MAVLink (`GLOBAL_POSITION_INT`), and using the ESP32-S3's internal ADC pin with a protective resistor divider for the MQ-135, we have eliminated redundant modules (standalone GPS, ADS1115 converter). This slashes size, weight, and overall payload cost.

| Component          | Interface | Est. Cost | Note |
|--------------------|-----------|-----------|------|
| **ESP32-S3 DevKit**| GPIO      | ₹600      | Dual-core, built-in WiFi, handles data processing & telemetry |
| PMS5003 PM sensor  | UART      | ₹900      | Laser PM2.5/PM10 particulate reader |
| BME280             | I²C       | ₹200      | Temperature, humidity, and barometric pressure module |
| MQ-135 Gas Sensor  | Analog    | ₹150      | Connected via protective 1.8kΩ/3.3kΩ divider to ESP32 ADC pin |
| LoRa SX1276 Ra-02  | SPI       | ₹450      | 433 MHz long-range telemetry transmitter |
| SPI MicroSD Module | SPI       | ₹80       | Local offline CSV backup storage |
| 5V BEC / DC-DC     | —         | ₹180      | Step-down power regulator from flight pack battery |
| **Total**          |           | **~₹2,560**| **~55% cheaper** than legacy Raspberry Pi build! |

Buy components from robu.in, robocraze.com, or rhydolabz.com.

---

## Quick Start

### Option A — Deploy MicroPython Firmware
1. Flash MicroPython firmware (v1.20 or newer) onto your ESP32-S3 DevKit using WebREPL or `esptool.py`:
   ```bash
   esptool.py --chip esp32s3 --port COM3 erase_flash
   esptool.py --chip esp32s3 --port COM3 --baud 460800 write_flash -z 0x0 GENERIC_S3-20230426-v1.20.0.bin
   ```
2. Upload the contents of the `firmware/` directory to the ESP32-S3 root using **Thonny IDE** or `mpremote`:
   ```bash
   mpremote fs cp firmware/config.json :config.json
   mpremote fs cp firmware/bme280.py :bme280.py
   mpremote fs cp firmware/vl53l1x.py :vl53l1x.py
   mpremote fs cp firmware/sdcard.py :sdcard.py
   mpremote fs cp firmware/main.py :main.py
   ```

### Option B — Deploy Arduino C++ Firmware (Optimized)
1. Open the [aerosense_esp32.ino](file:///c:/Users/aroma/Desktop/drone/AeroSense_Project/project/firmware/aerosense_esp32/aerosense_esp32.ino) sketch in the Arduino IDE.
2. Install the required libraries via the Library Manager:
   * Adafruit BME280 Library
   * VL53L1X (by Pololu)
   * Arduino-LoRa (by Sandeep Mistry)
3. Upload to your ESP32-S3. This version implements optimized **MessagePack `0xCA` single-precision 32-bit float serialization** to maximize LoRa range, reduce packet airtime, and reduce battery load.

---

## Running the Ground System

### Option 1 — Start the GCS and Dashboard via Launcher
You can start the unified GCS REST API Server (serving the React web app) and the Plotly Dash 3D Dashboard together:
1. Double-click `run_aerosense.bat` in the root of the project repository, or run:
   ```bash
   python project/launcher.py
   ```
2. This will automatically spin up:
   * The Flask GCS Server on [http://localhost:5001](http://localhost:5001)
   * The Dash Dashboard on [http://localhost:8050](http://localhost:8050)

### Option 2 — Manual Execution
* **Start Telemetry Ground Station**:
  ```bash
  pip3 install msgpack influxdb-client
  python3 project/Ground/ground_station/aerosense_ground.py
  ```
  This captures telemetry streams and saves them to `project/data/aerosense.db`.
  
* **Start 3D Plotly Dash Dashboard**:
  ```bash
  pip3 install dash plotly pandas scipy numpy
  python3 project/dashboard/aerosense_dashboard.py
  ```

---

## Pinout and Connections
Refer to the complete mapping guide in [WIRING_ESP32.md](file:///c:/Users/aroma/Desktop/drone/AeroSense_Project/project/docs/WIRING_ESP32.md).

---

## Flight Mission and Calibration
Configure ArduPilot waypoint grids inside `mission/aerosense_mission.py` and modify offset parameters inside `firmware/config.json`.

---

## License
MIT License
