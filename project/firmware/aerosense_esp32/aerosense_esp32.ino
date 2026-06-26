/*
  AeroSense Payload Firmware — aerosense_esp32.ino
  ESP32 | Arduino C++

  Features:
    - Multi-sensor air quality logging (PMS5003, BME280, MQ135, Autopilot GPS)
    - Real-time telemetry via WiFi UDP (MessagePack) and LoRa SX1276
    - Ingests GPS telemetry directly from Pixhawk autopilot via MAVLink #33
    - Cooperative multitasking using non-blocking millis() timing
    - Optimizations: Removed redundant SD card, VL53L1X, and HC-SR04 avoidance modules

  Libraries required (Install via Arduino Library Manager):
    1. Adafruit BME280 Library
*/

#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <SPI.h>
#include <Adafruit_BMP280.h>
// MAVLink parsing is handled natively in the sketch without external library dependencies

// ═════════════════════════════════════════════════════════════════════════════
// CONFIGURATION & PIN MAPS
// ═════════════════════════════════════════════════════════════════════════════
const char* WIFI_SSID = "Rande mind";
const char* WIFI_PASS = "Aromal18#";
const char* GS_IP     = "192.168.4.1";
const int   GS_PORT   = 5005;

// I2C Pins (Standard ESP32 I2C pins)
#define I2C_SDA_PIN   21
#define I2C_SCL_PIN   22

// SPI Pins (Shared standard VSPI bus for ESP32)
#define SPI_SCK_PIN   18
#define SPI_MISO_PIN  19
#define SPI_MOSI_PIN  23
#define LORA_CS_PIN    5

// LoRa Control Pins
#define LORA_RST_PIN  14
#define LORA_DIO0_PIN  4

// Serial Pins (Hardware Serial mapping)
#define PMS_RX_PIN    26 // Hardware UART2 RX (Wire 5)
#define PMS_TX_PIN    27 // Hardware UART2 TX (Wire 4)
#define MAV_TX_PIN    25 // Hardware UART1 TX
#define MAV_RX_PIN    33 // Hardware UART1 RX

// MQ-135 Gas Sensor Analog Pin
#define MQ135_ADC_PIN 34

// Calibration Offsets
const float PM25_OFFSET     = 0.0;
const float PM10_OFFSET     = 0.0;
const float TEMP_OFFSET     = -1.5;
const float HUMIDITY_OFFSET = 2.0;
const float MQ135_SCALE     = 1.0;

// ═════════════════════════════════════════════════════════════════════════════
// INSTANCES & DATA STRUCTURES
// ═════════════════════════════════════════════════════════════════════════════
WiFiUDP udp;
Adafruit_BMP280 bme(&Wire); // Pass Wire reference to constructor
SPIClass spi_bus(HSPI);

struct PollutionPoint {
  uint32_t timestamp;
  double lat;
  double lon;
  double alt_m;
  int gps_quality;
  double pm25;
  double pm10;
  double temp;
  double hum;
  double press;
  double voc;
  double mq135_v;
  int quality_flag;
};

// Global telemetry reading
PollutionPoint currentPoint;
bool loraOk = false;
bool bmeOk = false;

// Hardware Serial 1 for MAVLink, Hardware Serial 2 for PMS5003
HardwareSerial SerialMAV(1);
HardwareSerial SerialPMS(2);

// Time counters for non-blocking loop execution
unsigned long lastPayloadTime = 0;
unsigned long lastMAVLinkGPSUpdate = 0;
uint8_t mav_seq = 0;

// ── LoRa Registers ────────────────────────────────────────────────────────────
#define REG_FIFO           0x00
#define REG_OP_MODE        0x01
#define REG_FRF_MSB        0x06
#define REG_FRF_MID        0x07
#define REG_FRF_LSB        0x08
#define REG_PA_CONFIG      0x09
#define REG_FIFO_ADDR_PTR  0x0D
#define REG_FIFO_TX_BASE   0x0E
#define REG_IRQ_FLAGS      0x12
#define REG_PAYLOAD_LEN    0x22
#define REG_MODEM_CONFIG_1 0x1D
#define REG_MODEM_CONFIG_2 0x1E
#define REG_MODEM_CONFIG_3 0x26
#define REG_SYNC_WORD      0x39
#define MODE_SLEEP         0x80
#define MODE_STDBY         0x81
#define MODE_TX            0x83

// ═════════════════════════════════════════════════════════════════════════════
// LORA DEVICE FUNCTIONS
// ═════════════════════════════════════════════════════════════════════════════
void loraWriteReg(uint8_t reg, uint8_t val) {
  spi_bus.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  digitalWrite(LORA_CS_PIN, LOW);
  spi_bus.transfer(reg | 0x80);
  spi_bus.transfer(val);
  digitalWrite(LORA_CS_PIN, HIGH);
  spi_bus.endTransaction();
}

uint8_t loraReadReg(uint8_t reg) {
  spi_bus.beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
  digitalWrite(LORA_CS_PIN, LOW);
  spi_bus.transfer(reg & 0x7F);
  uint8_t val = spi_bus.transfer(0x00);
  digitalWrite(LORA_CS_PIN, HIGH);
  spi_bus.endTransaction();
  return val;
}

bool loraInit() {
  pinMode(LORA_RST_PIN, OUTPUT);
  pinMode(LORA_CS_PIN, OUTPUT);
  pinMode(LORA_DIO0_PIN, INPUT);
  digitalWrite(LORA_CS_PIN, HIGH);

  // Hard Reset
  digitalWrite(LORA_RST_PIN, LOW);
  delay(10);
  digitalWrite(LORA_RST_PIN, HIGH);
  delay(10);

  uint8_t version = loraReadReg(0x42);
  if (version != 0x12) {
    Serial.printf("[LoRa] SX1276 version mismatch: 0x%02X\n", version);
    return false;
  }

  loraWriteReg(REG_OP_MODE, MODE_SLEEP);
  delay(10);

  // Set frequency to 433 MHz
  // frf = (Freq * 1e6) / 61.03515625 = 7094272 -> 0x6C0000
  loraWriteReg(REG_FRF_MSB, 0x6C);
  loraWriteReg(REG_FRF_MID, 0x40);
  loraWriteReg(REG_FRF_LSB, 0x00);

  loraWriteReg(REG_PA_CONFIG, 0x8F);      // PA Boost
  loraWriteReg(REG_MODEM_CONFIG_1, 0x72); // BW=125kHz, CR=4/5, Explicit Header
  loraWriteReg(REG_MODEM_CONFIG_2, 0x74); // SF=7, CRC On
  loraWriteReg(REG_MODEM_CONFIG_3, 0x04); // LNA AGC On
  loraWriteReg(REG_SYNC_WORD, 0x12);
  loraWriteReg(REG_FIFO_TX_BASE, 0x00);
  loraWriteReg(REG_OP_MODE, MODE_STDBY);

  Serial.println("[LoRa] SX1276 at 433 MHz Initialized.");
  return true;
}

bool loraTransmit(const uint8_t* data, uint8_t len) {
  if (!loraOk) return false;
  loraWriteReg(REG_OP_MODE, MODE_STDBY);
  loraWriteReg(REG_FIFO_ADDR_PTR, 0x00);
  loraWriteReg(REG_PAYLOAD_LEN, len);

  for (uint8_t i = 0; i < len; i++) {
    loraWriteReg(REG_FIFO, data[i]);
  }

  loraWriteReg(REG_IRQ_FLAGS, 0xFF); // clear irq
  loraWriteReg(REG_OP_MODE, MODE_TX);

  unsigned long deadline = millis() + 1000;
  while (millis() < deadline) {
    if (digitalRead(LORA_DIO0_PIN)) {
      loraWriteReg(REG_IRQ_FLAGS, 0xFF);
      loraWriteReg(REG_OP_MODE, MODE_STDBY);
      return true;
    }
    delay(2);
  }
  return false; // timeout
}

// ═════════════════════════════════════════════════════════════════════════════
// SENSORS READING
// ═════════════════════════════════════════════════════════════════════════════
bool readPMS5003(double &pm25, double &pm10) {
  if (SerialPMS.available() < 32) return false;
  
  // Align with header 0x42, 0x4D
  while (SerialPMS.available() > 0) {
    if (SerialPMS.read() == 0x42) {
      if (SerialPMS.peek() == 0x4D) {
        SerialPMS.read(); // Consume 0x4D
        break;
      }
    }
  }

  uint8_t buffer[30];
  if (SerialPMS.readBytes(buffer, 30) < 30) return false;

  uint16_t checksum_calc = 0x42 + 0x4D;
  for (int i = 0; i < 28; i++) {
    checksum_calc += buffer[i];
  }
  uint16_t checksum_recv = (buffer[28] << 8) | buffer[29];
  if (checksum_calc != checksum_recv) return false;

  // Atmospheric PM2.5 (bytes 10-11) & PM10 (bytes 12-13)
  int pm25_raw = (buffer[10] << 8) | buffer[11];
  int pm10_raw = (buffer[12] << 8) | buffer[13];

  pm25 = max(0.0, (double)(pm25_raw + PM25_OFFSET));
  pm10 = max(0.0, (double)(pm10_raw + PM10_OFFSET));
  return true;
}

double readMQ135() {
  int raw = analogRead(MQ135_ADC_PIN);
  // ESP32 12-bit ADC (0-4095) representing 0-3.3V
  double voltage = (raw / 4095.0) * 3.3 * MQ135_SCALE;
  return voltage;
}

// ═════════════════════════════════════════════════════════════════════════════
// MESSAGEPACK MANUAL ENCODING (Optimized with 0xCA float32)
// ═════════════════════════════════════════════════════════════════════════════
void packDoubleMsgpack(uint8_t* buf, int &offset, double val) {
  buf[offset++] = 0xCB;
  union {
    double d;
    uint8_t b[8];
  } u;
  u.d = val;
  for (int i = 7; i >= 0; i--) {
    buf[offset++] = u.b[i];
  }
}

void packFloatMsgpack(uint8_t* buf, int &offset, float val) {
  buf[offset++] = 0xCA;
  union {
    float f;
    uint8_t b[4];
  } u;
  u.f = val;
  for (int i = 3; i >= 0; i--) {
    buf[offset++] = u.b[i];
  }
}

void packIntMsgpack(uint8_t* buf, int &offset, int val) {
  if (val >= 0 && val <= 127) {
    buf[offset++] = (uint8_t)val;
  } else if (val >= -32 && val < 0) {
    buf[offset++] = 0xE0 | (val + 32);
  } else if (val >= 0 && val < 256) {
    buf[offset++] = 0xCC;
    buf[offset++] = (uint8_t)val;
  } else {
    buf[offset++] = 0xCD;
    buf[offset++] = (val >> 8) & 0xFF;
    buf[offset++] = val & 0xFF;
  }
}

int packPointMessagepack(uint8_t* buf, const PollutionPoint &pt) {
  int offset = 0;
  buf[offset++] = 0x9D; // fixarray (13 elements)

  packDoubleMsgpack(buf, offset, (double)pt.timestamp);
  packDoubleMsgpack(buf, offset, pt.lat);
  packDoubleMsgpack(buf, offset, pt.lon);
  packFloatMsgpack(buf, offset, (float)pt.alt_m);
  packIntMsgpack(buf, offset, pt.gps_quality);
  packFloatMsgpack(buf, offset, (float)pt.pm25);
  packFloatMsgpack(buf, offset, (float)pt.pm10);
  packFloatMsgpack(buf, offset, (float)pt.temp);
  packFloatMsgpack(buf, offset, (float)pt.hum);
  packFloatMsgpack(buf, offset, (float)pt.press);
  packFloatMsgpack(buf, offset, (float)pt.voc);
  packFloatMsgpack(buf, offset, (float)pt.mq135_v);
  packIntMsgpack(buf, offset, pt.quality_flag);

  return offset;
}

// ═════════════════════════════════════════════════════════════════════════════
// MAVLINK V2 TELEMETRY INGESTION (No library dependency)
// ═════════════════════════════════════════════════════════════════════════════
uint16_t crcAccumulate(uint8_t b, uint16_t crc) {
  uint8_t ch = b ^ (crc & 0x00FF);
  ch ^= (ch << 4);
  return (crc >> 8) ^ (ch << 8) ^ (ch << 3) ^ (ch >> 4);
}

void readIncomingMAVLink() {
  static uint8_t rx_buf[1024];
  static int rx_len = 0;

  while (SerialMAV.available() > 0) {
    if (rx_len >= 1024) {
      // Discard older half of buffer to prevent overflow
      memmove(rx_buf, rx_buf + 512, 512);
      rx_len = 512;
    }
    rx_buf[rx_len++] = SerialMAV.read();
  }

  // Parse packets from buffer
  int parse_idx = 0;
  while (parse_idx < rx_len) {
    // Find MAVLink v2 magic byte (0xFD)
    int magic_idx = -1;
    for (int i = parse_idx; i < rx_len; i++) {
      if (rx_buf[i] == 0xFD) {
        magic_idx = i;
        break;
      }
    }

    if (magic_idx == -1) {
      rx_len = 0;
      break;
    }

    parse_idx = magic_idx;
    if (rx_len - parse_idx < 10) {
      break; // Need at least the 10-byte header
    }

    uint8_t payload_len = rx_buf[parse_idx + 1];
    uint32_t msg_id = rx_buf[parse_idx + 7] | (rx_buf[parse_idx + 8] << 8) | (rx_buf[parse_idx + 9] << 16);
    int total_len = 10 + payload_len + 2; // Header + Payload + Checksum

    if (rx_len - parse_idx < total_len) {
      break; // Incomplete packet, wait for more bytes
    }

    // CRC Validation
    uint16_t crc = 0xFFFF;
    for (int i = 1; i < 10; i++) {
      crc = crcAccumulate(rx_buf[parse_idx + i], crc);
    }
    for (int i = 0; i < payload_len; i++) {
      crc = crcAccumulate(rx_buf[parse_idx + 10 + i], crc);
    }

    uint8_t crc_extra = 0;
    bool has_crc_extra = false;
    if (msg_id == 33) {
      crc_extra = 104; // GLOBAL_POSITION_INT
      has_crc_extra = true;
    } else if (msg_id == 0) {
      crc_extra = 50;  // HEARTBEAT
      has_crc_extra = true;
    }

    uint16_t crc_recv;
    memcpy(&crc_recv, rx_buf + parse_idx + 10 + payload_len, 2);

    if (has_crc_extra) {
      uint16_t crc_calc = crcAccumulate(crc_extra, crc);
      if (crc_calc == crc_recv) {
        if (msg_id == 33) {
          // Extract lat, lon, alt from GLOBAL_POSITION_INT payload
          int32_t lat_val, lon_val, alt_val;
          memcpy(&lat_val, rx_buf + parse_idx + 10 + 4, 4);
          memcpy(&lon_val, rx_buf + parse_idx + 10 + 8, 4);
          memcpy(&alt_val, rx_buf + parse_idx + 10 + 12, 4);

          currentPoint.lat = lat_val / 10000000.0;
          currentPoint.lon = lon_val / 10000000.0;
          currentPoint.alt_m = alt_val / 1000.0; // mm -> m
          currentPoint.gps_quality = 3;
          lastMAVLinkGPSUpdate = millis();
        } else if (msg_id == 0) {
          // ----------- HEARTBEAT ALERT -----------
          Serial.println("[MAVLink Alert] Heartbeat packet successfully parsed from SpeedyBee!");
          // ----------------------------------------
        }
      }
    }

    parse_idx += total_len;
  }

  // Shift parsed data out of the buffer
  if (parse_idx > 0) {
    if (parse_idx < rx_len) {
      memmove(rx_buf, rx_buf + parse_idx, rx_len - parse_idx);
      rx_len -= parse_idx;
    } else {
      rx_len = 0;
    }
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);                                        // USB debug port
  SerialMAV.begin(57600, SERIAL_8N1, MAV_RX_PIN, MAV_TX_PIN);  // UART1 for MAVLink to Autopilot
  
  // Wait up to 3 seconds for Serial Monitor to connect (useful for USB CDC debug)
  unsigned long startWait = millis();
  while (!Serial && (millis() - startWait < 3000)) {
    delay(10);
  }
  Serial.println("\n--- AeroSense Booting ---");

  // Initialize Hardware Buses (I2C & SPI)
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 100000);
  spi_bus.begin(SPI_SCK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN);

  // Scan I2C bus for troubleshooting
  Serial.println("[I2C] Scanning bus...");
  int nDevices = 0;
  for (byte address = 8; address < 120; address++) {
    Wire.beginTransmission(address);
    byte error = Wire.endTransmission();
    if (error == 0) {
      Serial.printf("[I2C] Device found at address 0x%02X\n", address);
      nDevices++;
    } else if (error == 4) {
      Serial.printf("[I2C] Unknown error at address 0x%02X\n", address);
    }
  }
  if (nDevices == 0) {
    Serial.println("[I2C] No devices found on the bus!");
  } else {
    Serial.printf("[I2C] Scan complete. Found %d device(s).\n", nDevices);
    
    // Read Chip ID from 0x76 to verify if it is BME280 (0x60) or BMP280 (0x58)
    Wire.beginTransmission(0x76);
    Wire.write(0xD0); // Chip ID register
    byte error = Wire.endTransmission();
    if (error == 0) {
      Wire.requestFrom(0x76, 1);
      if (Wire.available()) {
        byte chipID = Wire.read();
        Serial.printf("[I2C Diagnostic] Chip ID at 0x76 is 0x%02X\n", chipID);
        if (chipID == 0x58) {
          Serial.println("[I2C Diagnostic] Sensor is a BMP280 (Pressure/Temp only, no Humidity).");
        } else if (chipID == 0x60) {
          Serial.println("[I2C Diagnostic] Sensor is a BME280 (Temp/Humidity/Pressure).");
        } else {
          Serial.println("[I2C Diagnostic] Unknown sensor chip ID.");
        }
      } else {
        Serial.println("[I2C Diagnostic] Failed to read from register 0xD0 on 0x76.");
      }
    } else {
      Serial.println("[I2C Diagnostic] Failed to connect to 0x76 for Chip ID read.");
    }
  }

  // Start UART2 for PMS5003 (9600 baud)
  SerialPMS.begin(9600, SERIAL_8N1, PMS_RX_PIN, PMS_TX_PIN);

  // Configure Internal ADC pin for MQ-135
  analogReadResolution(12);
  pinMode(MQ135_ADC_PIN, INPUT);

  // Connect WiFi STA
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("\n[WiFi] Connecting to %s...\n", WIFI_SSID);
  int wTime = 0;
  while (WiFi.status() != WL_CONNECTED && wTime < 20) {
    delay(500);
    wTime++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[WiFi] Connection timed out. Running without UDP.");
  }

  // Initialize BMP280
  bmeOk = bme.begin(0x76);
  if (bmeOk) {
    Serial.println("[BMP280] Sensor initialized successfully.");
  } else {
    Serial.println("[BMP280] Sensor not found! Check address (0x76/0x77) or wiring.");
  }

  // PMS5003 Diagnostic Check
  Serial.println("[PMS5003 Diagnostic] Listening for sensor data (3s timeout)...");
  unsigned long startPMS = millis();
  uint8_t pmsDump[64];
  int dumpCount = 0;
  bool pmsPacketParsed = false;
  double test_pm25 = 0, test_pm10 = 0;

  while (millis() - startPMS < 3000 && dumpCount < 64) {
    while (SerialPMS.available() > 0 && dumpCount < 64) {
      pmsDump[dumpCount++] = SerialPMS.read();
    }
    delay(10);
  }

  if (dumpCount > 0) {
    // Try to find the 0x42 0x4D header in the captured dump
    int headerIdx = -1;
    for (int i = 0; i < dumpCount - 1; i++) {
      if (pmsDump[i] == 0x42 && pmsDump[i+1] == 0x4D) {
        headerIdx = i;
        break;
      }
    }

    if (headerIdx != -1 && dumpCount - headerIdx >= 32) {
      // Validate checksum for the 32-byte frame
      uint16_t checksum_calc = 0x42 + 0x4D;
      for (int i = headerIdx + 2; i < headerIdx + 30; i++) {
        checksum_calc += pmsDump[i];
      }
      uint16_t checksum_recv = (pmsDump[headerIdx + 30] << 8) | pmsDump[headerIdx + 31];
      if (checksum_calc == checksum_recv) {
        int pm25_raw = (pmsDump[headerIdx + 12] << 8) | pmsDump[headerIdx + 13];
        int pm10_raw = (pmsDump[headerIdx + 14] << 8) | pmsDump[headerIdx + 15];
        test_pm25 = max(0.0, (double)(pm25_raw + PM25_OFFSET));
        test_pm10 = max(0.0, (double)(pm10_raw + PM10_OFFSET));
        pmsPacketParsed = true;
      }
    }

    if (pmsPacketParsed) {
      Serial.printf("[PMS5003 Diagnostic] SUCCESS! Communication verified. PM2.5: %.1f ug/m3, PM10: %.1f ug/m3\n", test_pm25, test_pm10);
    } else {
      Serial.println("[PMS5003 Diagnostic] WARNING: Received bytes on Serial, but failed to parse a valid packet (checksum/framing error).");
      Serial.print("[PMS5003 Diagnostic] Raw bytes received: ");
      for (int i = 0; i < dumpCount; i++) {
        Serial.printf("0x%02X ", pmsDump[i]);
      }
      Serial.println();
      Serial.println("[PMS5003 Diagnostic] Tip: If you see random changing bytes, it might be noise. If you see mostly 0x00 or 0xFF, the pin is likely floating (check RX/TX connection).");
    }
  } else {
    Serial.printf("[PMS5003 Diagnostic] FAILED: No serial data received. Check RX (GPIO %d) & TX (GPIO %d) wiring, power, and ground.\n", PMS_RX_PIN, PMS_TX_PIN);
  }

  // Initialize LoRa SX1276
  loraOk = loraInit();

  Serial.println("✅ AeroSense payload loop running...");
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN LOOP
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  // 1. Process incoming MAVLink telemetry from autopilot (specifically GPS)
  readIncomingMAVLink();

  unsigned long now = millis();

  // 2. Sensor Read and Telemetry Log Loop (1 Hz)
  if (now - lastPayloadTime >= 1000) {
    lastPayloadTime = now;

    // Read PMS5003
    double pm25 = -1.0, pm10 = -1.0;
    bool pmOk = readPMS5003(pm25, pm10);

    // Read BMP280
    double temp = -999.0, hum = -1.0, press = -1.0;
    if (bmeOk) {
      temp = bme.readTemperature() + TEMP_OFFSET;
      hum  = -1.0; // BMP280 does not have a humidity sensor
      press = bme.readPressure() / 100.0; // Pa -> hPa
    }

    // Read MQ135 voltage directly via internal ADC
    double mq_v = readMQ135();

    // Check Diagnostics
    int quality = 0;
    bool gps_healthy = (millis() - lastMAVLinkGPSUpdate) < 15000;
    if (!gps_healthy) {
      quality |= 0x01;
      currentPoint.gps_quality = 0;
    } else {
      currentPoint.gps_quality = 3;
    }
    if (!bmeOk) quality |= 0x02;
    if (!pmOk)  quality |= 0x04;

    // Build Payload Point
    currentPoint.timestamp = now / 1000;
    currentPoint.pm25 = pmOk ? pm25 : -1.0;
    currentPoint.pm10 = pmOk ? pm10 : -1.0;
    currentPoint.temp = bmeOk ? temp : -999.0;
    currentPoint.hum  = bmeOk ? hum : -1.0;
    currentPoint.press = bmeOk ? press : -1.0;
    currentPoint.voc = -1.0; // N/A on BME280
    currentPoint.mq135_v = mq_v;
    currentPoint.quality_flag = quality;

    // Pack to MessagePack binary format
    uint8_t packet_buf[150];
    int packet_len = packPointMessagepack(packet_buf, currentPoint);

    // Telemetry send over LoRa
    if (loraOk) {
      loraTransmit(packet_buf, packet_len);
    }

    // Telemetry send over WiFi UDP
    if (WiFi.status() == WL_CONNECTED) {
      udp.beginPacket(GS_IP, GS_PORT);
      udp.write(packet_buf, packet_len);
      udp.endPacket();
    }

    // Print diagnostic feed to Serial Monitor
    Serial.printf("[Diagnostic] GPS(%d) %.5f,%.5f Alt:%.1f | PM2.5:%.1f PM10:%.1f | T:%.1fC H:%.1f%% | MQ135:%.3fV | Q:0x%02X\n",
      currentPoint.gps_quality, currentPoint.lat, currentPoint.lon, currentPoint.alt_m,
      currentPoint.pm25, currentPoint.pm10, currentPoint.temp, currentPoint.hum,
      currentPoint.mq135_v, currentPoint.quality_flag
    );
  }
}
