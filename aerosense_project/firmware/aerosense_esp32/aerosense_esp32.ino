/*
  AeroSense Payload Firmware — aerosense_esp32.ino
  ESP32 | Arduino C++

  Features:
    - Multi-sensor air quality logging (PMS5003, BME280, ADS1115+MQ135, GPS)
    - Real-time telemetry via WiFi UDP (MessagePack) and LoRa SX1276
    - Obstacle avoidance via VL53L1X ToF + HC-SR04 ultrasonic -> MAVLink v2 #330
    - Local CSV logging to external SPI MicroSD card module
    - Cooperative multitasking using non-blocking millis() timing

  Libraries required (Install via Arduino Library Manager):
    1. Adafruit BME280 Library
    2. VL53L1X (by Pololu)
    3. EspSoftwareSerial (Usually built into the ESP32 Arduino Core as <SoftwareSerial.h>)
*/

#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>
#include <SPI.h>
#include <SD.h>
#include <Adafruit_BME280.h>
#include <VL53L1X.h>
#include <SoftwareSerial.h>

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
#define SD_CS_PIN      15

// LoRa Control Pins
#define LORA_RST_PIN  14
#define LORA_DIO0_PIN  4

// HC-SR04 Ultrasonic Pins (Sonar)
#define HC_TRIG_PIN   12
#define HC_ECHO_PIN   13

// Serial Pins (Hardware & Software Serial mapping)
#define PMS_TX_PIN    27
#define PMS_RX_PIN    26
#define GPS_TX_PIN    17
#define GPS_RX_PIN    16
#define MAV_TX_PIN    25
#define MAV_RX_PIN    33

// Calibration Offsets
const float PM25_OFFSET     = 0.0;
const float PM10_OFFSET     = 0.0;
const float TEMP_OFFSET     = -1.5;
const float HUMIDITY_OFFSET = 2.0;
const float MQ135_SCALE     = 1.0;

const float SAFETY_DISTANCE = 2.0; // warning threshold in meters

// ═════════════════════════════════════════════════════════════════════════════
// INSTANCES & DATA STRUCTURES
// ═════════════════════════════════════════════════════════════════════════════
WiFiUDP udp;
Adafruit_BME280 bme;
VL53L1X tof;
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
bool sdOk = false;
bool loraOk = false;
bool bmeOk = false;
bool tofOk = false;

// Hardware Serial 1 for MAVLink, Hardware Serial 2 for GPS
HardwareSerial SerialMAV(1);
HardwareSerial SerialGPS(2);

// SoftwareSerial for PMS5003 (9600 baud, low speed, perfect for software emulation)
SoftwareSerial SerialPMS;

// Time counters for non-blocking loop execution
unsigned long lastPayloadTime = 0;
unsigned long lastAvoidanceTime = 0;
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
  digitalWrite(LORA_CS_PIN, LOW);
  spi_bus.transfer(reg | 0x80);
  spi_bus.transfer(val);
  digitalWrite(LORA_CS_PIN, HIGH);
}

uint8_t loraReadReg(uint8_t reg) {
  digitalWrite(LORA_CS_PIN, LOW);
  spi_bus.transfer(reg & 0x7F);
  uint8_t val = spi_bus.transfer(0x00);
  digitalWrite(LORA_CS_PIN, HIGH);
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

  Serial.println("[LoRa] Initialized SX1276 at 433 MHz");
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
// SENSORS & GPS READING
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

double readADS1115() {
  // Config: single conversion on AIN0, +/-4.096V, 128SPS
  Wire.beginTransmission(0x48);
  Wire.write(0x01); // Config register pointer
  Wire.write(0xC3); // OS=1, MUX=100 (AIN0), PGA=001 (+/-4.096V), Mode=1 (single shot)
  Wire.write(0x85); // DR=100 (128SPS), Comp=unused
  Wire.endTransmission();

  delay(10);

  Wire.beginTransmission(0x48);
  Wire.write(0x00); // Conversion register pointer
  Wire.endTransmission();

  Wire.requestFrom(0x48, 2);
  if (Wire.available() < 2) return -1.0;
  int16_t val = (Wire.read() << 8) | Wire.read();
  
  // Scale parameter: 4.096V / 32768 LSB = 0.000125V per step
  return val * 0.000125 * MQ135_SCALE;
}

bool parseGGA(String line, double &lat, double &lon, double &alt, int &quality) {
  if (line.indexOf("GGA") == -1) return false;
  
  // Basic Checksum verification
  int astIdx = line.indexOf('*');
  if (astIdx != -1) {
    String body = line.substring(1, astIdx);
    int check_recv = strtol(line.substring(astIdx + 1).c_str(), NULL, 16);
    int check_calc = 0;
    for (unsigned int i = 0; i < body.length(); i++) {
      check_calc ^= body[i];
    }
    if (check_calc != check_recv) return false;
  }

  // Tokenize
  int commaIndex = 0;
  String parts[15];
  for (int i = 0; i < 15; i++) {
    int nextComma = line.indexOf(',', commaIndex);
    if (nextComma == -1) {
      parts[i] = line.substring(commaIndex);
      break;
    }
    parts[i] = line.substring(commaIndex, nextComma);
    commaIndex = nextComma + 1;
  }

  if (parts[6] == "" || parts[6].toInt() == 0) return false;
  quality = parts[6].toInt();

  // Latitude DDMM.MMMM
  String latStr = parts[2];
  if (latStr.length() > 2) {
    double latDeg = latStr.substring(0, 2).toFloat();
    double latMin = latStr.substring(2).toFloat();
    lat = latDeg + (latMin / 60.0);
    if (parts[3] == "S") lat = -lat;
  } else return false;

  // Longitude DDDMM.MMMM
  String lonStr = parts[4];
  if (lonStr.length() > 3) {
    double lonDeg = lonStr.substring(0, 3).toFloat();
    double lonMin = lonStr.substring(3).toFloat();
    lon = lonDeg + (lonMin / 60.0);
    if (parts[5] == "W") lon = -lon;
  } else return false;

  // Altitude
  alt = parts[9].toFloat();
  return true;
}

void processGPS() {
  while (SerialGPS.available() > 0) {
    String line = SerialGPS.readStringUntil('\n');
    double tempLat, tempLon, tempAlt;
    int tempQual;
    if (parseGGA(line, tempLat, tempLon, tempAlt, tempQual)) {
      currentPoint.lat = tempLat;
      currentPoint.lon = tempLon;
      currentPoint.alt_m = tempAlt;
      currentPoint.gps_quality = tempQual;
    }
  }
}

double readHCSR04() {
  digitalWrite(HC_TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(HC_TRIG_PIN, LOW);
  long duration = pulseIn(HC_ECHO_PIN, HIGH, 30000); // 30ms timeout
  if (duration == 0) return 4.0;
  double dist = duration * 0.0001715;
  return min(dist, 4.0);
}

// ═════════════════════════════════════════════════════════════════════════════
// MESSAGEPACK MANUAL ENCODING
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
  packDoubleMsgpack(buf, offset, pt.alt_m);
  packIntMsgpack(buf, offset, pt.gps_quality);
  packDoubleMsgpack(buf, offset, pt.pm25);
  packDoubleMsgpack(buf, offset, pt.pm10);
  packDoubleMsgpack(buf, offset, pt.temp);
  packDoubleMsgpack(buf, offset, pt.hum);
  packDoubleMsgpack(buf, offset, pt.press);
  packDoubleMsgpack(buf, offset, pt.voc);
  packDoubleMsgpack(buf, offset, pt.mq135_v);
  packIntMsgpack(buf, offset, pt.quality_flag);

  return offset;
}

// ═════════════════════════════════════════════════════════════════════════════
// MAVLINK V2 OBSTACLE_DISTANCE PACKER
// ═════════════════════════════════════════════════════════════════════════════
uint16_t crcAccumulate(uint8_t b, uint16_t crc) {
  uint8_t ch = b ^ (crc & 0x00FF);
  ch ^= (ch << 4);
  return (crc >> 8) ^ (ch << 8) ^ (ch << 3) ^ (ch >> 4);
}

void sendMAVLinkObstacleDistance(uint16_t front_cm, uint16_t right_cm) {
  uint16_t distances[72] = {0}; // 72 sectors of 5 degrees
  distances[0] = front_cm;      // Front sector (0 degrees)
  distances[18] = right_cm;     // Right sector (90 degrees / 5 = 18)

  uint8_t payload[167];
  uint64_t time_us = micros();
  uint16_t min_dist_cm = 10;
  uint16_t max_dist_cm = 400;
  float increment_f = 5.0f;
  float angle_offset = 0.0f;
  uint8_t frame = 12; // MAV_FRAME_BODY_FRD

  int offset = 0;
  memcpy(payload + offset, &time_us, 8); offset += 8;
  payload[offset++] = 0; // sensor_type (0 = Laser)
  for (int i = 0; i < 72; i++) {
    memcpy(payload + offset, &distances[i], 2); offset += 2;
  }
  payload[offset++] = 0; // increment (0)
  memcpy(payload + offset, &min_dist_cm, 2); offset += 2;
  memcpy(payload + offset, &max_dist_cm, 2); offset += 2;
  memcpy(payload + offset, &increment_f, 4); offset += 4;
  memcpy(payload + offset, &angle_offset, 4); offset += 4;
  payload[offset++] = frame;

  // Header MAVLink v2
  uint8_t header[10];
  header[0] = 0xFD; // STX
  header[1] = 167;  // Payload Len
  header[2] = 0;    // Incompat flags
  header[3] = 0;    // Compat flags
  header[4] = mav_seq;
  header[5] = 1;    // System ID
  header[6] = 1;    // Component ID
  header[7] = 0x4A; // MSG_ID (330 -> 0x014A) LSB
  header[8] = 0x01; // MSG_ID MSB
  header[9] = 0x00; // MSG_ID Upper
  
  mav_seq++;

  // Calculate CRC
  uint16_t crc = 0xFFFF;
  for (int i = 1; i < 10; i++) crc = crcAccumulate(header[i], crc);
  for (int i = 0; i < 167; i++) crc = crcAccumulate(payload[i], crc);
  crc = crcAccumulate(23, crc); // Extra CRC byte for MSG 330

  // Send packet to autopilot over SerialMAV (Hardware Serial 1)
  SerialMAV.write(header, 10);
  SerialMAV.write(payload, 167);
  SerialMAV.write((uint8_t*)&crc, 2);
}

// ═════════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);                                        // USB debug port
  SerialMAV.begin(57600, SERIAL_8N1, MAV_RX_PIN, MAV_TX_PIN);  // UART1 for MAVLink
  
  // Wait for serial configuration
  delay(100);

  // Initialize Hardware Buses
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN, 100000);
  spi_bus.begin(SPI_SCK_PIN, SPI_MISO_PIN, SPI_MOSI_PIN);

  // Start UARTs
  // SerialPMS is a SoftwareSerial instance: config RX and TX pins
  SerialPMS.begin(9600, SWSERIAL_8N1, PMS_RX_PIN, PMS_TX_PIN);
  
  // SerialGPS is a HardwareSerial instance: config RX and TX pins
  SerialGPS.begin(9600, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

  // Configure sensor pins
  pinMode(HC_TRIG_PIN, OUTPUT);
  pinMode(HC_ECHO_PIN, INPUT);
  digitalWrite(HC_TRIG_PIN, LOW);

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

  // Mount SD Card
  if (SD.begin(SD_CS_PIN, spi_bus)) {
    sdOk = true;
    Serial.println("[SD] MicroSD mounted successfully.");
    // Write CSV Header
    File logFile = SD.open("/flight.csv", FILE_WRITE);
    if (logFile) {
      logFile.println("timestamp_utc,lat,lon,alt_m,gps_quality,pm25_ugm3,pm10_ugm3,temp_c,humidity_pct,pressure_hpa,voc_ohm,mq135_v,quality_flag");
      logFile.close();
    }
  } else {
    Serial.println("[SD] MicroSD mount failed.");
  }

  // Init Sensors
  bmeOk = bme.begin(0x76, &Wire);
  if (bmeOk) Serial.println("[BME280] Connected.");
  
  tof.setTimeout(500);
  if (tof.init()) {
    tofOk = true;
    tof.setDistanceMode(VL53L1X::Long);
    tof.setMeasurementTimingBudget(100000);
    tof.startContinuous(100);
    Serial.println("[VL53L1X] Connected.");
  }

  loraOk = loraInit();

  Serial.println("✅ AeroSense payload loop running...");
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN LOOP
// ═════════════════════════════════════════════════════════════════════════════
void loop() {
  // 1. Process serial incoming GPS data
  processGPS();

  unsigned long now = millis();

  // 2. Obstacle Avoidance loop (10 Hz)
  if (now - lastAvoidanceTime >= 100) {
    lastAvoidanceTime = now;
    
    double front_m = 4.0;
    if (tofOk && tof.dataReady()) {
      front_m = tof.read(false) / 1000.0; // mm -> m
    }
    double right_m = readHCSR04(); // ultrasonic

    uint16_t front_cm = (uint16_t)(front_m * 100);
    uint16_t right_cm = (uint16_t)(right_m * 100);

    sendMAVLinkObstacleDistance(front_cm, right_cm);

    // Print warning flags to hardware serial monitor for debug
    if (front_m < SAFETY_DISTANCE) {
      Serial.printf("[Avoidance] WARNING: Front obstacle at %.2f m!\n", front_m);
    }
    if (right_m < SAFETY_DISTANCE) {
      Serial.printf("[Avoidance] WARNING: Right obstacle at %.2f m!\n", right_m);
    }
  }

  // 3. Sensor Read and Telemetry log loop (1 Hz)
  if (now - lastPayloadTime >= 1000) {
    lastPayloadTime = now;

    // Read PMS5003
    double pm25 = -1.0, pm10 = -1.0;
    bool pmOk = readPMS5003(pm25, pm10);

    // Read BME280
    double temp = -999.0, hum = -1.0, press = -1.0;
    if (bmeOk) {
      temp = bme.readTemperature() + TEMP_OFFSET;
      hum  = bme.readHumidity() + HUMIDITY_OFFSET;
      press = bme.readPressure() / 100.0; // Pa -> hPa
    }

    // Read MQ135 voltage
    double mq_v = readADS1115();

    // Check Diagnostics
    int quality = 0;
    if (currentPoint.gps_quality == 0) quality |= 0x01;
    if (!bmeOk)                         quality |= 0x02;
    if (!pmOk)                          quality |= 0x04;

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

    // Write to SD CSV
    if (sdOk) {
      File logFile = SD.open("/flight.csv", FILE_APPEND);
      if (logFile) {
        logFile.printf("%lu,%.6f,%.6f,%.1f,%d,%.2f,%.2f,%.2f,%.2f,%.2f,%.1f,%.4f,%d\n",
          currentPoint.timestamp, currentPoint.lat, currentPoint.lon, currentPoint.alt_m,
          currentPoint.gps_quality, currentPoint.pm25, currentPoint.pm10, currentPoint.temp,
          currentPoint.hum, currentPoint.press, currentPoint.voc, currentPoint.mq135_v,
          currentPoint.quality_flag
        );
        logFile.close();
      }
    }

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

    // Print diagnostic feed
    Serial.printf("[Diagnostic] GPS(%d) %.5f,%.5f Alt:%.1f | PM2.5:%.1f PM10:%.1f | T:%.1fC H:%.1f%% | Q:0x%02X\n",
      currentPoint.gps_quality, currentPoint.lat, currentPoint.lon, currentPoint.alt_m,
      currentPoint.pm25, currentPoint.pm10, currentPoint.temp, currentPoint.hum,
      currentPoint.quality_flag
    );
  }
}
