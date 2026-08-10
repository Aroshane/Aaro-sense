import struct
import time

class BME280:
    def __init__(self, i2c, address=0x76):
        self.i2c = i2c
        self.address = address
        
        # Check chip ID to verify communication
        try:
            chip_id = self.i2c.readfrom_mem(self.address, 0xD0, 1)[0]
        except Exception as e:
            raise OSError(f"Could not read from BME280 at address 0x{address:02X}: {e}")

        if chip_id not in (0x58, 0x60):
            raise OSError(f"Unknown chip ID 0x{chip_id:02X} (expected 0x58 or 0x60)")
            
        self.has_humidity = (chip_id == 0x60)
        self.read_calibration()
        
        # Configure the sensor: humidity oversampling x1
        if self.has_humidity:
            self.i2c.writeto_mem(self.address, 0xF2, b'\x01')
            
        # temp x1, press x1, normal mode (ctrl_meas = 0x27)
        self.i2c.writeto_mem(self.address, 0xF4, b'\x27')
        
        # Standby 1000ms, filter off (config = 0xA0)
        self.i2c.writeto_mem(self.address, 0xF5, b'\xA0')
        self.t_fine = 0

    def read_calibration(self):
        # Read temperature and pressure calibration parameters
        cal1 = self.i2c.readfrom_mem(self.address, 0x88, 24)
        self.dig_T1, self.dig_T2, self.dig_T3, \
        self.dig_P1, self.dig_P2, self.dig_P3, self.dig_P4, self.dig_P5, \
        self.dig_P6, self.dig_P7, self.dig_P8, self.dig_P9 = struct.unpack("<HhhHhhhhhhhh", cal1)
        
        if self.has_humidity:
            # Read humidity calibration parameters
            self.dig_H1 = self.i2c.readfrom_mem(self.address, 0xA1, 1)[0]
            cal2 = self.i2c.readfrom_mem(self.address, 0xE1, 7)
            self.dig_H2 = struct.unpack("<h", cal2[0:2])[0]
            self.dig_H3 = cal2[2]
            
            # H4 & H5 are stored split across 3 bytes
            e4 = cal2[3]
            e5 = cal2[4]
            e6 = cal2[5]
            
            self.dig_H4 = (e4 << 4) | (e5 & 0x0F)
            if self.dig_H4 > 2047:
                self.dig_H4 -= 4096
                
            self.dig_H5 = (e6 << 4) | (e5 >> 4)
            if self.dig_H5 > 2047:
                self.dig_H5 -= 4096
                
            self.dig_H6 = struct.unpack("<b", cal2[6:7])[0]

    def read_raw(self):
        size = 8 if self.has_humidity else 6
        data = self.i2c.readfrom_mem(self.address, 0xF7, size)
        
        raw_press = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        raw_temp = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        raw_hum = (data[6] << 8) | data[7] if self.has_humidity else 0
        return raw_press, raw_temp, raw_hum

    def get_readings(self):
        raw_press, raw_temp, raw_hum = self.read_raw()
        
        # 1. Compensate Temperature
        var1 = (((raw_temp >> 3) - (self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (((((raw_temp >> 4) - self.dig_T1) * ((raw_temp >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        self.t_fine = var1 + var2
        temp = (self.t_fine * 5 + 128) >> 8
        temperature = temp / 100.0
        
        # 2. Compensate Pressure
        var1 = (self.t_fine >> 1) - 64000
        var2 = (((var1 >> 2) * (var1 >> 2)) >> 11) * self.dig_P6
        var2 = var2 + ((var1 * self.dig_P5) << 1)
        var2 = (var2 >> 2) + (self.dig_P4 << 16)
        var1 = (((self.dig_P3 * (((var1 >> 2) * (var1 >> 2)) >> 13)) >> 3) + ((self.dig_P2 * var1) >> 1)) >> 18
        var1 = ((32768 + var1) * self.dig_P1) >> 15
        
        if var1 == 0:
            pressure = 0.0
        else:
            p = ((1048576 - raw_press) - (var2 >> 12)) * 3125
            if p < 0x80000000:
                p = (p << 1) // var1
            else:
                p = (p // var1) * 2
            var1 = (self.dig_P9 * (((p >> 3) * (p >> 3)) >> 13)) >> 12
            var2 = (((p >> 2)) * self.dig_P8) >> 13
            pressure = (p + ((var1 + var2 + self.dig_P7) >> 4)) / 100.0
            
        # 3. Compensate Humidity
        humidity = 0.0
        if self.has_humidity:
            h = self.t_fine - 76800
            h = (((((raw_hum << 14) - (self.dig_H4 << 20) - (self.dig_H5 * h)) + 16384) >> 15) *
                 (((((((h * self.dig_H6) >> 10) * (((h * self.dig_H3) >> 11) + 32768)) >> 10) + 2097152) *
                   self.dig_H2 + 8192) >> 14))
            h = h - (((((h >> 15) * (h >> 15)) >> 7) * self.dig_H1) >> 4)
            h = 0 if h < 0 else h
            h = 419430400 if h > 419430400 else h
            humidity = (h >> 12) / 1024.0
            
        return temperature, humidity, pressure
