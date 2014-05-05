#! ipyw
from __future__ import division
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

__version__ = '0.1.5'

import wpf

from System import TimeSpan, Environment, Type, Activator, Exception
from System.Windows import Application, Window, MessageBox, Clipboard
from System.Windows.Forms import FolderBrowserDialog, DialogResult
from System.Windows.Threading import DispatcherTimer
from System import IO
from System.Text import ASCIIEncoding

from System.Diagnostics import Debug

import os
import itertools
import glob
import time
import webbrowser
import io
import struct
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


class Demo():
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

######## Portal2LiveTimer.xaml ###########################################
xamlStream = IO.MemoryStream(ASCIIEncoding.ASCII.GetBytes("""
<Window 
       xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" 
       xmlns:d="http://schemas.microsoft.com/expression/blend/2008" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="d" 
       Title="Portal 2 Live Timer" ResizeMode="CanMinimize" Width="198" Height="338">
    <DockPanel>
        <Menu DockPanel.Dock="Top" Foreground="#FFAEAEAE">
            <Menu.Background>
                <LinearGradientBrush EndPoint="0,1" StartPoint="0,0">
                    <GradientStop Color="#FF3C3C3C"/>
                </LinearGradientBrush>
            </Menu.Background>
            <MenuItem Header="_Edit" Margin="2">
                <MenuItem x:Name="mnuEditCopy" Header="_Copy Maps/Ticks" Foreground="Black"/>
            </MenuItem>
            <MenuItem Header="_View" Margin="2">
                <MenuItem x:Name="mnuViewOntop"  Header="_Always on top" IsCheckable="True" Foreground="Black"/>
            </MenuItem>
            <MenuItem Header="_Help" Margin="2">
                <MenuItem x:Name="mnuHelpHelp" Header="_Usage" Foreground="Black"/>
                <Separator/>
                <MenuItem x:Name="mnuHelpSource" Header="_Source Repo" Foreground="Black"/>
                <MenuItem x:Name="mnuHelpIssues" Header="_Bugs/Feature Requests" Foreground="Black"/>
                <Separator/>
                <MenuItem x:Name="mnuHelpAbout" Header="_About" Foreground="Black"/>
            </MenuItem>
        </Menu>
        <StatusBar DockPanel.Dock="Bottom">
            <StatusBarItem Background="#FF3C3C3C" Foreground="#AAA">
                <TextBlock x:Name="tblkVersion" TextWrapping="Wrap" Text="version ?"/>
            </StatusBarItem>
        </StatusBar>
        <Grid>
            <Grid.Background>
                <LinearGradientBrush EndPoint="0.5,1" StartPoint="0.5,0">
                    <GradientStop Color="#FF1B1B1B" Offset="1"/>
                    <GradientStop Color="#FF232323" Offset="0.687"/>
                </LinearGradientBrush>
            </Grid.Background>
            <Label Content="Estimated Time" Margin="0,7,10,0" VerticalAlignment="Top" HorizontalAlignment="Right" Foreground="#DDD"/>
            <Label x:Name="lblTimerLive" Content="0:00" Margin="0,12,6,0" VerticalAlignment="Top" FontSize="48" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>

            <Label Content="Last Demo Split" Margin="0,77,10,0" VerticalAlignment="Top" HorizontalAlignment="Right" Foreground="#DDD"/>
            <Label x:Name="lblTimerSplit" Content="0:00" Margin="0,88,37,0" VerticalAlignment="Top" FontSize="30" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>
            <Label x:Name="lblTimerSplitMS" Content="000" Margin="0,94,7,0" VerticalAlignment="Top" FontSize="16" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>

            <Label Content="Last Map" HorizontalAlignment="Right" Margin="0,135,10,0" VerticalAlignment="Top" Foreground="#DDD"/>
            <Label x:Name="lblLastMap" Content="(none)" Margin="0,150,10,0" VerticalAlignment="Top" FontSize="16" Height="42" HorizontalAlignment="Right" Foreground="White" FontWeight="Bold"/>

            <Label Content="Status" Margin="0,180,10,0" VerticalAlignment="Top" HorizontalAlignment="Right" Foreground="#DDD"/>
            <Label x:Name="lblStatus" Content="Select Portal 2 path." Margin="0,196,10,0" VerticalAlignment="Top" FontWeight="Bold" HorizontalAlignment="Right" Foreground="White"/>

            <Button x:Name="btnReset" Content="Reset" HorizontalAlignment="Right" Margin="0,227,109,0" VerticalAlignment="Top" Width="64"
                    Focusable="False"
                    Background="#FF3C3C3C" Foreground="#AAA" Style="{StaticResource {x:Static ToolBar.ButtonStyleKey}}"/>
            <Button x:Name="btnDemoDir" Content="Demo Directory" HorizontalAlignment="Right" Margin="0,227,10,0" VerticalAlignment="Top" Width="94"
                    Focusable="False"
                    ToolTipService.InitialShowDelay="0" ToolTip="Select the directory where demos are saved." 
                    Background="#FF3C3C3C" Foreground="#AAA" Style="{StaticResource {x:Static ToolBar.ButtonStyleKey}}"/>
            <TextBox x:Name="txtDemoDir" Visibility="Hidden" Height="23" Margin="10,135,109,0" TextWrapping="Wrap" Text="Choose where demos are saved." VerticalAlignment="Top" IsEnabled="False"/>
            

        </Grid>
    </DockPanel>
</Window> 
"""))

######## Portal2LiveTimer.pyw ###########################################
STATE_WAIT = 0
STATE_RUNNING = 1
STATE_NOPATH = 2
STATE_COMPLETE = 3

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

BASE_BB = 'https://bitbucket.org/nick_timkovich/portal-2-live-timer/'

def gotoWiki(sender, args):
    webbrowser.open(BASE_BB + 'wiki')

def gotoSource(sender, args):
    webbrowser.open(BASE_BB + 'src')

def gotoIssues(sender, args):
    webbrowser.open(BASE_BB + 'issues?status=new&status=open')

def about(sender, args):
    MessageBox.Show(
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

        self.btnDemoDir.Click += self.pickDirectory
        self.btnReset.Click += self.resetClick

        self.mnuEditCopy.Click += self.copyDemoData
        self.mnuViewOntop.Click += self.setOnTop
        self.mnuHelpHelp.Click += gotoWiki
        self.mnuHelpIssues.Click += gotoIssues
        self.mnuHelpSource.Click += gotoSource
        self.mnuHelpAbout.Click += about

        self.pickDialog = FolderBrowserDialog()
        self.pickDialog.Description = "Select the Portal 2 root directory where demos are saved."
        self.pickDialog.ShowNewFolderButton = False
        self.pickDialog.RootFolder = Environment.SpecialFolder.MyComputer
        
        self.demoData = []

        portalPath = findPortal2()
        if portalPath:
            self.demoDir = portalPath
            self.pickDialog.SelectedPath = self.demoDir
            self.txtDemoDir.Text = self.demoDir
            self.btnDemoDir.ToolTip = "Currently set to: " + self.demoDir
            self.transitionWait()

    def transitionWait(self):
        self.state = STATE_WAIT
        self.lblStatus.Content = "Waiting for demo..."
        self.lblLastMap.Content = "(none)"
        self.clockTime(0)
        self.splitTime(0)
        self.demoTime = 0
        self.demoData = []
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

    def copyDemoData(self, sender, args):
        tsv = 'map\tstart tick\tend tick\n'
        tsv += '\n'.join(['\t'.join(str(f) for f in demo) for demo in self.demoData])
        Clipboard.SetText(tsv)

    def setOnTop(self, sender, args):
        self.Topmost = self.mnuViewOntop.IsChecked

    def pickDirectory(self, sender, args):
        result = self.pickDialog.ShowDialog()
        if result == DialogResult.OK:
            self.demoDir = self.pickDialog.SelectedPath
            self.txtDemoDir.Text = self.demoDir
            self.btnDemoDir.ToolTip = "Currently set to: " + self.demoDir
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
                self.lblLastMap.Content = demo1.header['map_name'].replace('_', '__')

                # resync timer and update split
                self.timeStart = time.time() - self.demoTime
                self.update_clock()
                self.splitTime(self.demoTime)

                self.demoData.append((demo1.header['map_name'], demo1.tick_start, demo1.tick_end))

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

if __name__ == '__main__':
    Application().Run(Portal2LiveTimer())