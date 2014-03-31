#! ipyw
import clr
#clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

import wpf

from System import TimeSpan, Environment
from System.Windows import Application, Window
from System.Windows.Forms import FolderBrowserDialog, DialogResult
from System.Windows.Threading import DispatcherTimer

import time

class Portal2LiveTimer(Window):
    def __init__(self):
        wpf.LoadComponent(self, 'Portal2LiveTimer.xaml')

        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan(0, 0, 0, 0, 30)
        self.timer.Tick += self.update

        self.btnDemoDir.Click += self.pickDirectory
        self.btnReset.Click += self.start

        self.pickDialog = FolderBrowserDialog()
        self.pickDialog.Description = "Select the Portal 2 root directory where demos are saved."
        self.pickDialog.ShowNewFolderButton = False
        self.pickDialog.RootFolder = Environment.SpecialFolder.MyComputer

    def pickDirectory(self, sender, args):
        result = self.pickDialog.ShowDialog()
        if result == DialogResult.OK:
            self.demoDir = self.pickDialog.SelectedPath
            self.txtDemoDir.Text = self.demoDir

    def start(self, sender, args):
        self.timer.Start()
        self.timer_start = time.time()

    def update(self, sender, args):
        clock = time.time() - self.timer_start
        clock_hr = int(clock // 3600)
        clock_min = int((clock // 60) % 60)
        clock_sec = clock % 60

        if clock_hr:
            clock_fmt = '{:2d}:{:02d}:{:05.1f}'.format(clock_hr, clock_min, clock_sec)
        elif clock_min:
            clock_fmt = '{:2d}:{:05.1f}'.format(clock_min, clock_sec)
        else:
            clock_fmt = '{:5.1f}'.format(clock_sec)

        self.lblTimerLive.Content = clock_fmt

if __name__ == '__main__':
    Application().Run(Portal2LiveTimer())
