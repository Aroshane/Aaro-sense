#include <SPI.h>
#include <LoRa.h>

// ============================================================================
// HARDWARE ARCHITECTURE CONFIGURATION
// ============================================================================
const int SCK_PIN   = 13; // Hardware SPI Clock
const int MISO_PIN  = 12; // Hardware SPI MISO
const int MOSI_PIN  = 11; // Hardware SPI MOSI
const int CS_PIN    = 10; // NSS / Chip Select
const int RST_PIN   = 9;  // Reset Pin
const int DIO0_PIN  = 2;  // RX/TX Completion Interrupt

const long RF_FREQUENCY = 433E6; // 433 MHz Band

void setup() {
  // Initialize USB-Serial Link to host laptop
  Serial.begin(115200);
  while (!Serial); // Wait for USB CDC terminal to mount

  Serial.println("\n==================================================");
  Serial.println("     AEROSENSE GROUND STATION RADIO RECEIVER      ");
  Serial.println("==================================================");
  Serial.println("Initializing SX1276 SPI LoRa Module Hardware...");

  // Override and explicitly set the SPI Pins for the Nano architecture
  LoRa.setPins(CS_PIN, RST_PIN, DIO0_PIN);

  // Set up RF front-end registers
  if (!LoRa.begin(RF_FREQUENCY)) {
    Serial.println("❌ Critical Error: SX1276 Hardware Initialization Failed!");
    Serial.println("Verify your hardware connections and VCC lines.");
    while (1); // Halt execution to prevent register corruption
  }

  // Optimize LoRa modem settings for telemetry stability over range
  LoRa.setSignalBandwidth(125E3); // 125 kHz bandwidth
  LoRa.setSpreadingFactor(7);     // SF7 for fast throughput matching MessagePack bursts
  LoRa.setCodingRate4(5);         // CR 4/5 error correction
  LoRa.enableCrc();               // Enforce hardware payload CRC validation

  Serial.print("SX1276 locked on frequency: ");
  Serial.print(RF_FREQUENCY / 1E6);
  Serial.println(" MHz");
  Serial.println("Radio Layer Online. Listening for incoming payload packets...\n");
}

void loop() {
  // Poll register for incoming packet size over the air
  int packetSize = LoRa.parsePacket();
  
  if (packetSize) {
    // Read raw packet stream character by character
    while (LoRa.available()) {
      uint8_t rawByte = (uint8_t)LoRa.read();
      
      // Send the raw byte payload straight over USB-Serial to the host machine.
      // Your Python ground script will ingest this byte array and decode the MessagePack frame.
      Serial.write(rawByte);
    }
  }
}
