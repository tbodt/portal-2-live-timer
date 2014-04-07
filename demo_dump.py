#! python3
from __future__ import print_function
import argparse
import struct
import collections

import numpy as np
import matplotlib.pyplot as plt

import sourcedemo

class Dumper(object):
    def __init__(self, **kwargs):
        self.include = None
        self.exclude = None
        self.all = set(sourcedemo.COMMAND_NAME.keys())
        if 'include' in kwargs:
            self.include = set(kwargs['include'])
        elif 'exclude' in kwargs:
            self.exclude = self.all - set(kwargs['exclude'])
        else:
            self.include = self.all

        self.handlers = {
            sourcedemo.Commands.PACKET: self.format_packet,
            sourcedemo.Commands.USER_CMD: self.format_usercmd,
        }
        self.last_tick = None

    def dump(self, command, tick, data):
        if command not in self.include:
            return

        if self.last_tick != tick:
            print('{:6d} : '.format(tick), end='')
        else:
            print('{:6s} : '.format(''), end='')

        print('{:12s} : '.format(sourcedemo.COMMAND_NAME[command]), end='')

        print(self.handlers.get(command, self.format_blind)(data))
        self.last_tick = tick

    def format_packet(self, data):
        return 'x:{:+9.2f}  y:{:+9.2f}  z:{:+9.2f}'.format(*data)

    def format_usercmd(self, data):
        fmt = ''

        # ???
        fmt += '({:6d}) '.format(struct.unpack('i', data[:4])[0])
        # ???
        fmt += '({:6d}) '.format(struct.unpack('i', data[4:8])[0])

        fmt += ' '.join(format(ord(d), '02X') for d in data[8:])
        return fmt

    def format_blind(self, data):
        return (' '.join(format(ord(d), '02X') for d in data) + '\n' +
            '                       ' + str(data))

def print_packet(tick, data):
    print_data(tick, 'x:{:+9.2f}  y:{:+9.2f}  z:{:+9.2f}'.format(*data))

def print_data(tick, data):
    print('{:6d} : {}'.format(tick, data))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Print ALL the packets in '
        'the demo between tick_start and tick_stop.')
    parser.add_argument('demo_file')
    parser.add_argument('tick_start', type=int)
    parser.add_argument('tick_stop', type=int)
    args = parser.parse_args()

    dumper = Dumper()
    demo = sourcedemo.Demo(args.demo_file)

    # callbacks = {
    #     sourcedemo.Commands.PACKET: print_packet,
    # }

    for command, tick, data in demo._process_commands():
        if args.tick_start <= tick <= args.tick_stop:
            dumper.dump(command, tick, data)

    demo.demo.close()

    print(demo.header)
    print(demo.tick_start, demo.tick_end, demo.get_ticks())
    print(demo.get_time())
