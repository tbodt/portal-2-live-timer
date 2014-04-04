import io
import struct

class BinaryReader(io.FileIO):
    def read_binary(self, fmt):
        data = self.read(struct.calcsize(fmt))
        return struct.unpack(fmt, data)

    def read_char(self):
        return self.read_binary('c')[0]

    def read_uint8(self):
        return self.read_binary('B')[0]

    def read_int32(self):
        return self.read_binary('i')[0]

    def read_float32(self):
        return self.read_binary('f')[0]

    def read_string(self, length, trim_null=True, to_unicode=False):
        sb = self.read_binary(str(length) + 's')[0]
        if trim_null:
            sb = sb.rstrip(b'\x00')
        if to_unicode:
            sb = sb.decode('utf-8')
        return sb

    def skip(self, delta):
        self.seek(delta, io.SEEK_CUR)
