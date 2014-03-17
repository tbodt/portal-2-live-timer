"""
Source-engine DEM (Demo)
https://developer.valvesoftware.com/wiki/DEM_Format
"""
import struct
import itertools
import io
from collections import namedtuple
from pprint import pprint

import enum

from . import binary_reader

TICK_FREQUENCY = 60 # Hz
MAX_OSPATH = 260
HEADER_MAGIC = b'HL2DEMO\x00'
INTRO_SPAWN = -8674.000, 1773.000, 28.000

# Tick difference between moving away from the spawn location and the 
# crosshairs appearing
CROSSHAIR_TICK_OFFSET = 104

class Commands(enum.IntEnum):
    SIGN_ON = 1
    PACKET = 2
    SYNC_TICK = 3
    CONSOLE_CMD = 4
    USER_CMD = 5
    DATATABLES = 6
    STOP = 7
    CUSTOM_DATA = 8
    STRING_TABLES = 9

class Demo():
    """
    Read a Source-engine DEM (Demo) file.
    https://developer.valvesoftware.com/wiki/DEM_Format
    """
    def __init__(self, filepath):
        self.demo = binary_reader.BinaryReader(filepath)
        try:
            magic = self.demo.read_string(8, trim_null=False)
        except struct.error:
            raise Exception('Empty file.')
        if magic != HEADER_MAGIC:
            raise Exception("The specified file doesn't seem to be a demo.")

        self.header = {
                'demo_protocol':    self.demo.read_int32(),
                'network_protocol': self.demo.read_int32(),
                'server_name':      self.demo.read_string(MAX_OSPATH),
                'client_name':      self.demo.read_string(MAX_OSPATH),
                'map_name':         self.demo.read_string(MAX_OSPATH),
                'game_directory':   self.demo.read_string(MAX_OSPATH),
                'playback_time':    self.demo.read_float32(),
                'ticks':            self.demo.read_int32(),
                'frames':           self.demo.read_int32(),
                'sign_on_length':   self.demo.read_int32(),
            }

        self.process()

    def process(self):
        # TODO: Remove when done debugging.
        for command, tick, data in itertools.islice(self._process_commands(), 2**31):
            continue
            if command == Commands.PACKET:
                print(command, tick, '{:10.3f}, {:10.3f}, {:10.3f}'.format(*data))
            elif command == Commands.CONSOLE_CMD:
                print(command, tick, data)
            elif command == Commands.USER_CMD:
                print(command, tick, data)
            else:
                print(command, tick)

    def get_ticks(self):
        return

    def _process_commands(self):
        while True:
            command = self.demo.read_uint8()
            if command == Commands.STOP:
                break

            tick = self.demo.read_int32()
            self.demo.skip(1) # unknown

            yield command, tick, self._process_command(command)

    def _process_command(self, command):
        return {
            Commands.SIGN_ON:       self._process_sign_on,
            Commands.PACKET:        self._process_packet,
            Commands.SYNC_TICK:     self._process_sync_tick,
            Commands.CONSOLE_CMD:   self._process_console_cmd,
            Commands.USER_CMD:      self._process_user_cmd,
            Commands.DATATABLES:    self._process_data_tables,
            Commands.CUSTOM_DATA:   self._process_custom_data,
            Commands.STRING_TABLES: self._process_string_tables,
        }[command]()

    def _process_sign_on(self):
        """Sign on packet: Ignore"""
        self.demo.skip(self.header['sign_on_length'])

    def _process_packet(self):
        """Network packet: Get position data"""
        self.demo.skip(4) # unknown
        x, y, z = self.demo.read_binary('fff')
        self.demo.skip(0x90) # unknown

        cmd_len = self.demo.read_int32()
        self.demo.skip(cmd_len) # ignore it all

        return x, y, z

    def _process_sync_tick(self):
        """Never happens?  Means nothing?"""
        pass

    def _process_console_cmd(self):
        """Console command: Returns the command"""
        cmd_len = self.demo.read_int32()
        console_cmd = self.demo.read_string(cmd_len)
        return console_cmd

    def _process_user_cmd(self):
        """User command: Unknown format"""
        self.demo.skip(4) # unknown
        data_len = self.demo.read_int32()
        raw_data = self.demo.read_binary('{}s'.format(data_len))[0]
        return raw_data

    def _process_data_tables(self):
        """Data tables command: Unimplemented"""
        raise NotImplementedError()

    def _process_string_tables(self):
        """String tables: Unknown format"""
        data_len = self.demo.read_int32()
        raw_data = self.demo.read_binary('{}s'.format(data_len))[0]
        return raw_data

    def _process_custom_data(self):
        """Custom data: Unknown format"""
        self.demo.skip(4) # unknown
        data_len = self.demo.read_int32()
        raw_data = self.demo.read_binary('{}s'.format(data_len))[0]
        return raw_data
