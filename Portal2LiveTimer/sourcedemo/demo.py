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

from .binary_reader import BinaryReader

MAX_OSPATH = 260
HEADER_MAGIC = b'HL2DEMO\x00'

INTRO_START_POS = -8709.20, +1690.07, +28.00
INTRO_START_TOL = 0.02, 0.02, 0.5
INTRO_START_TICK_OFFSET = +1
INTRO_MAGIC_UNKNOWN_NUMBER = 3330 # second int32 in the user cmd packet

# best guess. you can move at ~2-3 units/tick, so don't check exactly.
FINALE_END_POS = 54.1, 159.2, -201.4

# how many ticks from last portal shot to being at the checkpoint.
# experimentally determined, may be wrong.
FINALE_END_TICK_OFFSET = -852

def on_the_moon(pos):
    # check if you're in a specific cylinder of volume and far enough below the floor.
    x, y, z = pos
    xf, yf, zf = FINALE_END_POS
    if (x - xf)**2 + (y - yf)**2 < 50**2 and z < zf:
        return True
    else:
        return False

def at_spawn(pos):
    # check if at the spawn coordinate for sp_a1_intro1
    for datum, check, tol in zip(pos, INTRO_START_POS, INTRO_START_TOL):
        if abs(datum - check) > tol:
            return False
    return True

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


class Demo(object):
    """
    Read a Source-engine DEM (Demo) file.
    https://developer.valvesoftware.com/wiki/DEM_Format
    """
    TICK_FREQUENCY = 60 # Hz

    def __init__(self, filepath):
        self.demo = BinaryReader(filepath)
        
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

        self.tick_start = None
        self.tick_end = None

        self.tick_start_game = None # exception for sp_a1_intro1
        self.tick_end_game = None   # exception for sp_a4_finale4

        self.process()
        self.demo.close()

    def process(self):
        for command, tick, data in self._process_commands():
            continue
        
        self.tick_start = self.tick_start_game if self.tick_start_game else self.tick_start
        self.tick_end = self.tick_end_game if self.tick_end_game else self.tick_end

    def get_ticks(self):
        assert self.tick_start is not None, "tick_start was None"
        assert self.tick_end is not None, "tick_end was None"

        ticks = self.tick_end - self.tick_start

        Debug.WriteLine('Ticks for map {:25s}: {} ({} to {})'.format(self.header['map_name'], ticks, self.tick_start, self.tick_end))

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
                    self.tick_start = tick
                self.tick_end = tick
                
                # Finale exception
                if (self.header['map_name'] == 'sp_a4_finale4' 
                        and not self.tick_end_game 
                        and on_the_moon(data)):
                    self.tick_end_game = tick + FINALE_END_TICK_OFFSET

                # Intro exception
                if (self.header['map_name'] == 'sp_a1_intro1'
                        and self.tick_start_game is None
                        and at_spawn(data)):
                    # because crosshair would appear the next frame (2 ticks)
                    self.tick_start_game = tick + INTRO_START_TICK_OFFSET

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
        assert data_len >= 8, "unexpectedly short data length"
        unk1, unk2 = self.demo.read_binary('ii')
        remainder = self.demo.read_binary('{}s'.format(data_len - 8))[0]
        return unk1, unk2, remainder

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
