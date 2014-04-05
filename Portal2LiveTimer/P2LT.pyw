#! ipyw
from __future__ import division
import clr
#clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

clr.AddReferenceToFileAndPath("IronPython.Wpf.dll")

__version__ = '0.1.0'

import wpf

from System import TimeSpan, Environment, Type, Activator, Exception
from System.Windows import Application, Window, MessageBox
from System.Windows.Forms import FolderBrowserDialog, DialogResult
from System.Windows.Threading import DispatcherTimer
from System import IO
from System.Text import ASCIIEncoding

from System.Diagnostics import Debug

import os
import glob
import time
import webbrowser
import io
import struct

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

            if (command == Commands.CONSOLE_CMD and 
                    data == b'ss_force_primary_fullscreen 0'):
                print(tick)
                self.tick_start = tick

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

xamlStream = IO.MemoryStream(ASCIIEncoding.ASCII.GetBytes("""
<Window 
       xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" 
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" 
       xmlns:d="http://schemas.microsoft.com/expression/blend/2008" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="d" 
       Title="Portal 2 Live Timer" ResizeMode="CanMinimize" Width="562" Height="294">
    <DockPanel>
        <Menu DockPanel.Dock="Top">
            <MenuItem Header="_Edit" Margin="2">
                <MenuItem Header="_Copy map/time data to clipboard" IsEnabled="False"/>
            </MenuItem>
            <MenuItem Header="_Help" Margin="2">
                <MenuItem x:Name="mnuHelpHelp" Header="_Usage"/>
                <Separator/>
                <MenuItem x:Name="mnuHelpSource" Header="_Source Repo"/>
                <MenuItem x:Name="mnuHelpIssues" Header="_Bugs/Feature Requests"/>
                <Separator/>
                <MenuItem x:Name="mnuHelpAbout" Header="_About"/>
            </MenuItem>
        </Menu>
        <StatusBar DockPanel.Dock="Bottom">
            <StatusBarItem>
                <TextBlock x:Name="tblkVersion" TextWrapping="Wrap" Text="version ?"/>
            </StatusBarItem>
        </StatusBar>
        <Grid>
            <Label x:Name="lblTimerLive" Content="0:00" Margin="0,7,7,0" VerticalAlignment="Top" FontSize="48" FontWeight="Bold" HorizontalAlignment="Right"/>
            <Button x:Name="btnDemoDir" Content="Demo Directory" HorizontalAlignment="Right" Height="23" Margin="0,135,10,0" VerticalAlignment="Top" Width="94"/>
            <Label x:Name="lblLastMap" Content="(none)" Margin="10,88,0,0" VerticalAlignment="Top" FontSize="24" FontWeight="Bold" Height="42" HorizontalAlignment="Left"/>
            <Label Content="Last Map" HorizontalAlignment="Left" Margin="10,77,0,0" VerticalAlignment="Top"/>
            <Label Content="Estimated Time" Margin="0,5,10,0" VerticalAlignment="Top" HorizontalAlignment="Right"/>
            <Label Content="Last Demo Split" Margin="0,77,10,0" VerticalAlignment="Top" HorizontalAlignment="Right"/>
            <Label x:Name="lblTimerSplit" Content="0:00.000" Margin="0,88,10,0" VerticalAlignment="Top" FontSize="24" FontWeight="Bold" HorizontalAlignment="Right" Height="42"/>
            <TextBox x:Name="txtDemoDir" Height="23" Margin="10,135,109,0" TextWrapping="Wrap" Text="Choose where demos are saved." VerticalAlignment="Top" IsEnabled="False"/>
            <Label Content="Status" Margin="10,7,0,0" VerticalAlignment="Top" HorizontalAlignment="Left"/>
            <Label x:Name="lblStatus" Content="Select Portal 2 path." Margin="10,19,0,0" VerticalAlignment="Top" FontSize="24" FontWeight="Bold" Height="42" HorizontalAlignment="Left"/>
            <Button x:Name="btnReset" Content="Reset" HorizontalAlignment="Left" Height="30" Margin="10,174,0,0" VerticalAlignment="Top" Width="62" RenderTransformOrigin="0.581,-0.067"/>

        </Grid>
    </DockPanel>
</Window> 
"""))
#xamlStream.Seek(0, IO.SeekOrigin.Begin)

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
playthroughs.  For details of use, see the Bitbucket Wiki (Help/Wiki).

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

        self.mnuHelpHelp.Click += gotoWiki
        self.mnuHelpIssues.Click += gotoIssues
        self.mnuHelpSource.Click += gotoSource
        self.mnuHelpAbout.Click += about

        self.pickDialog = FolderBrowserDialog()
        self.pickDialog.Description = "Select the Portal 2 root directory where demos are saved."
        self.pickDialog.ShowNewFolderButton = False
        self.pickDialog.RootFolder = Environment.SpecialFolder.MyComputer
        
        portalPath = findPortal2()
        if portalPath:
            self.demoDir = portalPath
            self.txtDemoDir.Text = self.demoDir
            self.transitionWait()

    def transitionWait(self):
        self.state = STATE_WAIT
        self.lblStatus.Content = "Waiting for demo..."
        self.lblLastMap.Content = "(none)"
        self.clockTime(0)
        self.demoTime = 0
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

    def pickDirectory(self, sender, args):
        result = self.pickDialog.ShowDialog()
        if result == DialogResult.OK:
            self.demoDir = self.pickDialog.SelectedPath
            self.txtDemoDir.Text = self.demoDir
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
                self.lblTimerSplit.Content = formatTime(self.demoTime, 3)

                self.processedDemos.add(demo_file)
                self.unprocessedDemos.remove(demo_file)
                if demo1.tick_end_game:
                    self.transitionComplete()
                else:
                    self.lblStatus.Content = "Monitoring ({}+{} demos)...".format(len(self.processedDemos), len(self.unprocessedDemos))
            except DemoProcessError:
                pass

    def update_clock(self):
        clock = time.time() - self.timeStart
        self.clockTime(clock)

    def clockTime(self, seconds):
        self.lblTimerLive.Content = formatTime(seconds)

if __name__ == '__main__':
    Application().Run(Portal2LiveTimer())
