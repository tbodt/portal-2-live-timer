#!/usr/bin/env python
import sys
import os
import argparse
import time

import sourcedemo
import p2maps

def main():
    parser = argparse.ArgumentParser(description=
            "Watch a directory for new demo files and add them up.")

    parser.add_argument('-d', '--directory', help="Directory to watch.  "
            "If not specified, I try to find it.")

    args = parser.parse_args()

    # watch directory for new demo files

    # if there is a new (empty) file do a split and resync timer to 
    # sum-of-demos plus file creation time
    #sourcedemo.Demo()

if __name__ == '__main__':
    sys.exit(main())
