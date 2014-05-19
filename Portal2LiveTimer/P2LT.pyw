#! ipyw
from __future__ import division
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

__version__ = '0.2.1c'

import wpf

from System import IO, Exception, Windows, TimeSpan, Environment, Type, Activator
from System.Windows import Application, Window, Forms, Visibility, MessageBoxButton, MessageBoxImage, Media
from System.Windows.Threading import DispatcherTimer
from System.Text import ASCIIEncoding
from System.Diagnostics import Debug

import os
import itertools
import glob
import time
import webbrowser
import csv
import io
import struct
import collections
from collections import namedtuple
from pprint import pprint

######## binary_reader.py ###########################################
class BinaryReader(io.FileIO):
    def read_binary(self, fmt):
        data = self.read(struct.calcsize(fmt))
        unpacked = struct.unpack(fmt, str(data))
        return unpacked

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
            sb = sb.rstrip('\x00')
        if to_unicode:
            sb = sb.decode('utf-8')
        return sb

    def skip(self, delta):
        self.seek(delta, io.SEEK_CUR)

######## demo.py ###########################################
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

######## p2maps.py ###########################################
CHAPTERS = [
    [# Chapter 1 - The Courtesy Call
        'sp_a1_intro1',
        'sp_a1_intro2',
        'sp_a1_intro3',
        'sp_a1_intro4',
        'sp_a1_intro5',
        'sp_a1_intro6',
        'sp_a1_intro7',
        'sp_a1_wakeup',
        'sp_a2_intro',
    ],
    [# Chapter 2 - The Cold Boot
        'sp_a2_laser_intro',
        'sp_a2_laser_stairs',
        'sp_a2_dual_lasers',
        'sp_a2_laser_over_goo',
        'sp_a2_catapult_intro',
        'sp_a2_trust_fling',
        'sp_a2_pit_flings',
        'sp_a2_fizzler_intro',
    ],
    [# Chapter 3 - The Return
        'sp_a2_sphere_peek',
        'sp_a2_ricochet',
        'sp_a2_bridge_intro',
        'sp_a2_bridge_the_gap',
        'sp_a2_turret_intro',
        'sp_a2_laser_relays',
        'sp_a2_turret_blocker',
        'sp_a2_laser_vs_turret',
        'sp_a2_pull_the_rug',
    ],
    [# Chapter 4 - The Surprise
        'sp_a2_column_blocker',
        'sp_a2_laser_chaining',
        'sp_a2_triple_laser',
        'sp_a2_bts1',
        'sp_a2_bts2',
    ],
    [# Chapter 5 - The Escape
        'sp_a2_bts3',
        'sp_a2_bts4',
        'sp_a2_bts5',
        'sp_a2_bts6',
        'sp_a2_core',
    ],
    [# Chapter 6 - The Fall
        'sp_a3_00',
        'sp_a3_01',
        'sp_a3_03',
        'sp_a3_jump_intro',
        'sp_a3_bomb_flings',
        'sp_a3_crazy_box',
        'sp_a3_transition01',
    ],
    [# Chapter 7 - The Reunion
        'sp_a3_speed_ramp',
        'sp_a3_speed_flings',
        'sp_a3_portal_intro',
        'sp_a3_end',
    ],
    [# Chapter 8 - The Itch
        'sp_a4_intro',
        'sp_a4_tb_intro',
        'sp_a4_tb_trust_drop',
        'sp_a4_tb_wall_button',
        'sp_a4_tb_polarity',
        'sp_a4_tb_catch',
        'sp_a4_stop_the_box',
        'sp_a4_laser_catapult',
        'sp_a4_laser_platform',
        'sp_a4_speed_tb_catch',
        'sp_a4_jump_polarity',
    ],
    [# Chapter 9 - The Part Where...
        'sp_a4_finale1',
        'sp_a4_finale2',
        'sp_a4_finale3',
        'sp_a4_finale4',
        #'sp_a5_credits',
    ],
]
    
MAPS = list(itertools.chain.from_iterable(CHAPTERS))

######## mapsort.py ###########################################
N_MAPS = len(MAPS)

class SplitsParseError(IOError):
    pass

def parse_csv(file):
    """
    Takes a file path and returns a list of 2-tuples with map name and
    ticks taken.

    Demo file can be 2 or 3 columns and optionally have a header.  The format
    of a 2-column CSV is assumed to be (map name, ticks), and the 3-column
    format to be (map name, start tick, end tick)
    """
    try:
        with open(file, 'r') as f:
            has_header = csv.Sniffer().has_header(f.read(1024))
            f.seek(0)
            print(has_header)

            democsv = csv.reader(f)
            header = next(democsv) if has_header else None

            data = [row for row in democsv]
    except IOError as e:
        raise SplitsParseError("Could not read file")
    except csv.Error as e:
        raise SplitsParseError("Could not parse file as CSV")

    problems = []

    data_len = len(data)
    if data_len == 0:
        raise SplitsParseError("Empty data file")

    field_len = len(header if header else data[0])
    if not (2 <= field_len <= 3):
        raise SplitsParseError("Data file must have 2 (map/ticks) or 3 (map/start tick/stop tick) fields ({} detected)".format(field_len))

    # make sure it's all the same size
    for i, row in enumerate(data, start=1):
        if len(row) != field_len:
            raise SplitsParseError("Row {} is differently sized than other rows ({} long, expected {})".format(i+1 if header else i, len(row), field_len))

    # convert strings into numbers
    try:
        if field_len == 3:
            data = [(mapn, int(stop) - int(start)) for mapn, start, stop in data]
        elif field_len == 2:
            data = [(mapn, int(ticks)) for mapn, ticks in data]
    except ValueError as e:
        raise SplitsParseError("Error converting data, ensure ticks are integers")

    return data

def startstop_to_ticks(data):
    return [(mapn, stop-start) for mapn, start, stop in data]

def validate_times(map_times, ignore_credits=True):
    if ignore_credits:
        missing_maps = set(MAPS[:-1]) - set(map_times)
    else:
        missing_maps = set(MAPS) - set(map_times)
    unknown_maps = set(map_times) - set(MAPS)

    if missing_maps:
        raise SplitsParseError("Data file missing {} map(s) for complete run: {}".format(len(missing_maps), ', '.join(missing_maps)))
    if unknown_maps:
        raise SplitsParseError("Data file contains {} unrecognized map(s): {}".format(len(unknown_maps), ', '.join(unknown_maps)))

def combine_maps(data, validate=True):
    # sum ticks
    map_times = collections.defaultdict(int)
    for mapn, ticks in data:
        map_times[mapn] += ticks

    if validate:
        validate_times(map_times)

    return map_times

def sort_maps(map_times):
    """
    Takes a dictionary with maps as keys and ticks as values and returns a
    sorted list-of-items (tuples) representation.
    """
    map_times_sorted = sorted(map_times.items(), key=lambda x: MAPS.index(x[0]))
    return map_times_sorted

def combine_chapters(map_times):
    """
    Takes a dictionary with maps as keys and ticks as values and returns a
    list of ticks based on chapters
    """
    chapter_times = [0 for _ in CHAPTERS]
    for i, chapter in enumerate(CHAPTERS):
        for mapn in chapter:
            chapter_times[i] += map_times[mapn]

    return chapter_times

######## Portal2LiveTimer.xaml ###########################################
xamlStream = IO.MemoryStream(ASCIIEncoding.ASCII.GetBytes("""
<Window 
       xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" 
       xmlns:d="http://schemas.microsoft.com/expression/blend/2008" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="d" 
       Title="Portal 2 Live Timer" Width="195" Height="428"
       MinWidth="195" MinHeight="140">
    <Window.Resources>
        <Style TargetType="{x:Type Label}">
            <Setter Property="Foreground" Value="#DDD"/>
        </Style>
        <Style x:Key="baseLabel" TargetType="{x:Type Label}">
            <Setter Property="Foreground" Value="#DDD"/>
            <Setter Property="VerticalAlignment" Value="Top"/>
        </Style>
        <Style TargetType="{x:Type MenuItem}">
            <Setter Property="Foreground" Value="Black"/>
        </Style>
        <Style x:Key="MenuRoot" TargetType="{x:Type MenuItem}">
            <Setter Property="Foreground" Value="#FFAEAEAE"/>
            <Setter Property="Margin" Value="2"/>
        </Style>
        <Style x:Key="Heading" TargetType="{x:Type Label}" BasedOn="{StaticResource baseLabel}">
            <Setter Property="HorizontalAlignment" Value="Right"/>
        </Style>
        <Style x:Key="Time" TargetType="{x:Type Label}" BasedOn="{StaticResource baseLabel}">
            <Setter Property="HorizontalAlignment" Value="Right"/>
            <Setter Property="FontWeight" Value="Bold"/>
            <Setter Property="Foreground" Value="White"/>
        </Style>
        <Style x:Key="MainTime" TargetType="{x:Type Label}" BasedOn="{StaticResource Time}">
            <Setter Property="FontSize" Value="48"/>
        </Style>
        <Style x:Key="SplitTime" TargetType="{x:Type Label}" BasedOn="{StaticResource Time}">
            <Setter Property="FontSize" Value="30"/>
        </Style>
        <Style x:Key="SplitTimeMS" TargetType="{x:Type Label}" BasedOn="{StaticResource Time}">
            <Setter Property="FontSize" Value="16"/>
        </Style>
        <Style x:Key="ChapterTitle" TargetType="{x:Type Label}" BasedOn="{StaticResource baseLabel}">
            <Setter Property="HorizontalAlignment" Value="Left"/>
        </Style>
        <Style x:Key="ChapterTime" TargetType="{x:Type Label}" BasedOn="{StaticResource Time}"/>
    </Window.Resources>
    <Grid>
        <DockPanel Panel.ZIndex="100">
            <Menu x:Name="mnuMain" Visibility="Collapsed" DockPanel.Dock="Top" Background="#252525">
                <MenuItem Header="_FILE" Style="{StaticResource MenuRoot}">
                    <MenuItem x:Name="mnuFileDemos" Header="Select _Demo Directory"/>
                    <Separator />
                    <MenuItem x:Name="mnuFileLoad" Header="_Open Splits..."/>
                    <MenuItem x:Name="mnuFileClose" Header="_Close Splits"/>
                    <Separator />
                    <MenuItem x:Name="mnuFileSave" Header="_Save Current Run..."/>
                    <Separator />
                    <MenuItem x:Name="mnuFileExit" Header="E_xit"/>
                </MenuItem>
                <MenuItem Header="_EDIT" Style="{StaticResource MenuRoot}">
                    <MenuItem x:Name="mnuEditCopy" Header="_Copy Maps/Ticks"/>
                </MenuItem>
                <MenuItem Header="_VIEW" Style="{StaticResource MenuRoot}">
                    <MenuItem x:Name="mnuViewOntop"  Header="_Always on Top" IsCheckable="True"/>
                </MenuItem>
                <MenuItem Header="_HELP" Style="{StaticResource MenuRoot}">
                    <MenuItem x:Name="mnuHelpHelp" Header="_Usage"/>
                    <Separator/>
                    <MenuItem x:Name="mnuHelpSource" Header="_Source Repo"/>
                    <MenuItem x:Name="mnuHelpIssues" Header="_Bugs/Feature Requests"/>
                    <Separator/>
                    <MenuItem x:Name="mnuHelpAbout" Header="_About"/>
                </MenuItem>
            </Menu>
            <Grid />
        </DockPanel>
        <DockPanel>
            <StatusBar DockPanel.Dock="Bottom" Background="#222" Foreground="#999">
                <StatusBarItem>
                    <TextBlock x:Name="tblkVersion" TextWrapping="Wrap" Text="version x.y.z"/>
                </StatusBarItem>
                <StatusBarItem HorizontalAlignment="Right">
                    <Button x:Name="btnReset" HorizontalAlignment="Center" Margin="0" 
                	    Focusable="False" BorderThickness="0"
                	    Foreground="#999" Style="{StaticResource {x:Static ToolBar.ButtonStyleKey}}">
                        <Underline>Reset</Underline>
                    </Button>
                </StatusBarItem>
            </StatusBar>
            <Grid>
                <Grid.Background>
                    <LinearGradientBrush EndPoint="0.5,1" StartPoint="0.5,0">
                        <GradientStop Color="#111" Offset="1"/>
                        <GradientStop Color="#1A1A1A" Offset="0.687"/>
                    </LinearGradientBrush>
                </Grid.Background>
                <DockPanel>
                    <Grid x:Name="gridMainTimes"  DockPanel.Dock="Top" Height="128">
                    <!--<Grid DockPanel.Dock="Top" Height="158">-->
                        <!-- Main Timing -->
                        <Label Content="Estimated Time" Margin="0,5,8,0" Style="{StaticResource Heading}"/>
                        <Label x:Name="lblTimerLive" Content="0:00:00" Margin="0,9,5,0" VerticalAlignment="Top" FontSize="47" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>

                        <Label Content="After Last Demo" Margin="0,72,8,0" Style="{StaticResource Heading}"/>
                        <Label x:Name="lblTimerSplit" Style="{StaticResource SplitTime}" Margin="0,82,36,0"
                               Content="0:00"/>
                        <Label x:Name="lblTimerSplitMS" Style="{StaticResource SplitTimeMS}" Margin="0,88,7,0" 
                               Content="000"/>
                        <Label x:Name="lblTimerSplitDiff" Style="{StaticResource SplitTime}" Foreground="#0C0" Margin="0,112,36,0" 
                               Content="−0:00"/>
                        <Label x:Name="lblTimerSplitDiffMS" Style="{StaticResource SplitTimeMS}" Foreground="#0C0" Margin="0,118,7,0"
                               Content="000"/>
                    </Grid>
                    <Grid DockPanel.Dock="Bottom" Height="50">
                        <!-- Status -->
                        <Label Content="Status" Margin="0,-3,8,0" Style="{StaticResource Heading}"/>
                        <Label x:Name="lblStatus" Content="Select demo path." Margin="0,16,8,0" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>
                    </Grid>
                    <Grid>
                        <!-- Chapter Splits -->
                        <Rectangle x:Name="rectChHighlight" Height="20" VerticalAlignment="Top" Margin="0,3,0,0" Grid.ColumnSpan="2">
                            <Rectangle.Fill>
                                <LinearGradientBrush EndPoint="0.5,1" StartPoint="0.5,0">
                                    <GradientStop Color="#11444444"/>
                                    <GradientStop Color="#DD444444" Offset="1"/>
                                </LinearGradientBrush>
                            </Rectangle.Fill>
                        </Rectangle>

                        <Label Margin="4,0,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>1. <Italic>The Courtesy Call</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,20,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>2. <Italic>The Cold Boot</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,40,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>3. <Italic>The Return</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,60,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>4. <Italic>The Surprise</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,80,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>5. <Italic>The Escape</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,100,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>6. <Italic>The Fall</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,120,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>7. <Italic>The Reunion</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,140,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>8. <Italic>The Itch</Italic></TextBlock>
                        </Label>
                        <Label Margin="4,160,0,0" Style="{StaticResource ChapterTitle}">
                            <TextBlock>9. <Italic>This Is That Part</Italic></TextBlock>
                        </Label>
                        <Label x:Name="lblTCh1" Content="---" Style="{StaticResource ChapterTime}" Margin="0,0,4,0"/>
                        <Label x:Name="lblTCh2" Content="---" Style="{StaticResource ChapterTime}" Margin="0,20,4,0"/>
                        <Label x:Name="lblTCh3" Content="---" Style="{StaticResource ChapterTime}" Margin="0,40,4,0"/>
                        <Label x:Name="lblTCh4" Content="---" Style="{StaticResource ChapterTime}" Margin="0,60,4,0"/>
                        <Label x:Name="lblTCh5" Content="---" Style="{StaticResource ChapterTime}" Margin="0,80,4,0"/>
                        <Label x:Name="lblTCh6" Content="---" Style="{StaticResource ChapterTime}" Margin="0,100,4,0"/>
                        <Label x:Name="lblTCh7" Content="---" Style="{StaticResource ChapterTime}" Margin="0,120,4,0"/>
                        <Label x:Name="lblTCh8" Content="---" Style="{StaticResource ChapterTime}" Margin="0,140,4,0"/>
                        <Label x:Name="lblTCh9" Content="---" Style="{StaticResource ChapterTime}" Margin="0,160,4,0"/>
                    </Grid>
                </DockPanel>
            </Grid>
        </DockPanel>
    </Grid>
</Window> 
"""))

######## Portal2LiveTimer.pyw ###########################################
TIME_FUDGE_LOAD = -2
TIME_FUDGE_START = -12

STATE_WAIT = 0
STATE_RUNNING = 1
STATE_NOPATH = 2
STATE_COMPLETE = 3

BRUSH_DEFAULT = Media.SolidColorBrush(Media.Colors.White)
BRUSH_GOOD = Media.SolidColorBrush(Media.Colors.LimeGreen)
BRUSH_BAD = Media.SolidColorBrush(Media.Colors.Red)
BRUSH_MEH = Media.SolidColorBrush(Media.Colors.OliveDrab)

def findPortal2():
    guess = r'C:\Program Files (x86)\Steam\SteamApps\common\portal 2\portal2'
    if os.path.isdir(guess):
        return guess

    for startMenu in [
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
        ]:
        
        # check if Steam shortcut is there
        steam_shortcut = os.path.join(startMenu, 'Programs', 'Steam', 'Steam.lnk')
        if not os.path.isfile(steam_shortcut):
            continue # didn't find it

        # If so, follow the shortcut to the Steam folder
        shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"))
        shortcut = shell.CreateShortCut(steam_shortcut)
        steam_folder = os.path.dirname(shortcut.TargetPath())
        p2_folder = os.path.join(steam_folder, 
                'SteamApps', 'common', 'portal 2', 'portal2')
        if os.path.isdir(p2_folder):
            return p2_folder # found it

def demosInDirectory(directory):
    return glob.glob(os.path.join(directory, '*.dem'))

def saveDemoCSV(filename, demodata):
    header = ['map', 'tick_start', 'tick_stop']
    with open(filename, 'wb') as f:
        democsv = csv.writer(f)    
        democsv.writerow(header)
        for row in demodata:
            democsv.writerow(row)

def loadDemoCSV(filename):
    demodata = parse_csv(filename)
    demodata = combine_maps(demodata, validate=True)
    return demodata

def chapterSplits(map_times):
    rec_maps = set([mapn for mapn, ticks in map_times.iteritems() if ticks > 0])

    ch_times = combine_chapters(map_times)
    ch_splits = [None] * len(CHAPTERS)

    # check that chapters are complete
    last_ch = 0
    for i, chapter in enumerate(CHAPTERS):
        if set(chapter).issubset(rec_maps):
            ch_splits[i] = last_ch + ch_times[i]
            last_ch = ch_splits[i]
        else:
            break

    return ch_splits

def mapSplits(map_times):
    sorted_times = sort_maps(map_times)
    map_splits = []

    last_map = 0
    for mapn, ticks in sorted_times:
        map_splits.append(last_map + ticks)
        last_map = map_splits[-1]

    return map_splits

def formatTime(seconds, precision=0):
    clock_hr = int(seconds // 3600)
    clock_min = int((seconds // 60) % 60)
    clock_sec = int(seconds % 60)
    clock_frac = float(seconds) % 1

    if clock_hr:
        clock_fmt = '{:d}:{:02d}:{:02d}'.format(clock_hr, clock_min, clock_sec)
    else:
        clock_fmt = '{:d}:{:02d}'.format(clock_min, clock_sec)

    if precision:
        clock_fmt = clock_fmt + '{:.{p}f}'.format(clock_frac, p=precision)[1:]

    return clock_fmt

def formatDiff(seconds, variable_precision=True):
    negative = seconds < 0
    seconds = abs(seconds)
    clock_hr = int(seconds // 3600)
    clock_min = int((seconds // 60) % 60)
    clock_sec = int(seconds % 60)
    clock_frac = float(seconds) % 1

    if variable_precision:
        precision = 0
        if clock_hr:
            clock_fmt = '{:d}h{:02d}'.format(clock_hr, clock_min)
        elif clock_min:
            clock_fmt = '{:d}:{:02d}'.format(clock_min, clock_sec)
            if clock_min < 10:
                precision = 1
        else:
            clock_fmt = '{:d}'.format(clock_sec)
            if clock_sec >= 10:
                precision = 2
            else:
                precision = 3
    else:
        if clock_hr:
            clock_fmt = '{:d}:{:02d}:{:02d}'.format(clock_hr, clock_min, clock_sec)
        elif clock_min:
            clock_fmt = '{:d}:{:02d}'.format(clock_min, clock_sec)
        else:
            clock_fmt = '{:d}'.format(clock_sec)
        precision = 3
        
    if precision:
        clock_fmt = clock_fmt + '{:.{p}f}'.format(clock_frac, p=precision)[1:]

    #Debug.WriteLine('Diff format: {}, negative={}'.format(seconds, negative))

    return (u'\u2212' if negative else '+') + clock_fmt

BASE_BB = 'https://bitbucket.org/nick_timkovich/portal-2-live-timer/'

def gotoWiki(sender, args):
    webbrowser.open(BASE_BB + 'wiki')

def gotoSource(sender, args):
    webbrowser.open(BASE_BB + 'src')

def gotoIssues(sender, args):
    webbrowser.open(BASE_BB + 'issues?status=new&status=open')

def about(sender, args):
    Windows.MessageBox.Show(
        """Portal 2 Live Timer
        
A timer that uses demos to time Portal 2 single player speedruns and
playthroughs.  For details of use, see the Bitbucket Wiki (Help / Usage).

Created by @nicktimko (Alphahelix235 on Twitch)
Version {}
""".format(__version__))

class Portal2LiveTimer(Window):
    def __init__(self):
        wpf.LoadComponent(self, xamlStream)
        self.tblkVersion.Text = 'version ' + __version__
        self.state = STATE_NOPATH

        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan(0, 0, 0, 1)
        self.timer.Tick += self.update

        #self.IsMouseDirectlyOverChanged += self.showhideMenu
        self.MouseEnter += self.showhideMenu
        self.MouseLeave += self.showhideMenu

        self.btnReset.Click += self.resetClick

        self.mnuFileDemos.Click += self.pickDirectory
        self.mnuFileSave.Click += self.saveDemoCSV
        self.mnuFileClose.Click += self.removeSplits
        self.mnuFileLoad.Click += self.loadDemoCSV
        self.mnuFileExit.Click += lambda sender, args: self.Close()

        self.mnuEditCopy.Click += self.copyDemoData
        self.mnuViewOntop.Click += self.setOnTop
        #self.mnuViewBgKey += self.backgroundColor
        #self.mnuViewBgReset += self.backgroundReset
        self.mnuHelpHelp.Click += gotoWiki
        self.mnuHelpIssues.Click += gotoIssues
        self.mnuHelpSource.Click += gotoSource
        self.mnuHelpAbout.Click += about

        self.pickDialog = Forms.FolderBrowserDialog()
        self.pickDialog.Description = "Select the Portal 2 root directory where demos are saved."
        self.pickDialog.ShowNewFolderButton = False
        self.pickDialog.RootFolder = Environment.SpecialFolder.MyComputer
        
        self.saveDialog = Forms.SaveFileDialog()
        self.saveDialog.Title = "Select where to save demo timings"
        self.saveDialog.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        self.openDialog = Forms.OpenFileDialog()
        self.openDialog.Title = "Select a split file in 2- or 3-column CSV format"
        self.openDialog.Filter = "CSV files (*.csv)|*.csv"
        
        self.mapDeltaShowing = False
        self.demoData = []
        self.demoDataMaps = []
        self.demoDataChapters = [None] * len(CHAPTERS)
        self.splitData = None
        self.splitDataMaps = None
        self.splitDataChapters = None
        self.lblTChs = [self.lblTCh1, self.lblTCh2, self.lblTCh3, 
                        self.lblTCh4, self.lblTCh5, self.lblTCh6, 
                        self.lblTCh7, self.lblTCh8, self.lblTCh9]

        portalPath = findPortal2()
        if portalPath:
            self.demoDir = portalPath
            self.pickDialog.SelectedPath = self.demoDir
            self.transitionWait()

    def showhideMenu(self, sender, args):
        self.mnuMain.Visibility = Visibility.Visible if self.IsMouseOver else Visibility.Collapsed
        # = 'Visible' if self.IsMouseOver else 'Collapsed'

    def transitionWait(self):
        self.state = STATE_WAIT
        self.lblStatus.Content = "Waiting for demo..."
        #self.lblLastMap.Content = "(none)"
        self.clockTime(0)
        self.splitTime(0)
        self.demoTime = 0
        self.demoData = []
        self.demoDataMaps = []
        self.demoDataChapters = [None] * len(CHAPTERS)
        self.splitMap()
        self.splitChapters()
        self.timer.Start()
        
        # demos dealt with
        self.ignoredDemos = set(demosInDirectory(self.demoDir))
        self.processedDemos = set()
        self.unprocessedDemos = set()

        Debug.WriteLine('{} ignored demos'.format(len(self.ignoredDemos)))

    def transitionRunning(self):
        self.state = STATE_RUNNING
        self.lblStatus.Content = "Monitoring..."
        self.timeStart = time.time()

    def transitionComplete(self):
        self.state = STATE_COMPLETE
        self.lblStatus.Content = "Run Complete! ({} demos)".format(len(self.processedDemos))
        self.lblTimerLive.Content = formatTime(self.demoTime)
        self.timer.Stop()

    def saveDemoCSV(self, sender, args):
        result = self.saveDialog.ShowDialog()
        if result == Forms.DialogResult.OK and self.saveDialog.FileName:
            try:
                saveDemoCSV(self.saveDialog.FileName, self.demoData)
            except IOError:
                Windows.MessageBox.Show("Error saving file", "Error saving", MessageBoxButton.OK, MessageBoxImage.Error)

    def loadDemoCSV(self, sender, args):
        result = self.openDialog.ShowDialog()
        if result == Forms.DialogResult.OK and self.openDialog.FileName:
            try:
                splitdata = loadDemoCSV(self.openDialog.FileName)
            except SplitsParseError as e:
                print(e)
                Windows.MessageBox.Show("Error parsing splits file!\n\n{}\n\n"
                        "If this error is inexplicable, check the Help wiki (Help, Usage).\n"
                        "If this error is in error, please file a bug report, attaching your CSV file (Help, Bugs)."
                        .format(e.message), "Error loading", MessageBoxButton.OK, MessageBoxImage.Error)
                return

            self.splitData = splitdata
            self.splitDataMaps = mapSplits(splitdata)
            self.splitDataChapters = chapterSplits(splitdata)
            self.showMapDelta()
            self.splitMap()
            self.splitChapters()

    def removeSplits(self, sender, args):
        self.splitData = None
        self.splitDataMaps = None
        self.splitDataChapters = None
        self.splitChapters()
        self.hideMapDelta()

    def showMapDelta(self):
        if not self.mapDeltaShowing:
            self.Height += 30
            self.gridMainTimes.Height += 30
            self.mapDeltaShowing = True
        
    def hideMapDelta(self):
        if self.mapDeltaShowing:
            self.Height -= 30
            self.gridMainTimes.Height -= 30
            self.mapDeltaShowing = False

    def copyDemoData(self, sender, args):
        tsv = 'map\tstart tick\tend tick\n'
        tsv += '\n'.join(['\t'.join(str(f) for f in demo) for demo in self.demoData])
        Windows.Clipboard.SetText(tsv)

    def setOnTop(self, sender, args):
        self.Topmost = self.mnuViewOntop.IsChecked

    def pickDirectory(self, sender, args):
        result = self.pickDialog.ShowDialog()
        if result == Forms.DialogResult.OK:
            self.demoDir = self.pickDialog.SelectedPath
            self.transitionWait()

    def resetClick(self, sender, args):
        if self.state != STATE_NOPATH:
            self.transitionWait()

    def update(self, sender, args):
        return {
                STATE_WAIT: self.updateWait,
                STATE_RUNNING: self.updateRunning,
                STATE_NOPATH: lambda: None,
                STATE_COMPLETE: lambda: None,
            }[self.state]()

    def updateWait(self):
        # look in directory for new demos
        currentDemos = set(demosInDirectory(self.demoDir))
        if currentDemos - self.ignoredDemos:
            self.transitionRunning()

    def updateRunning(self):
        # update timer
        self.update_clock()

        # check for new demos
        allDemos = set(demosInDirectory(self.demoDir))
        self.unprocessedDemos.update(allDemos - self.ignoredDemos - self.processedDemos)

        for demo_file in self.unprocessedDemos:
            try:
                info = IO.FileInfo(demo_file)
                if not info.Length: 
                    break

                demo1 = Demo(demo_file)
                self.demoTime += demo1.get_time()
                #self.lblLastMap.Content = demo1.header['map_name'].replace('_', '__')

                # resync timer and update split
                self.timeStart = time.time() - self.demoTime - TIME_FUDGE_LOAD
                self.update_clock()
                self.splitTime(self.demoTime)

                self.demoData.append((demo1.header['map_name'], demo1.tick_start, demo1.tick_end))

                map_times = combine_maps(startstop_to_ticks(self.demoData), validate=False)
                self.demoDataMaps = mapSplits(map_times)
                self.demoDataChapters = chapterSplits(map_times)
                self.splitMap()
                self.splitChapters()

                self.processedDemos.add(demo_file)
                if demo1.tick_end_game:
                    self.transitionComplete()
            except (DemoProcessError, IOError):
                pass

        self.unprocessedDemos = self.unprocessedDemos - self.processedDemos
        if self.state == STATE_RUNNING:
            self.lblStatus.Content = "Monitoring ({}+{} demos)...".format(len(self.processedDemos), len(self.unprocessedDemos))

    def update_clock(self):
        clock = time.time() - self.timeStart
        self.clockTime(clock)

    def clockTime(self, seconds):
        self.lblTimerLive.Content = formatTime(seconds)

    def splitTime(self, seconds):
        timef = formatTime(seconds, 3)
        self.lblTimerSplit.Content = timef[:-4]
        self.lblTimerSplitMS.Content = timef[-3:]

    def splitMap(self):
        if self.splitDataMaps:
            empty = True
            for split, reference in zip(self.demoDataMaps, self.splitDataMaps):
                empty = False
            
            if not empty:
                diff = split - reference
                positive = True if diff > 0 else False
                timef = formatDiff(diff / 60.0, variable_precision=False)
                
                if diff != 0:
                    self.lblTimerSplitDiff.Content = timef[:-4]
                    self.lblTimerSplitDiffMS.Content = timef[-3:]
                    self.lblTimerSplitDiff.Foreground = BRUSH_BAD if positive else BRUSH_GOOD
                    self.lblTimerSplitDiffMS.Foreground = BRUSH_BAD if positive else BRUSH_GOOD
                else:
                    self.lblTimerSplitDiff.Content = 'par'
                    self.lblTimerSplitDiff.Foreground = BRUSH_MEH
                    self.lblTimerSplitDiffMS.Content = ''
            else:
                self.lblTimerSplitDiff.Content = '---'
                self.lblTimerSplitDiffMS.Content = ''
                self.lblTimerSplitDiff.Foreground = BRUSH_DEFAULT
                self.lblTimerSplitDiffMS.Foreground = BRUSH_DEFAULT

    def splitChapters(self):
        highlighted = False
        if self.splitDataChapters is None:
            for i, (label, split) in enumerate(zip(self.lblTChs, self.demoDataChapters)):
                label.Foreground = BRUSH_DEFAULT
                if split is not None:
                    label.Content = formatTime(split/60.0, 1)
                else:
                    if not highlighted:
                        self.rectChHighlight.Margin = Windows.Thickness(0, 3 + 20*i, 0, 0)
                        self.rectChHighlight.Visibility = Visibility.Visible
                        highlighted = True
                    label.Content = '---'
        else:
            for i, (label, split, reference) in enumerate(zip(self.lblTChs, self.demoDataChapters, self.splitDataChapters)):
                if split is not None:
                    diff = split - reference
                    label.Content = formatDiff(diff/60.0)
                    if diff < 0:
                        label.Foreground = BRUSH_GOOD
                    elif diff > 0:
                        label.Foreground = BRUSH_BAD
                    else:
                        label.Foreground = BRUSH_MEH
                        label.Content = "par"
                else:
                    label.Content = formatTime(reference/60.0, 1)
                    label.Foreground = BRUSH_DEFAULT
                    if not highlighted:
                        self.rectChHighlight.Margin = Windows.Thickness(0, 3 + 20*i, 0, 0)
                        self.rectChHighlight.Visibility = Visibility.Visible
                        highlighted = True

        if not highlighted:
            self.rectChHighlight.Visibility = Visibility.Hidden

if __name__ == '__main__':
    Application().Run(Portal2LiveTimer())
