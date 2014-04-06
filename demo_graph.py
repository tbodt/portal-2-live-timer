#! python3
import argparse

import numpy as np
import matplotlib.pyplot as plt

import sourcedemo

def on_xlim_changed(ax):
    xlim = ax.get_xlim()
    for a in ax.figure.axes:
        # shortcuts: last avoids n**2 behavior when each axis fires event
        if a is ax or len(a.lines) == 0 or getattr(a, 'xlim', None) == xlim:
            continue

        ylim = np.inf, -np.inf
        for l in a.lines:
            x, y = l.get_data()
            # faster, but assumes that x is sorted
            start, stop = np.searchsorted(x, xlim)
            yc = y[max(start-1,0):(stop+1)]
            ylim = min(ylim[0], np.nanmin(yc)), max(ylim[1], np.nanmax(yc))

        # TODO: update limits from Patches, Texts, Collections, ...

        # x axis: emit=False avoids infinite loop
        a.set_xlim(xlim, emit=False)

        # y axis: set dataLim, make sure that autoscale in 'y' is on 
        corners = (xlim[0], ylim[0]), (xlim[1], ylim[1])
        a.dataLim.update_from_data_xy(corners, ignore=True, updatex=False)
        a.autoscale(enable=True, axis='y')
        # cache xlim to mark 'a' as treated
        a.xlim = xlim


class Tracker(object):
    def __init__(self):
        self.xyz = []
        self.ticks = []

    def log_pos(self, tick, data):
        if not self.ticks or tick > self.ticks[-1]:
            self.ticks.append(tick)
            self.xyz.append(data)

    def show(self):
        f, ax = plt.subplots(nrows=3, sharex=True)
        x, y, z = zip(*self.xyz)

        ax[0].plot(self.ticks, x)
        ax[1].plot(self.ticks, y)
        ax[2].plot(self.ticks, z)

        for a in ax:
            a.callbacks.connect('xlim_changed', on_xlim_changed)

        plt.show()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('demo_file')
    args = parser.parse_args()

    demo = sourcedemo.Demo(args.demo_file)

    tracker = Tracker()
    callbacks = {sourcedemo.Commands.PACKET: tracker.log_pos}

    demo.process(callbacks)
    demo.demo.close()

    print(demo.header)
    print(demo.tick_start, demo.tick_end, demo.get_ticks())
    print(demo.get_time())

    tracker.show()
