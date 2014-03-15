"""
Source-engine DEM (Demo)
https://developer.valvesoftware.com/wiki/DEM_Format
"""
import struct
import io
from collections import namedtuple
from pprint import pprint

MAX_OSPATH = 260

HEADER_MAGIC = b'HL2DEMO\x00'
HEADER_FIELDS = [
    # Field                 Type      Value
    #('magic',               '8s'),  # should be "HL2DEMO"+NULL
    ('demo_protocol',       'i'),   # Demo protocol version
    ('network_protocol',    'i'),   # Network protocol version number
    ('server_name',         '{}s'.format(MAX_OSPATH)),
    ('client_name',         '{}s'.format(MAX_OSPATH)),
    ('map_name',            '{}s'.format(MAX_OSPATH)),
    ('game_directory',      '{}s'.format(MAX_OSPATH)),
    ('playback_time',       'f'),   # The length of the demo, in seconds
    ('ticks',               'i'),   # The number of ticks in the demo
    ('frames',              'i'),   # The number of frames in the demo
    ('sign_on_length',      'i'),   # Length of the signon data (Init for first frame)
]

CMD_SIGN_ON = 1
CMD_PACKET = 2
CMD_SYNC_TICK = 3
CMD_CONSOLE_CMD = 4
CMD_USER_CMD = 5
CMD_DATATABLES = 6
CMD_STOP = 7
CMD_CUSTOM_DATA = 8
CMD_STRING_TABLES = 9

class BinReader(io.FileIO):
    def read_binary(self, fmt):
        data = self.read(struct.calcsize(fmt))
        return struct.unpack(fmt, data)
    def read_chr(self):
        return self.read_binary('c')[0]
    def read_byte(self):
        return self.read_binary('B')[0]
    def read_int(self):
        return self.read_binary('i')[0]
    def read_float(self):
        return self.read_binary('f')[0]
    def read_string(self, length, trim_null=False):
        sb = self.read_binary(str(length) + 's')[0]
        if trim_null:
            sb = sb.rstrip(b'\x00')
        return sb
    def skip(self, delta):
        self.seek(delta, io.SEEK_CUR)

class Demo():
    """
    Read a Source-engine DEM (Demo) file.
    https://developer.valvesoftware.com/wiki/DEM_Format
    """
    def __init__(self, filepath):
        self.demo = BinReader(filepath)
        magic = self.demo.read_string(8)
        if magic != HEADER_MAGIC:
            raise Exception("The specified file doesn't seem to be a demo.")

        self.header = {name: self.demo.read_binary(fmt)[0] for name, fmt in HEADER_FIELDS}

        # stringify and trim bytestrings
        for field in self.header:
            if isinstance(self.header[field], bytes):
                self.header[field] = self.header[field].decode().rstrip('\x00')

        while True:
            command = self.demo.read_byte()
            if command == CMD_STOP:
                break
            # if command is a stop, break

            tick = self.demo.read_int()

            self.demo.skip(1) # unknown

            self._process_command(command)

    def _process_command(self, command):
        {
            CMD_SIGN_ON: self._process_sign_on,
            CMD_PACKET: self._process_packet,
            CMD_SYNC_TICK: self._process_sync_tick,
            CMD_CONSOLE_CMD: self._process_console_cmd,
            CMD_USER_CMD: self._process_user_cmd,
            CMD_DATATABLES: self._process_data_tables,
            CMD_CUSTOM_DATA: self._process_custom_data,
            CMD_STRING_TABLES: self._process_string_tables,
        }[command]()

    def _process_sign_on(self):
        """Sign on packet: Ignore"""
        print('Sign On')
        self.demo.skip(self.header['sign_on_length'])

    def _process_packet(self):
        """Network packet: Get position data"""
        self.demo.skip(4) # unknown
        x, y, z = self.demo.read_binary('fff')
        self.demo.skip(0x90) # unknown

        cmd_len = self.demo.read_int()
        self.demo.skip(cmd_len) # ignore it all

        return x, y, z

    def _process_sync_tick(self):
        """Never happens?  Means nothing?"""
        pass

    def _process_console_cmd(self):
        """Console command: Returns the command"""
        cmd_len = self.demo.read_int()
        console_cmd = self.demo.read_string(cmd_len)

        return console_cmd

    def _process_user_cmd(self):
        """User command: Ignore"""
        self.demo.skip(4)
        self.demo.skip(self.demo.read_int())

    def _process_data_tables(self):
        """Data tables command: Unimplemented"""
        raise NotImplementedError()

    def _process_string_tables(self):
        """String tables: Ignore"""
        self.demo.skip(self.demo.read_int())
        

    def _process_custom_data(self):
        """Custom data: Ignore"""
        self.demo.skip(4)
        self.demo.skip(self.demo.read_int())

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('demo_file')
    args = parser.parse_args()

    demo = Demo(args.demo_file)

    print(demo.header)
