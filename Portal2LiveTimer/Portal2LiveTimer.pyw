#! ipyw
from __future__ import division
import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

__version__ = '0.1.6'

import wpf

from System import TimeSpan, Environment, Type, Activator, Exception
from System.Windows import Application, Window, MessageBox, Clipboard, Visibility, Controls, MessageBoxButton, MessageBoxImage
from System.Windows.Forms import FolderBrowserDialog, DialogResult, SaveFileDialog, OpenFileDialog
from System.Windows.Threading import DispatcherTimer
from System import IO

from System.Diagnostics import Debug

import os
import itertools
import glob
import time
import webbrowser
import csv

from sourcedemo import Demo, DemoProcessError
from p2maps import MAPS, ALL_MAPS
from mapsort import parse_csv, DemoParseException, combine_maps, startstop_to_ticks, combine_chapters

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

def chapterSplits(demodata):
    map_times = combine_maps(startstop_to_ticks(demodata), validate=False)
    rec_maps = set([mapn for mapn, ticks in map_times.iteritems() if ticks > 0])

    ch_times = combine_chapters(map_times)
    ch_splits = [None] * len(MAPS)

    # check that chapters are complete
    last_ch = 0
    for i, chapter in enumerate(MAPS):
        if set(chapter).issubset(rec_maps):
            ch_splits[i] = last_ch + ch_times[i]
            last_ch = ch_splits[i]
        else:
            break

    return ch_splits

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
        wpf.LoadComponent(self, 'Portal2LiveTimer.xaml')
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
        #self.mnuFileLoad.Click += self.loadDemoCSV
        self.mnuFileExit.Click += lambda sender, args: self.Close()

        self.mnuEditCopy.Click += self.copyDemoData
        self.mnuViewOntop.Click += self.setOnTop
        #self.mnuViewBgKey += self.backgroundColor
        #self.mnuViewBgReset += self.backgroundReset
        self.mnuHelpHelp.Click += gotoWiki
        self.mnuHelpIssues.Click += gotoIssues
        self.mnuHelpSource.Click += gotoSource
        self.mnuHelpAbout.Click += about

        self.pickDialog = FolderBrowserDialog()
        self.pickDialog.Description = "Select the Portal 2 root directory where demos are saved."
        self.pickDialog.ShowNewFolderButton = False
        self.pickDialog.RootFolder = Environment.SpecialFolder.MyComputer

        self.saveDialog = SaveFileDialog()
        self.saveDialog.Title = "Select where to save demo timings"
        self.saveDialog.Filter = "CSV files (*.csv)|*.csv|All files (*.*)|*.*"
        
        self.demoData = []
        self.splitData = []
        self.lblTChs = [self.lblTCh1, self.lblTCh2, self.lblTCh3, 
                        self.lblTCh4, self.lblTCh5, self.lblTCh6, 
                        self.lblTCh7, self.lblTCh8, self.lblTCh9]

        portalPath = findPortal2()
        if portalPath:
            self.demoDir = portalPath
            self.pickDialog.SelectedPath = self.demoDir
            self.txtDemoDir.Text = self.demoDir
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
        self.splitChapters([None] * len(MAPS))
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

    def saveDemoCSV(self, sender, args):
        result = self.saveDialog.ShowDialog()
        if result == DialogResult.OK and self.saveDialog.FileName:
            try:
                saveDemoCSV(self.saveDialog.FileName, self.demoData)
            except IOError:
                MessageBox.Show("Error saving file", "Error saving", MessageBoxButton.OK, MessageBoxImage.Error)

    def loadDemoCSV(self, sender, args):
        pass

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
                self.timeStart = time.time() - self.demoTime
                self.update_clock()
                self.splitTime(self.demoTime)

                self.demoData.append((demo1.header['map_name'], demo1.tick_start, demo1.tick_end))
                ch_splits = chapterSplits(self.demoData)
                self.splitChapters(ch_splits)

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

    def splitChapters(self, current_splits, past_splits=None):
        if past_splits is None:
            for label, split in zip(self.lblTChs, current_splits):
                if split is not None:
                    label.Content = formatTime(split/60.0, 1)
                else:
                    label.Content = '---'


if __name__ == '__main__':
    Application().Run(Portal2LiveTimer())