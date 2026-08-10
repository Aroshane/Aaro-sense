"""
AeroSense Payload Firmware — main.py
ESP32-S3 | MicroPython 1.20+

Features:
  - Multi-sensor air quality logging (PMS5003, BME280, ADS1115+MQ135, GPS)
  - Real-time telemetry via WiFi UDP (MessagePack) and LoRa SX1276
  - Obstacle avoidance via VL53L1X ToF + HC-SR04 ultrasonic -> MAVLink v2 #330
  - Local CSV logging to external SPI MicroSD card module
  - Simulation mode configured in config.json
"""

import uasyncio as asyncio
import time
import struct
import os
import machine
from machine import Pin, SPI, I2C, UART
import random
import math
import socket

# Load drivers
import sdcard
from bme280 import BME280
from vl53l1x import VL53L1X

# ── Global MAVLink variables ──────────────────────────────────────────────────
mav_seq = 0

# ── Dataclasses / Structures ──────────────────────────────────────────────────
class PollutionPoint:
    def __init__(self, timestamp, lat, lon, alt_m, gps_quality, pm25, pm10,
                 temperature, humidity, pressure, voc, mq135_raw, quality_flag):
        self.timestamp = timestamp
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.gps_quality = gps_quality
        self.pm25 = pm25
        self.pm10 = pm10
        self.temperature = temperature
        self.humidity = humidity
        self.pressure = pressure
        self.voc = voc
        self.mq135_raw = mq135_raw
        self.quality_flag = quality_flag

    def to_csv_row(self):
        # Format ISO timestamp locally
        t_struct = time.gmtime(int(self.timestamp))
        iso_time = "{:04d}-{:02d}-{:02d}T{:02d}:{:02d}:{:02d}Z".format(
            t_struct[0], t_struct[1], t_struct[2], t_struct[3], t_struct[4], t_struct[5]
        )
        return [
            iso_time, self.lat, self.lon, self.alt_m, self.gps_quality,
            self.pm25, self.pm10, self.temperature, self.humidity,
            self.pressure, self.voc, self.mq135_raw, self.quality_flag
        ]

    @staticmethod
    def csv_header():
        return [
            "timestamp_utc", "lat", "lon", "alt_m", "gps_quality",
            "pm25_ugm3", "pm10_ugm3", "temp_c", "humidity_pct",
            "pressure_hpa", "voc_ohm", "mq135_v", "quality_flag"
        ]

    def to_msgpack(self) -> bytes:
        # Serialise to MessagePack lists (ints & floats only) using double-precision float (0xCB)
        lst = [
            round(self.timestamp, 1), round(self.lat, 6), round(self.lon, 6),
            round(self.alt_m, 1), self.gps_quality, round(self.pm25, 2),
            round(self.pm10, 2), round(self.temperature, 2), round(self.humidity, 2),
            round(self.pressure, 2), round(self.voc, 0), round(self.mq135_raw, 4),
            self.quality_flag
        ]
        return pack_msgpack_list(lst)

class ObstacleReading:
    def __init__(self, orientation_deg: int, distance_m: float, sensor_type: str):
        self.orientation_deg = orientation_deg
        self.distance_m = distance_m
        self.sensor_type = sensor_type

# ── MessagePack Encoder ───────────────────────────────────────────────────────
def pack_msgpack_list(lst) -> bytes:
    res = bytearray()
    n = len(lst)
    if n < 16:
        res.append(0x90 | n)
    else:
        raise ValueError("List too large for fixarray encoding")
        
    for x in lst:
        if isinstance(x, int):
            if 0 <= x <= 127:
                res.append(x)
            elif -32 <= x < 0:
                res.append(0xE0 | (x + 32))
            elif x >= 0:
                if x < 256:
                    res.extend([0xCC, x])
                elif x < 65536:
                    res.extend(struct.pack(">BH", 0xCD, x))
                else:
                    res.extend(struct.pack(">BI", 0xCE, x))
            else:
                if x >= -128:
                    res.extend(struct.pack(">Bb", 0xD0, x))
                elif x >= -32768:
                    res.extend(struct.pack(">Bh", 0xD1, x))
                else:
                    res.extend(struct.pack(">Bi", 0xD2, x))
        elif isinstance(x, float):
            res.extend(struct.pack(">Bd", 0xCB, x))
        else:
            raise TypeError("Unsupported MessagePack type")
    return bytes(res)

# ── Custom Minimal GPS NMEA GGA Parser ────────────────────────────────────────
def parse_gga(line: str):
    if not line.startswith("$") or "GGA" not in line:
        return None
    try:
        # Verify NMEA Checksum
        if "*" in line:
            body, crc_hex = line.split("*")
            calc_crc = 0
            for char in body[1:]:
                calc_crc ^= ord(char)
            if calc_crc != int(crc_hex.strip(), 16):
                return None
        else:
            body = line

        parts = body.split(",")
        if len(parts) < 10:
            return None

        # Fix Quality indicator
        quality_str = parts[6]
        if not quality_str or int(quality_str) == 0:
            return None
        quality = int(quality_str)

        # Latitude: DDMM.MMMM -> Dec Deg
        lat_val = parts[2]
        lat_dir = parts[3]
        if lat_val:
            lat_deg = float(lat_val[:2])
            lat_min = float(lat_val[2:])
            lat = lat_deg + (lat_min / 60.0)
            if lat_dir == "S":
                lat = -lat
        else:
            return None

        # Longitude: DDDMM.MMMM -> Dec Deg
        lon_val = parts[4]
        lon_dir = parts[5]
        if lon_val:
            lon_deg = float(lon_val[:3])
            lon_min = float(lon_val[3:])
            lon = lon_deg + (lon_min / 60.0)
            if lon_dir == "W":
                lon = -lon
        else:
            return None

        # Altitude: MSL
        alt_val = parts[9]
        alt_m = float(alt_val) if alt_val else 0.0

        return lat, lon, alt_m, quality
    except Exception:
        return None

# ── MAVLink Pack Utility ──────────────────────────────────────────────────────
def pack_obstacle_distance_mavlink2(distances, min_dist_cm, max_dist_cm, increment_f, time_us):
    global mav_seq
    # MAVLink v2 Header: STX(0xFD), Payload Len(167), Incompat(0), Compat(0), Seq, Sys(1), Comp(1), MsgID (330 -> 0x4A, 0x01, 0x00)
    # Payload Fields:
    # time_usec (uint64_t)
    # sensor_type (uint8_t) - 0 (Laser)
    # distances (uint16_t[72])
    # increment (uint8_t)
    # min_distance (uint16_t)
    # max_distance (uint16_t)
    # increment_f (float)
    # angle_offset (float) - 0.0
    # frame (uint8_t) - 12 (MAV_FRAME_BODY_FRD)
    
    payload = struct.pack(
        "<Q B" + "H"*72 + "B H H f f B",
        time_us,
        0,
        *distances,
        0,
        min_dist_cm,
        max_dist_cm,
        increment_f,
        0.0,
        12
    )

    header = struct.pack(
        "<B B B B B B B H B",
        0xFD,
        len(payload),
        0,
        0,
        mav_seq,
        1,
        1,
        0x014A,
        0
    )
    mav_seq = (mav_seq + 1) & 0xFF

    def crc_feed(crc, b):
        tmp = b ^ (crc & 0xFF)
        tmp ^= (tmp << 4) & 0xFF
        return ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF

    crc = 0xFFFF
    for b in header[1:] + payload:
        crc = crc_feed(crc, b)
    crc = crc_feed(crc, 23)  # CRC Extra byte for MSG_ID 330

    return header + payload + struct.pack("<H", crc)

# ── Native Hardware Drivers ───────────────────────────────────────────────────

class PMS5003Reader:
    HEAD1 = 0x42; HEAD2 = 0x4D; FRAME_LEN = 32

    def __init__(self, uart_id, tx_pin, rx_pin, baud, cal):
        self.uart = UART(uart_id, baudrate=baud, tx=Pin(tx_pin), rx=Pin(rx_pin), timeout=100)
        self.cal = cal
        self.pm25 = 0.0
        self.pm10 = 0.0
        self._ok = False

    def read(self) -> bool:
        try:
            # Check if bytes are waiting
            if not self.uart.any():
                return False
            # Sync to header
            for _ in range(64):
                b = self.uart.read(1)
                if b and b[0] == self.HEAD1:
                    b = self.uart.read(1)
                    if b and b[0] == self.HEAD2:
                        break
            else:
                self._ok = False
                return False

            body = self.uart.read(self.FRAME_LEN - 2)
            if not body or len(body) < self.FRAME_LEN - 2:
                self._ok = False
                return False

            frame = bytes([self.HEAD1, self.HEAD2]) + body
            checksum_calc = sum(frame[:-2]) & 0xFFFF
            checksum_recv = (frame[-2] << 8) | frame[-1]
            if checksum_calc != checksum_recv:
                self._ok = False
                return False

            pm25_raw = (frame[10] << 8) | frame[11]
            pm10_raw = (frame[12] << 8) | frame[13]

            self.pm25 = max(0.0, pm25_raw + self.cal["pm25_offset"])
            self.pm10 = max(0.0, pm10_raw + self.cal["pm10_offset"])
            self._ok = True
            return True
        except Exception:
            self._ok = False
            return False

class InternalADCReader:
    def __init__(self, pin_num, cal):
        self.cal = cal
        self.voltage = 0.0
        self._ok = False
        try:
            from machine import ADC
            self.adc = ADC(Pin(pin_num))
            # Set 11dB attenuation for 0-3.3V range
            self.adc.atten(ADC.ATTN_11DB)
            self._ok = True
        except Exception as e:
            print(f"[InternalADC] Init failed: {e}")
            self._ok = False

    def read(self) -> bool:
        if not self._ok:
            return False
        try:
            val = self.adc.read_uv() # Read in microvolts (better accuracy on newer MicroPython)
            self.voltage = (val / 1_000_000.0) * self.cal["mq135_scale"]
            return True
        except AttributeError:
            try:
                # Fallback to standard 12-bit read
                val = self.adc.read()
                self.voltage = (val / 4095.0) * 3.3 * self.cal["mq135_scale"]
                return True
            except Exception:
                return False
        except Exception:
            return False


# GPSReader removed in favor of direct MAVLink autopilot telemetry ingestion.

class LoRaTX:
    REG_FIFO = 0x00; REG_OP_MODE = 0x01; REG_FRF_MSB = 0x06; REG_FRF_MID = 0x07
    REG_FRF_LSB = 0x08; REG_PA_CONFIG = 0x09; REG_FIFO_ADDR_PTR = 0x0D
    REG_FIFO_TX_BASE = 0x0E; REG_IRQ_FLAGS = 0x12; REG_PAYLOAD_LEN = 0x22
    REG_MODEM_CONFIG_1 = 0x1D; REG_MODEM_CONFIG_2 = 0x1E; REG_MODEM_CONFIG_3 = 0x26
    REG_SYNC_WORD = 0x39; MODE_SLEEP = 0x80; MODE_STDBY = 0x81; MODE_TX = 0x83

    def __init__(self, spi, cs_pin, rst_pin, dio0_pin, freq_mhz):
        self.spi = spi
        self.cs = Pin(cs_pin, Pin.OUT, value=1)
        self.rst = Pin(rst_pin, Pin.OUT, value=1)
        self.dio0 = Pin(dio0_pin, Pin.IN)
        self.freq = freq_mhz
        self._ok = False

    def init(self):
        try:
            self.rst.value(0)
            time.sleep_ms(10)
            self.rst.value(1)
            time.sleep_ms(10)

            version = self._read_reg(0x42)
            if version != 0x12:
                print(f"[LoRa] SX1276 version mismatch: 0x{version:02X}")
                return False

            self._write_reg(self.REG_OP_MODE, self.MODE_SLEEP)
            time.sleep_ms(10)

            frf = int((self.freq * 1e6) / 61.03515625)
            self._write_reg(self.REG_FRF_MSB, (frf >> 16) & 0xFF)
            self._write_reg(self.REG_FRF_MID, (frf >> 8) & 0xFF)
            self._write_reg(self.REG_FRF_LSB, frf & 0xFF)

            self._write_reg(self.REG_PA_CONFIG, 0x8F)
            self._write_reg(self.REG_MODEM_CONFIG_1, 0x72)
            self._write_reg(self.REG_MODEM_CONFIG_2, 0x74)
            self._write_reg(self.REG_MODEM_CONFIG_3, 0x04)
            self._write_reg(self.REG_SYNC_WORD, 0x12)
            self._write_reg(self.REG_FIFO_TX_BASE, 0x00)
            self._write_reg(self.REG_OP_MODE, self.MODE_STDBY)
            self._ok = True
            print(f"[LoRa] Init OK @ {self.freq} MHz")
            return True
        except Exception as e:
            print(f"[LoRa] Init Exception: {e}")
            return False

    def transmit(self, data: bytes) -> bool:
        if not self._ok:
            return False
        try:
            self._write_reg(self.REG_OP_MODE, self.MODE_STDBY)
            self._write_reg(self.REG_FIFO_ADDR_PTR, 0x00)
            self._write_reg(self.REG_PAYLOAD_LEN, len(data))
            
            for b in data:
                self._write_reg(self.REG_FIFO, b)

            self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
            self._write_reg(self.REG_OP_MODE, self.MODE_TX)

            deadline = time.ticks_ms() + 1000
            while time.ticks_diff(deadline, time.ticks_ms()) > 0:
                if self.dio0.value():
                    self._write_reg(self.REG_IRQ_FLAGS, 0xFF)
                    self._write_reg(self.REG_OP_MODE, self.MODE_STDBY)
                    return True
                time.sleep_ms(5)
            return False
        except Exception as e:
            print(f"[LoRa] TX Exception: {e}")
            return False

    def _write_reg(self, reg, val):
        self.cs(0)
        self.spi.write(bytes([reg | 0x80, val]))
        self.cs(1)

    def _read_reg(self, reg):
        self.cs(0)
        self.spi.write(bytes([reg & 0x7F]))
        val = self.spi.read(1)[0]
        self.cs(1)
        return val

class UltrasonicHCSR04:
    def __init__(self, trigger_pin, echo_pin, orientation_deg):
        self.trig = Pin(trigger_pin, Pin.OUT, value=0)
        self.echo = Pin(echo_pin, Pin.IN)
        self.orientation_deg = orientation_deg
        self.distance_m = 4.0

    def read(self):
        try:
            self.trig.value(1)
            time.sleep_us(10)
            self.trig.value(0)
            
            # Pulse duration check (30ms = 30000us timeout)
            duration = machine.time_pulse_us(self.echo, 1, 30000)
            if duration < 0:
                self.distance_m = 4.0
            else:
                # Speed of sound logic (343m/s) -> 343m/s / 2 / 10^6 us/s = 0.0001715
                self.distance_m = min(duration * 0.0001715, 4.0)
            return ObstacleReading(self.orientation_deg, self.distance_m, "hc_sr04")
        except Exception:
            return None

class MAVLinkConnection:
    def __init__(self, uart_id, tx_pin, rx_pin, baud):
        self.uart = UART(uart_id, baudrate=baud, tx=Pin(tx_pin), rx=Pin(rx_pin), timeout=10)
        self._ok = True
        self.lat = 8.8932
        self.lon = 76.6141
        self.alt_m = 0.0
        self.quality = 0
        self.last_update = 0
        self._rx_buf = bytearray()
        print(f"[MAVLink] Serial configured on UART{uart_id} @ {baud}")

    def check_rx(self):
        """Non-blocking parse of incoming MAVLink packets to extract GPS coordinates."""
        try:
            # Check if bytes are waiting on UART
            if not self.uart.any():
                return
            
            data = self.uart.read()
            if not data:
                return
            self._rx_buf.extend(data)
            
            # Keep buffer size bounded
            if len(self._rx_buf) > 1024:
                self._rx_buf = self._rx_buf[-512:]
                
            # Process packets in buffer
            while True:
                # Sync to MAVLink v2 magic byte (0xFD)
                idx = self._rx_buf.find(0xFD)
                if idx == -1:
                    self._rx_buf.clear()
                    break
                if idx > 0:
                    del self._rx_buf[:idx] # Discard leading bytes
                    
                # We need at least the header (10 bytes) to parse length and MsgID
                if len(self._rx_buf) < 10:
                    break
                    
                payload_len = self._rx_buf[1]
                msg_id = self._rx_buf[7] | (self._rx_buf[8] << 8) | (self._rx_buf[9] << 16)
                
                total_packet_len = 10 + payload_len + 2 # Header + Payload + Checksum (2)
                if len(self._rx_buf) < total_packet_len:
                    break # Incomplete packet, wait for more bytes
                    
                packet = bytes(self._rx_buf[:total_packet_len])
                del self._rx_buf[:total_packet_len]
                
                # Check for GLOBAL_POSITION_INT (ID 33)
                if msg_id == 33:
                    # Validate Checksum
                    header = packet[:10]
                    payload = packet[10:10+payload_len]
                    checksum_recv = struct.unpack("<H", packet[-2:])[0]
                    
                    def crc_feed(crc, b):
                        tmp = b ^ (crc & 0xFF)
                        tmp ^= (tmp << 4) & 0xFF
                        return ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF

                    crc = 0xFFFF
                    for b in header[1:] + payload:
                        crc = crc_feed(crc, b)
                    crc = crc_feed(crc, 104) # CRC Extra for ID 33
                    
                    if crc == checksum_recv:
                        # Extract lat, lon, alt from payload
                        # Skip time_boot_ms (first 4 bytes)
                        # lat (4-7), lon (8-11), alt (12-15)
                        lat_val, lon_val, alt_val = struct.unpack("<iii", payload[4:16])
                        self.lat = lat_val / 1e7
                        self.lon = lon_val / 1e7
                        self.alt_m = alt_val / 1000.0 # mm -> m
                        self.quality = 3 # Fused position indicates 3D fix
                        self.last_update = time.time()
                    else:
                        print("[MAVLink] CRC validation failed for GLOBAL_POSITION_INT")
        except Exception as e:
            print(f"[MAVLink] RX Error: {e}")

    @property
    def healthy(self):
        # Healthy if we received GPS coordinate updates in the last 15 seconds
        return (time.time() - self.last_update) < 15.0

    def send_obstacle_distance(self, readings, safety_m=2.0):
        distances = [0] * 72
        for r in readings:
            sector = int(r.orientation_deg / 5) % 72
            distances[sector] = int(r.distance_m * 100) # m -> cm

        min_dist_cm = int(0.1 * 100)
        max_dist_cm = int(4.0 * 100)
        packet = pack_obstacle_distance_mavlink2(
            distances, min_dist_cm, max_dist_cm, 5.0, int(time.time() * 1e6)
        )
        try:
            self.uart.write(packet)
        except Exception as e:
            print(f"[MAVLink] Write Exception: {e}")

# ── WiFi UDP Setup ────────────────────────────────────────────────────────────
class UDPStation:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[UDP] Targets ground station {ip}:{port}")

    def transmit(self, data):
        try:
            self.sock.sendto(data, (self.ip, self.port))
            return True
        except Exception:
            return False

# ── Simulation Classes ────────────────────────────────────────────────────────

class SimPMS5003:
    def __init__(self, cal):
        self.cal = cal
        self.pm25 = 0.0
        self.pm10 = 0.0
        self._t = 0
    def read(self):
        self._t += 0.1
        self.pm25 = max(0, 15 + 12*math.sin(self._t) + random.random()*3 + self.cal["pm25_offset"])
        self.pm10 = self.pm25 * 1.4
        return True
    @property
    def healthy(self): return True

class SimBME280:
    def __init__(self, cal):
        self.cal = cal
        self._t = 0
        self.temperature = 28.5
        self.humidity = 68.0
        self.pressure = 1010.2
    def get_readings(self):
        self._t += 0.05
        self.temperature = 28.5 + 2*math.sin(self._t*0.3) + self.cal["temp_offset"]
        self.humidity = 68.0 + 5*math.cos(self._t*0.2) + self.cal["humidity_offset"]
        self.pressure = 1010.2 + 0.5*math.sin(self._t*0.1)
        return self.temperature, self.humidity, self.pressure

class SimADS1115:
    def __init__(self, cal):
        self.cal = cal
        self.voltage = 1.2
    def read(self):
        self.voltage = (1.2 + (random.random() - 0.5)*0.1) * self.cal["mq135_scale"]
        return True

class SimGPS:
    def __init__(self):
        self._t = 0
        self.lat = 8.8932
        self.lon = 76.6141
        self.alt_m = 30.0
        self.quality = 3
        self._dir = 1
    def check_uart(self):
        self._t += 1
        self.lon += 0.000025 * self._dir
        if self._t % 20 == 0:
            self.lat += 0.000015
            self._dir *= -1
        self.alt_m = 30.0 + 15*math.sin(self._t * 0.05)
    @property
    def healthy(self): return True

class SimVL53L1X:
    def __init__(self, o_deg):
        self.orientation_deg = o_deg
    def read(self):
        d = 4.0 if random.random() > 0.05 else random.uniform(0.5, 2.5)
        return ObstacleReading(self.orientation_deg, d, "vl53l1x_sim")
    def start_ranging(self): pass
    def stop_ranging(self): pass
    def clear_interrupt(self): pass
    @property
    def data_ready(self): return True

class SimHCSR04:
    def __init__(self, o_deg):
        self.orientation_deg = o_deg
    def read(self):
        d = 4.0 if random.random() > 0.04 else random.uniform(0.3, 3.0)
        return ObstacleReading(self.orientation_deg, d, "hcsr04_sim")

class SimMAVLink:
    def send_obstacle_distance(self, readings, safety_m=2.0):
        dangers = [r for r in readings if r.distance_m < safety_m]
        for d in dangers:
            print(f"[SimMAVLink] ⚠️ OBSTACLE at {d.orientation_deg}° — {d.distance_m:.2f}m [{d.sensor_type}]")

class SimLoRa:
    def init(self): return True
    def transmit(self, data): return True

# ── CSV File Logger ───────────────────────────────────────────────────────────
class FileLogger:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.path = None
        self.file = None

    def open(self):
        # Generate filename from system ticks
        t = time.ticks_ms()
        self.path = f"{self.base_dir}/flight_{t}.csv"
        # Ensure directories exist
        try:
            os.mkdir(self.base_dir)
        except Exception:
            pass
        try:
            self.file = open(self.path, "w")
            # Write header
            header = ",".join(PollutionPoint.csv_header()) + "\n"
            self.file.write(header)
            self.file.flush()
            print(f"[Logger] Flight CSV ready: {self.path}")
        except Exception as e:
            print(f"[Logger] File open failed: {e}")

    def write(self, pt: PollutionPoint):
        if not self.file:
            return
        try:
            row_data = [str(x) for x in pt.to_csv_row()]
            row = ",".join(row_data) + "\n"
            self.file.write(row)
            self.file.flush()
        except Exception as e:
            print(f"[Logger] File write failed: {e}")

    def close(self):
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None

# ── Async Loops ───────────────────────────────────────────────────────────────

async def avoidance_loop(sensors, mav, safety_m):
    print("[Avoidance] Loop started (10 Hz)")
    while True:
        try:
            readings = []
            for s in sensors:
                r = s.read()
                if r:
                    readings.append(r)
            if readings:
                mav.send_obstacle_distance(readings, safety_m)
        except Exception as e:
            print(f"[Avoidance] Loop Exception: {e}")
        await asyncio.sleep(0.1)

async def payload_loop(cfg):
    sim_mode = cfg.get("sim_mode", False)
    cal = cfg["calibration"]
    sens_cfg = cfg["sensors"]
    lora_cfg = cfg["lora"]
    sd_cfg = cfg["sdcard"]
    av_cfg = cfg["avoidance"]
    ap_cfg = cfg.get("autopilot", {"enabled": True, "uart_id": 1, "tx_pin": 25, "rx_pin": 33, "baud": 57600})
    log_cfg = cfg["logging"]
    wifi_cfg = cfg["wifi"]

    # ── Init Network WiFi Station ─────────────────────────────────────────────
    wifi_ok = False
    udp_tx = None
    if not sim_mode and wifi_cfg.get("enabled", False):
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)
            wlan.connect(wifi_cfg["ssid"], wifi_cfg["password"])
            print(f"[WiFi] Connecting to {wifi_cfg['ssid']}...")
            for _ in range(20): # 10s timeout
                if wlan.isconnected():
                    wifi_ok = True
                    break
                await asyncio.sleep(0.5)
            if wifi_ok:
                print(f"[WiFi] Connected! IP: {wlan.ifconfig()[0]}")
                udp_tx = UDPStation(wifi_cfg["ground_station_ip"], wifi_cfg["udp_port"])
            else:
                print("[WiFi] Connection timed out. Running without UDP telemetry.")
        except Exception as e:
            print(f"[WiFi] Setup failed: {e}")

    # ── Mount SD Card ─────────────────────────────────────────────────────────
    sd_ok = False
    if not sim_mode and sd_cfg.get("enabled", False):
        try:
            sd_spi = SPI(
                sd_cfg["spi_id"],
                baudrate=10000000,
                sck=Pin(sd_cfg["sck_pin"]),
                mosi=Pin(sd_cfg["mosi_pin"]),
                miso=Pin(sd_cfg["miso_pin"])
            )
            sd_cs = Pin(sd_cfg["cs_pin"], Pin.OUT)
            sd = sdcard.SDCard(sd_spi, sd_cs)
            vfs = os.VfsFat(sd)
            os.mount(vfs, "/sd")
            sd_ok = True
            print("[SD] Mounted at /sd")
        except Exception as e:
            print(f"[SD] Mount failed (using local flash for logging instead): {e}")

    log_dir = "/sd" if sd_ok else "/flash_logs"
    logger = FileLogger(log_dir)
    logger.open()

    # ── Init Sensor Hardware/Simulation ───────────────────────────────────────
    if sim_mode:
        print("=" * 60)
        print("  AEROSENSE PAYLOAD — RUNNING IN SIMULATION MODE")
        print("=" * 60)
        pms = SimPMS5003(cal)
        bme = SimBME280(cal)
        mq135 = SimADS1115(cal)
        gps = SimGPS()
        lora = SimLoRa()
        mav = SimMAVLink()
    else:
        # Common I2C
        sda = Pin(sens_cfg["bme280"]["sda_pin"])
        scl = Pin(sens_cfg["bme280"]["scl_pin"])
        i2c = I2C(sens_cfg["bme280"]["i2c_id"], sda=sda, scl=scl, freq=100000)

        pms = PMS5003Reader(sens_cfg["pms5003"]["uart_id"], sens_cfg["pms5003"]["tx_pin"], sens_cfg["pms5003"]["rx_pin"], sens_cfg["pms5003"]["baud"], cal)
        bme = BME280(i2c, sens_cfg["bme280"]["i2c_addr"])
        mq135 = InternalADCReader(sens_cfg["mq135"]["pin"], cal)
        
        # MAVLink Autopilot Telemetry link
        mav = MAVLinkConnection(ap_cfg["uart_id"], ap_cfg["tx_pin"], ap_cfg["rx_pin"], ap_cfg["baud"])
        gps = mav # Alias MAVLink as gps to reuse loop data structures

        # LoRa SX1276 Ra-02 SPI
        lora_spi = SPI(
            lora_cfg["spi_id"],
            baudrate=5000000,
            sck=Pin(lora_cfg["sck_pin"]),
            mosi=Pin(lora_cfg["mosi_pin"]),
            miso=Pin(lora_cfg["miso_pin"])
        )
        lora = LoRaTX(lora_spi, lora_cfg["cs_pin"], lora_cfg["rst_pin"], lora_cfg["dio0_pin"], lora_cfg["freq_mhz"])
        lora.init()

    # ── Obstacle Avoidance Init ───────────────────────────────────────────────
    avoidance_sensors = []
    av_task = None
    if av_cfg.get("enabled", False):
        for s in av_cfg["sensors"]:
            if sim_mode:
                if s["type"] == "vl53l1x":
                    avoidance_sensors.append(SimVL53L1X(s["orientation_deg"]))
                elif s["type"] == "hc_sr04":
                    avoidance_sensors.append(SimHCSR04(s["orientation_deg"]))
            else:
                if s["type"] == "vl53l1x":
                    try:
                        tof = VL53L1X(i2c, s["i2c_addr"])
                        tof.start_ranging()
                        avoidance_sensors.append(tof)
                        print(f"[VL53L1X] Configured at 0x{s['i2c_addr']:02X} — {s['orientation_deg']}°")
                    except Exception as e:
                        print(f"[VL53L1X] Init failed: {e}")
                elif s["type"] == "hc_sr04":
                    avoidance_sensors.append(UltrasonicHCSR04(s["trigger_pin"], s["echo_pin"], s["orientation_deg"]))
                    print(f"[HC-SR04] Configured trig={s['trigger_pin']} echo={s['echo_pin']} — {s['orientation_deg']}°")

        mav = SimMAVLink() if sim_mode else MAVLinkConnection(av_cfg["uart_id"], av_cfg["tx_pin"], av_cfg["rx_pin"], av_cfg["baud"])
        av_task = asyncio.create_task(avoidance_loop(avoidance_sensors, mav, av_cfg["safety_distance_m"]))

    # ── Main Payload Core Loop ────────────────────────────────────────────────
    interval_ms = int(log_cfg["interval_s"] * 1000)
    print("✅ AeroSense payload loop running...")

    try:
        while True:
            t0 = time.ticks_ms()

            # Poll UART lines (Non-blocking check)
            if sim_mode:
                gps.check_uart()
            else:
                mav.check_rx()
            pm_ok = pms.read()
            
            # Read I2C components
            bme_ok = False
            try:
                temp_c, hum, press_hpa = bme.get_readings()
                bme_ok = True
            except Exception:
                temp_c = hum = press_hpa = 0.0

            ads_ok = mq135.read()

            # Construct diagnostics flag
            quality = 0
            if not gps.healthy: quality |= 0x01
            if not bme_ok:      quality |= 0x02
            if not pm_ok:       quality |= 0x04

            pt = PollutionPoint(
                timestamp=time.time(),
                lat=gps.lat,
                lon=gps.lon,
                alt_m=gps.alt_m,
                gps_quality=gps.quality,
                pm25=pms.pm25 if pm_ok else -1.0,
                pm10=pms.pm10 if pm_ok else -1.0,
                temperature=temp_c if bme_ok else -999.0,
                humidity=hum if bme_ok else -1.0,
                pressure=press_hpa if bme_ok else -1.0,
                voc=-1.0, # N/A on BME280
                mq135_raw=mq135.voltage if ads_ok else -1.0,
                quality_flag=quality
            )

            # Local flash / SD CSV log
            logger.write(pt)

            # Telemetry transmit
            payload_bin = pt.to_msgpack()
            if lora._ok:
                lora.transmit(payload_bin)
            if udp_tx:
                udp_tx.transmit(payload_bin)

            # Console diagnostic output
            print(
                f"GPS({pt.gps_quality}) {pt.lat:.5f},{pt.lon:.5f} alt={pt.alt_m:.1f}m | "
                f"PM2.5={pt.pm25:.1f} PM10={pt.pm10:.1f} | T={pt.temperature:.1f}C RH={pt.humidity:.1f}% | "
                f"Q=0x{quality:02X}"
            )

            # Compute accurate loop wait time
            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            sleep_time = max(0, interval_ms - elapsed)
            await asyncio.sleep_ms(sleep_time)

    except asyncio.CancelledError:
        print("[Payload] Main loop cancelled, cleaning up...")
    finally:
        if av_task:
            av_task.cancel()
        logger.close()
        # Clean up VL53L1X ranging
        if not sim_mode:
            for s in avoidance_sensors:
                if hasattr(s, "stop_ranging"):
                    s.stop_ranging()
        print("[Payload] Shutdown complete.")

# ── Entry Point ───────────────────────────────────────────────────────────────
def main():
    # Load config file (ujson)
    try:
        with open("config.json") as f:
            import ujson
            cfg = ujson.load(f)
    except Exception as e:
        print("Could not load config.json, using defaults. Exception:", e)
        return

    try:
        asyncio.run(payload_loop(cfg))
    except KeyboardInterrupt:
        print("Stopped by user.")

if __name__ == "__main__":
    main()
