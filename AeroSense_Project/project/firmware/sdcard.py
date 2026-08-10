# MicroPython driver for SD cards using SPI
import time

class SDCard:
    def __init__(self, spi, cs):
        self.spi = spi
        self.cs = cs

        self.cmdbuf = bytearray(6)
        self.dummybuf = bytearray(512)
        self.tokenbuf = bytearray(1)
        for i in range(512):
            self.dummybuf[i] = 0xFF
        self.dummybuf_memoryview = memoryview(self.dummybuf)

        self.init_card()

    def init_card(self):
        self.cs.init(self.cs.OUT, value=1)

        # Clock card at least 74 cycles with CS high
        for i in range(16):
            self.spi.write(b"\xff")

        # CMD0: go to idle state
        if self.cmd(0, 0, 0x95) != 1:
            raise OSError("no SD card found")

        # CMD8: check voltage range
        r = self.cmd(8, 0x1AA, 0x87, 4)
        if r == 1:
            self.init_card_v2()
        else:
            self.init_card_v1()

    def init_card_v1(self):
        for i in range(100):
            self.cmd(55, 0, 0)
            if self.cmd(41, 0, 0) == 0:
                self.cdv = 512
                self.cmd(16, 512, 0) # set block size to 512
                return
            time.sleep_ms(10)
        raise OSError("SD v1 init failed")

    def init_card_v2(self):
        for i in range(100):
            time.sleep_ms(50)
            self.cmd(55, 0, 0)
            r = self.cmd(41, 0x40000000, 0)
            if r == 0:
                self.cmd(58, 0, 0, 4)
                if self.tokenbuf[0] & 0x40:
                    self.cdv = 1
                else:
                    self.cdv = 512
                    self.cmd(16, 512, 0)
                return
        raise OSError("SD v2 init failed")

    def cmd(self, cmd, arg, crc, final=0):
        self.cs(0)

        # Send CMD and arguments
        self.cmdbuf[0] = 0x40 | cmd
        self.cmdbuf[1] = (arg >> 24) & 0xFF
        self.cmdbuf[2] = (arg >> 16) & 0xFF
        self.cmdbuf[3] = (arg >> 8) & 0xFF
        self.cmdbuf[4] = arg & 0xFF
        self.cmdbuf[5] = crc
        self.spi.write(self.cmdbuf)

        # Wait for response
        for i in range(128):
            self.spi.readinto(self.tokenbuf, 0xFF)
            if not (self.tokenbuf[0] & 0x80):
                # Read final bytes if any
                if final:
                    for j in range(final):
                        self.spi.readinto(self.tokenbuf, 0xFF)
                self.cs(1)
                self.spi.write(b"\xff")
                return self.tokenbuf[0]

        self.cs(1)
        self.spi.write(b"\xff")
        return -1

    def readinto(self, buf):
        self.cs(0)

        # Read until start byte (0xFE)
        for i in range(10000):
            self.spi.readinto(self.tokenbuf, 0xFF)
            if self.tokenbuf[0] == 0xFE:
                break
        else:
            self.cs(1)
            raise OSError("SD card read timeout")

        # Read data
        self.spi.readinto(buf, 0xFF)

        # Read checksum
        self.spi.write(b"\xff\xff")
        self.cs(1)
        self.spi.write(b"\xff")

    def write(self, token, buf):
        self.cs(0)

        self.tokenbuf[0] = token
        self.spi.write(self.tokenbuf)
        self.spi.write(buf)
        self.spi.write(b"\xff\xff")

        # Wait for response
        for i in range(1000):
            self.spi.readinto(self.tokenbuf, 0xFF)
            if (self.tokenbuf[0] & 0x1F) == 0x05:
                break
        else:
            self.cs(1)
            raise OSError("SD card write timeout")

        # Wait for write to finish
        for i in range(1000000):
            self.spi.readinto(self.tokenbuf, 0xFF)
            if self.tokenbuf[0] == 0xFF:
                break
        else:
            self.cs(1)
            raise OSError("SD card write busy timeout")

        self.cs(1)
        self.spi.write(b"\xff")

    def readblocks(self, block_num, buf):
        nblocks = len(buf) // 512
        assert len(buf) % 512 == 0, "Buffer length must be a multiple of 512"
        if nblocks == 1:
            if self.cmd(17, block_num * self.cdv, 0) != 0:
                raise OSError("SD card read block failed")
            self.readinto(buf)
        else:
            if self.cmd(18, block_num * self.cdv, 0) != 0:
                raise OSError("SD card read blocks failed")
            offset = 0
            mv = memoryview(buf)
            for i in range(nblocks):
                self.readinto(mv[offset : offset + 512])
                offset += 512
            self.cmd(12, 0, 0)

    def writeblocks(self, block_num, buf):
        nblocks = len(buf) // 512
        assert len(buf) % 512 == 0, "Buffer length must be a multiple of 512"
        if nblocks == 1:
            if self.cmd(24, block_num * self.cdv, 0) != 0:
                raise OSError("SD card write block failed")
            self.write(0xFE, buf)
        else:
            if self.cmd(25, block_num * self.cdv, 0) != 0:
                raise OSError("SD card write blocks failed")
            offset = 0
            mv = memoryview(buf)
            for i in range(nblocks):
                self.write(0xFC, mv[offset : offset + 512])
                offset += 512
            self.cs(0)
            self.tokenbuf[0] = 0xFD
            self.spi.write(self.tokenbuf)
            self.spi.write(b"\xff")
            for i in range(1000000):
                self.spi.readinto(self.tokenbuf, 0xFF)
                if self.tokenbuf[0] == 0xFF:
                    break
            self.cs(1)
            self.spi.write(b"\xff")

    def ioctl(self, op, arg):
        if op == 4: # get number of blocks
            return 0
        elif op == 5: # get block size
            return 512
