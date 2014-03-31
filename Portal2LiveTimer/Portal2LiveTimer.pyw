#! ipyw
import clr
#clr.AddReference("System.Xml")
#clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

import wpf

from System import TimeSpan
from System.Windows import Application, Window
#from System.Windows.Forms import FolderBrowserDialog
from System.Windows.Threading import DispatcherTimer

import time

class Portal2DemoTimer(Window):
    def __init__(self):
        super(Portal2DemoTimer, self).__init__()
        wpf.LoadComponent(self, 'Portal2LiveTimer.xaml')

        self.timer = DispatcherTimer()
        #self.timer.Interval =  TimeSpan(0, 0, 0, 0, 200)
        #self.timer.Tick += self.update

        self.btnReset.Click += self.reset
        self.btnDemoDir.Click += self.selectDirectory
        
    def selectDirectory(self, sender, args):
        dialog = FolderBrowserDialog()
        result = dialog.ShowDialog()

    def reset(self, sender, args):
        pass

    def start(self, sender, args):
        self.timer.Start()
        self.timer_start = time.time()

    def update(self, sender, args):
        clock = time.time() - self.timer_start
        clock_hr = int(clock // 3600)
        clock_min = int((clock // 60) % 60)
        clock_sec = clock % 60

        if clock_hr:
            clock_fmt = '{:2d}:{:02d}:{:05.2f}'.format(clock_hr, clock_min, clock_sec)
        elif clock_min:
            clock_fmt = '{:2d}:{:05.2f}'.format(clock_min, clock_sec)
        else:
            clock_fmt = '{:5.2f}'.format(clock_sec)

        self.timerDisplay.Content = clock_fmt

if __name__ == '__main__':
    Application().Run(Portal2DemoTimer())
