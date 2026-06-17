"""
AeroSense Ground Station — aerosense_ground.py
Runs on a second RPi or laptop.
Receives telemetry via LoRa (SX1276 Ra-02 SPI) and WiFi UDP socket (port 5005),
decodes MessagePack, writes to a local SQLite database (for dashboard compatibility),
writes to InfluxDB, and prints a live console feed.

Install dependencies:
  pip3 install msgpack influxdb-client
  (If running on Raspberry Pi with LoRa hardware: pip3 install RPi.GPIO spidev)
"""

import time
import logging
import msgpack
import socket
import threading
import sqlite3
import os
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# ── Config ────────────────────────────────────────────────────────────────────
LORA_SPI_BUS  = 0
LORA_SPI_CS   = 0
LORA_RST_PIN  = 25
LORA_DIO0_PIN = 24
LORA_FREQ_MHZ = 433.0

INFLUX_URL    = "http://localhost:8086"
INFLUX_TOKEN  = "your-influxdb-token-here"
INFLUX_ORG    = "aerosense"
INFLUX_BUCKET = "aerosense"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("aerosense.ground")

# Global stop signal for threads
running = True

# ── LoRa RX Driver Variables ──────────────────────────────────────────────────
REG_FIFO           = 0x00
REG_OP_MODE        = 0x01
REG_FRF_MSB        = 0x06
REG_FRF_MID        = 0x07
REG_FRF_LSB        = 0x08
REG_IRQ_FLAGS      = 0x12
REG_RX_NB_BYTES    = 0x13
REG_FIFO_RX_CURRENT= 0x10
REG_FIFO_ADDR_PTR  = 0x0D
REG_MODEM_CONFIG_1 = 0x1D
REG_MODEM_CONFIG_2 = 0x1E
REG_MODEM_CONFIG_3 = 0x26
REG_SYNC_WORD      = 0x39
REG_PKT_SNR_VALUE  = 0x19
REG_PKT_RSSI_VALUE = 0x1A

MODE_SLEEP    = 0x80
MODE_STDBY    = 0x81
MODE_RX_CONT  = 0x85

# Placeholders for Raspberry Pi Specific SPI / GPIO
spi = None
GPIO = None

def write_reg(reg, val):
    spi.xfer2([reg | 0x80, val])

def read_reg(reg):
    return spi.xfer2([reg & 0x7F, 0x00])[1]

def lora_init():
    global spi, GPIO
    import RPi.GPIO as _GPIO
    import spidev as _spidev
    GPIO = _GPIO
    spi = _spidev.SpiDev()

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(LORA_RST_PIN,  GPIO.OUT)
    GPIO.setup(LORA_DIO0_PIN, GPIO.IN)

    spi.open(LORA_SPI_BUS, LORA_SPI_CS)
    spi.max_speed_hz = 5_000_000
    spi.mode = 0b00

    # Reset
    GPIO.output(LORA_RST_PIN, GPIO.LOW);  time.sleep(0.01)
    GPIO.output(LORA_RST_PIN, GPIO.HIGH); time.sleep(0.01)

    ver = read_reg(0x42)
    assert ver == 0x12, f"SX1276 version wrong: 0x{ver:02X}"

    write_reg(REG_OP_MODE, MODE_SLEEP); time.sleep(0.01)

    # Frequency
    frf = int((LORA_FREQ_MHZ * 1e6) / 61.03515625)
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >>  8) & 0xFF)
    write_reg(REG_FRF_LSB,  frf        & 0xFF)

    # BW=125kHz, CR=4/5, explicit header
    write_reg(REG_MODEM_CONFIG_1, 0x72)
    # SF=7, CRC on
    write_reg(REG_MODEM_CONFIG_2, 0x74)
    # LNA AGC on
    write_reg(REG_MODEM_CONFIG_3, 0x04)

    write_reg(REG_SYNC_WORD, 0x12)

    # Set FIFO RX base to 0
    write_reg(0x0F, 0x00)

    write_reg(REG_OP_MODE, MODE_RX_CONT)
    log.info(f"LoRa RX ready @ {LORA_FREQ_MHZ} MHz")


def receive_packet() -> bytes | None:
    """Poll DIO0 — returns bytes if a packet arrived, else None."""
    if not GPIO.input(LORA_DIO0_PIN):
        return None

    flags = read_reg(REG_IRQ_FLAGS)
    write_reg(REG_IRQ_FLAGS, 0xFF)  # clear all

    if flags & 0x20:   # CRC error
        log.warning("LoRa CRC error")
        return None

    if not (flags & 0x40):  # RxDone bit
        return None

    nb = read_reg(REG_RX_NB_BYTES)
    ptr = read_reg(REG_FIFO_RX_CURRENT)
    write_reg(REG_FIFO_ADDR_PTR, ptr)

    raw = bytes(spi.xfer2([REG_FIFO & 0x7F] + [0x00] * nb)[1:])

    snr  = read_reg(REG_PKT_SNR_VALUE)
    rssi = read_reg(REG_PKT_RSSI_VALUE) - 157

    log.debug(f"RX {nb} bytes | RSSI={rssi} dBm SNR={snr*0.25:.1f} dB")
    return raw

# ── UDP Telemetry Receiver Thread ─────────────────────────────────────────────
def udp_listener_thread(ip, port, packet_queue):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    sock.bind((ip, port))
    sock.settimeout(1.0)
    log.info(f"UDP listener thread bound to {ip}:{port}")
    
    while running:
        try:
            data, addr = sock.recvfrom(1024)
            packet_queue.append((data, "udp", 0))
        except socket.timeout:
            continue
        except Exception as e:
            log.error(f"UDP Listener Exception: {e}")
            break
    sock.close()

# ── InfluxDB Writer ───────────────────────────────────────────────────────────
def make_influx_point(d: dict, rssi: int = 0) -> Point:
    return (
        Point("pollution")
        .tag("source", "drone")
        .field("lat",         d["lat"])
        .field("lon",         d["lon"])
        .field("alt_m",       d["alt_m"])
        .field("gps_quality", d["gps_quality"])
        .field("pm25",        d["pm25"])
        .field("pm10",        d["pm10"])
        .field("temperature", d["temperature"])
        .field("humidity",    d["humidity"])
        .field("pressure",    d["pressure"])
        .field("voc",         d["voc"])
        .field("mq135_v",     d["mq135_raw"])
        .field("quality_flag",d["quality_flag"])
        .field("lora_rssi",   rssi)
        .time(int(d["timestamp"] * 1e9), WritePrecision.NS)
    )

# ── MessagePack Decoder ───────────────────────────────────────────────────────
KEYS = ["timestamp","lat","lon","alt_m","gps_quality",
        "pm25","pm10","temperature","humidity","pressure",
        "voc","mq135_raw","quality_flag"]

def decode(raw: bytes) -> dict | None:
    try:
        values = msgpack.unpackb(raw)
        return dict(zip(KEYS, values))
    except Exception as e:
        log.error(f"Decode error: {e}")
        return None

# ── Main ground loop ──────────────────────────────────────────────────────────
def main():
    global running
    packet_queue = []
    
    # 1. Initialize local SQLite Database (creates tables if missing)
    db_dir = "data"
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "aerosense.db")
    db_conn = sqlite3.connect(db_path, check_same_thread=False)
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS pollution_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL, lat REAL, lon REAL, alt_m REAL,
            gps_quality INTEGER, pm25 REAL, pm10 REAL,
            temperature REAL, humidity REAL, pressure REAL,
            voc REAL, mq135_raw REAL, quality_flag INTEGER
        )""")
    db_conn.commit()
    log.info(f"SQLite database initialized at: {db_path}")

    # 2. Try initializing LoRa SPI hardware
    lora_enabled = False
    try:
        lora_init()
        lora_enabled = True
    except ImportError:
        log.warning("LoRa imports (RPi.GPIO/spidev) not found. LoRa hardware disabled.")
    except Exception as e:
        log.warning(f"LoRa initialization failed: {e}. LoRa hardware disabled.")

    # 3. Start UDP Receiver Thread
    udp_thread = threading.Thread(target=udp_listener_thread, args=("0.0.0.0", 5005, packet_queue))
    udp_thread.daemon = True
    udp_thread.start()

    # 4. InfluxDB Setup
    write_api = None
    influx_client = None
    try:
        influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        log.info("InfluxDB connection established.")
    except Exception as e:
        log.warning(f"InfluxDB client could not be configured: {e}. Telemetry will not be sent to InfluxDB.")

    log.info("Ground station telemetry server listening (Ctrl-C to stop)...")
    pkt_count = 0

    try:
        while True:
            # Poll LoRa hardware packet
            if lora_enabled:
                try:
                    raw = receive_packet()
                    if raw:
                        rssi = read_reg(REG_PKT_RSSI_VALUE) - 157
                        packet_queue.append((raw, "lora", rssi))
                except Exception as e:
                    log.error(f"LoRa poll exception: {e}")

            # Drain queue
            while packet_queue:
                raw, source, rssi = packet_queue.pop(0)
                d = decode(raw)
                if d:
                    pkt_count += 1
                    ts = datetime.fromtimestamp(d["timestamp"], tz=timezone.utc)
                    
                    # Safe ASCII logs (replaces non-ASCII symbols with equivalent letters)
                    print(
                        f"\n[#{pkt_count}] {ts.strftime('%H:%M:%S')} UTC (via {source.upper()}" +
                        (f", RSSI={rssi}dBm" if source == "lora" else "") + ")\n"
                        f"  GPS : lat={d['lat']:.5f}  lon={d['lon']:.5f}  "
                        f"alt={d['alt_m']:.1f} m  fix={d['gps_quality']}\n"
                        f"  PM  : PM2.5={d['pm25']:.1f}  PM10={d['pm10']:.1f} ug/m3\n"
                        f"  Env : T={d['temperature']:.1f}C  "
                        f"RH={d['humidity']:.1f}%  P={d['pressure']:.1f} hPa\n"
                        f"  Gas : VOC={d['voc']:.0f} ohm  MQ135={d['mq135_raw']:.3f} V\n"
                        f"  Flag: 0x{d['quality_flag']:02X}"
                    )

                    # Log to Local SQLite
                    try:
                        db_conn.execute("""
                            INSERT INTO pollution_points
                            (timestamp, lat, lon, alt_m, gps_quality, pm25, pm10,
                             temperature, humidity, pressure, voc, mq135_raw, quality_flag)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            d["timestamp"], d["lat"], d["lon"], d["alt_m"], d["gps_quality"],
                            d["pm25"], d["pm10"], d["temperature"], d["humidity"], d["pressure"],
                            d["voc"], d["mq135_raw"], d["quality_flag"]
                        ))
                        db_conn.commit()
                    except Exception as e:
                        log.error(f"SQLite Write Error: {e}")

                    # Log to InfluxDB
                    if write_api:
                        try:
                            pt = make_influx_point(d, rssi)
                            write_api.write(bucket=INFLUX_BUCKET, record=pt)
                        except Exception as e:
                            log.warning(f"InfluxDB write failed: {e}")

            time.sleep(0.02)  # 50 Hz loop

    except KeyboardInterrupt:
        log.info("Interrupted. Stopping ground station...")
    finally:
        running = False
        if lora_enabled:
            spi.close()
            GPIO.cleanup()
        if influx_client:
            influx_client.close()
        db_conn.close()
        log.info("Ground station stopped.")

if __name__ == "__main__":
    main()
