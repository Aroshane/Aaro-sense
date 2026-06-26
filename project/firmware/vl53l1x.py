import time
import struct

class VL53L1X:
    def __init__(self, i2c, address=0x29):
        self.i2c = i2c
        self.address = address
        
        # Check model ID to confirm chip presence (address size is 16-bit)
        try:
            model_id = self.read_reg16(0x010F)
        except Exception as e:
            raise OSError(f"Could not communicate with VL53L1X at 0x{address:02X}: {e}")

        if model_id != 0xEAEE:
            raise OSError(f"Unexpected VL53L1X model ID: 0x{model_id:04X} (expected 0xEAEE)")
            
        self.init_sensor()

    def write_reg8(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, bytes([val]), addrsize=16)

    def write_reg16(self, reg, val):
        self.i2c.writeto_mem(self.address, reg, struct.pack(">H", val), addrsize=16)

    def read_reg8(self, reg):
        return self.i2c.readfrom_mem(self.address, reg, 1, addrsize=16)[0]

    def read_reg16(self, reg):
        return struct.unpack(">H", self.i2c.readfrom_mem(self.address, reg, 2, addrsize=16))[0]

    def init_sensor(self):
        # Default tuning configuration values from ST API
        init_seq = [
            (0x002D, 0x00), (0x002F, 0x01), (0x0030, 0x01), (0x0031, 0x00),
            (0x0032, 0x02), (0x0033, 0x08), (0x0034, 0x00), (0x0035, 0x08),
            (0x0036, 0x10), (0x0037, 0x01), (0x003F, 0x00), (0x0040, 0x02),
            (0x0041, 0x0F), (0x0042, 0x01), (0x0043, 0x00), (0x0044, 0x00),
            (0x0045, 0x20), (0x0046, 0x0B), (0x0047, 0x00), (0x0048, 0x00),
            (0x004A, 0x0A), (0x004B, 0x00), (0x004C, 0x00), (0x004D, 0x00),
            (0x004E, 0x00), (0x004F, 0x00), (0x0050, 0x00), (0x0051, 0x00),
            (0x0052, 0x00), (0x0053, 0x00), (0x0054, 0x00), (0x0055, 0x00),
            (0x0056, 0x00), (0x0057, 0x00), (0x0058, 0x00), (0x0059, 0x00),
            (0x005A, 0x00), (0x005B, 0x00), (0x005C, 0x00), (0x005D, 0x00),
            (0x005E, 0x00), (0x005F, 0x00), (0x0060, 0x00), (0x0061, 0x00),
            (0x0062, 0x00), (0x0063, 0x00), (0x0064, 0x00), (0x0065, 0x00),
            (0x0066, 0x00), (0x0067, 0x00), (0x0068, 0x00), (0x0069, 0x00),
            (0x006A, 0x00), (0x006B, 0x00), (0x006C, 0x00), (0x006D, 0x00),
            (0x006E, 0x01), (0x006F, 0x00), (0x0070, 0x02), (0x0071, 0x01),
            (0x0072, 0x07), (0x0073, 0x02), (0x0074, 0x07), (0x0075, 0x05),
            (0x0076, 0x00), (0x0077, 0x05), (0x0078, 0x43), (0x0079, 0x03),
            (0x007A, 0x00), (0x007B, 0x08), (0x007C, 0x00), (0x007D, 0x02),
            (0x007E, 0x0A), (0x007F, 0x21), (0x0080, 0x00), (0x0081, 0x00),
            (0x0082, 0x00), (0x0083, 0x00), (0x0084, 0x00), (0x0085, 0x00),
            (0x0086, 0x01), (0x0087, 0x00)
        ]
        for reg, val in init_seq:
            self.write_reg8(reg, val)
            
        # Complete system boot
        self.write_reg8(0x0087, 0x40)
        self.set_distance_mode(2)    # Default: Long Range
        self.set_timing_budget(100)  # Default: 100ms

    def set_distance_mode(self, mode):
        # 1 = Short Range (up to 1.3m), 2 = Long Range (up to 4.0m)
        if mode == 1:
            self.write_reg8(0x006D, 0x11)
            self.write_reg8(0x006E, 0x07)
            self.write_reg8(0x006F, 0x05)
        elif mode == 2:
            self.write_reg8(0x006D, 0x12)
            self.write_reg8(0x006E, 0x0F)
            self.write_reg8(0x006F, 0x05)

    def set_timing_budget(self, budget_ms):
        if budget_ms == 20:
            self.write_reg16(0x0070, 0x0013)
        elif budget_ms == 33:
            self.write_reg16(0x0070, 0x0022)
        elif budget_ms == 50:
            self.write_reg16(0x0070, 0x0030)
        elif budget_ms == 100:
            self.write_reg16(0x0070, 0x0046)
        elif budget_ms == 200:
            self.write_reg16(0x0070, 0x008F)
        elif budget_ms == 500:
            self.write_reg16(0x0070, 0x01D3)

    def start_ranging(self):
        self.write_reg8(0x0060, 0x01)

    def stop_ranging(self):
        self.write_reg8(0x0060, 0x00)

    @property
    def data_ready(self):
        # Data ready is active-low on interrupt register status bit 0
        return (self.read_reg8(0x004F) & 0x01) == 0

    @property
    def distance(self):
        # Ranging distance returned in millimeters
        return self.read_reg16(0x0096)

    def clear_interrupt(self):
        self.write_reg8(0x0086, 0x01)
