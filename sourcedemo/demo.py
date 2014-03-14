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
    ('magic',               '8s'),  # should be "HL2DEMO"+NULL
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

PACKET_TYPES = {
    b'\x01': 'sign_on',
    b'\x02': 'packet',
    b'\x03': 'sync_tick',
    b'\x04': 'console_cmd',
    b'\x05': 'user_cmd',
    b'\x06': 'datatables',
    b'\x07': 'stop',
    b'\x08': 'custom_data',
    b'\x09': 'string_tables',
}

header_field_names, header_field_types = zip(*HEADER_FIELDS)
header_struct = ''.join(header_field_types)

def struct_read(struct_fmt, handle):
    data = handle.read(struct.calcsize(struct_fmt))
    return struct.unpack(struct_fmt, data)

class Demo():
    """
    Read a Source-engine DEM (Demo) file.
    https://developer.valvesoftware.com/wiki/DEM_Format
    """
    def __init__(self, filepath):
        num_packets = 0
        with open(filepath, 'rb') as f:
            header_data = f.read(struct.calcsize(header_struct))
            self.header = dict(zip(header_field_names, struct.unpack(header_struct, header_data)))
            if self.header['magic'] != HEADER_MAGIC:
                raise Exception("The specified file doesn't seem to be a demo.")
            del self.header['magic']

            
            # while True:
            #     if num_packets:
            #         packet_len = struct.unpack('i', f.read(4))[0]
            #     else:
            #         packet_len = self.header['sign_on_length']
            #     packet_data = f.read(packet_len - 4)# - struct.calcsize(header_struct) + 4)

            #     num_packets += 1
            #     print(num_packets, packet_len, packet_data[:min(len(packet_data), 10)])

        # stringify and trim bytestrings
        for field in self.header:
            if isinstance(self.header[field], bytes):
                self.header[field] = self.header[field].decode().rstrip('\x00')

        # pprint(self.header)

        # with open(filepath, 'rb') as f:
        #     f.seek(0x3354A - 8)
        #     server_frame, client_frame, subpacket_size = readout(f, 'iii')

        #     subpacket_data = f.read(subpacket_size)

        #     while True:
        #         command = f.read(1)
        #         command_num = readout(f, 'i')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('demo_file')
    args = parser.parse_args()

    demo = Demo(args.demo_file)

    print(demo.header)
