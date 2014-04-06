"""
Source-engine DEM (Demo)
https://developer.valvesoftware.com/wiki/DEM_Format
"""
from __future__ import division
import struct
import itertools
import io
from collections import namedtuple
from pprint import pprint

from System.Diagnostics import Debug

from . import binary_reader

MAX_OSPATH = 260
HEADER_MAGIC = b'HL2DEMO\x00'

INTRO_START_POS = -8674.000, 1773.000, 28.000
FINALE_END_POS = 54.1, 159.2, -201.4  # all +/- 1 unit at least, maybe even 2.
FINALE_END_TICK_OFFSET = 19724 - 20577 # experimentally determined, may be wrong.

def on_the_moon(pos):
    # check if you're in a specific cylinder of volume and far enough below the floor.
    x, y, z = pos
    xf, yf, zf = FINALE_END_POS
    if (x - xf)**2 + (y - yf)**2 < 50**2 and z < zf:
        return True
    else:
        return False

class Commands(object):
    SIGN_ON = 1
    PACKET = 2
    SYNC_TICK = 3
    CONSOLE_CMD = 4
    USER_CMD = 5
    DATATABLES = 6
    STOP = 7
    CUSTOM_DATA = 8
    STRING_TABLES = 9


class DemoProcessError(Exception):
    pass


class Demo():
    """
    Read a Source-engine DEM (Demo) file.
    https://developer.valvesoftware.com/wiki/DEM_Format
    """
    TICK_FREQUENCY = 60 # Hz

    def __init__(self, filepath):
        self.demo = binary_reader.BinaryReader(filepath)
        
        try:
            magic = self.demo.read_string(8, trim_null=False)
        except struct.error:
            raise DemoProcessError('File error, might be empty?')
        if magic != HEADER_MAGIC:
            raise DemoProcessError("The specified file doesn't seem to be a demo.")

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

        #self.ticks = []
        self.tick_start = None
        self.tick_end = None
        self.tick_end_game = None

        self.process()

        self.demo.close()

    def process(self):
        for command, tick, data in self._process_commands():
            continue

    def get_ticks(self):
        if self.tick_end_game:
            ticks = self.tick_end_game - self.tick_start
        else: 
            ticks = self.tick_end - self.tick_start
        return ticks

    def get_time(self):
        return self.get_ticks()/Demo.TICK_FREQUENCY

    def _process_commands(self):
        while True:
            command = self.demo.read_uint8()
            if command == Commands.STOP:
                break

            tick = self.demo.read_int32()
            self.demo.skip(1) # unknown
            data = self._process_command(command)

            if command == Commands.PACKET and tick >= 0:
                if self.tick_start is None:
                    # handle the intro differently
                    if self.header['map_name'] == 'sp_a1_intro1':
                        for datum, check in zip(data, INTRO_START_POS):
                            if abs(datum - check) > 0.01:
                                break
                        else:
                            # corrected start time
                            self.tick_start = tick
                    else:
                        self.tick_start = tick

                if (self.header['map_name'] == 'sp_a4_finale4' 
                        and not self.tick_end_game 
                        and on_the_moon(data)):
                    self.tick_end_game = tick + FINALE_END_TICK_OFFSET
                
                self.tick_end = tick
                
            yield command, tick, data

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
