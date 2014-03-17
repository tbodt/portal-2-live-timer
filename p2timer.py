#!/usr/bin/env python
import sys
import os
import argparse
import time
import itertools
import winreg
import glob

import win32com.client

import sourcedemo
import p2maps

DEFAULT_PATH = r'C:\Program Files (x86)\Steam\SteamApps\common\portal 2\portal2'

def find_portal():
    # Try the default place
    if os.path.isdir(DEFAULT_PATH):
        return DEFAULT_PATH
    else:
        # Find start menu location in registry
        # All users' start menu
        hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        hklm_startmenu_value = "Common Start Menu"
        # User's start menu
        hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
        hkcu_startmenu_value = "Start Menu"
        for registry, value in [
                    (hklm, hklm_startmenu_value),
                    (hkcu, hkcu_startmenu_value)
                ]:
            key = winreg.OpenKey(registry, r'Software\Microsoft\Windows'
                r'\CurrentVersion\Explorer\User Shell Folders')

            # check if Steam shortcut is there
            steam_shortcut = os.path.expandvars(os.path.join(
                    winreg.QueryValueEx(key, value)[0],
                    'Programs', 'Steam', 'Steam.lnk'
                ))
            if not os.path.isfile(steam_shortcut):
                continue # didn't find it

            # If so, follow the shortcut to the Steam folder
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(steam_shortcut)
            steam_folder = os.path.dirname(shortcut.Targetpath)
            p2_folder = os.path.join(steam_folder, 
                    'SteamApps', 'common', 'portal 2', 'portal2')
            if os.path.isdir(p2_folder):
                return p2_folder # found it

    return None # failure

def demos_in_directory(directory):
    return glob.glob(os.path.join(directory, '*.dem'))

class Portal2Demo(sourcedemo.Demo):
    def get_ticks(self):
        if self.header['map_name'] == p2maps.MAP_LIST[0]:
            # subtract ticks before crosshair
            pass

        elif self.header['map_name'] == p2maps.MAP_LIST[-1]:
            # subtract ticks after final shot
            pass

        else:
            return super(Portal2Demo, self).get_ticks()

def main():
    parser = argparse.ArgumentParser(description=
            "Watch a directory for new demo files and add them up.")

    parser.add_argument('-d', '--directory', help="Directory to watch.  "
            "If not specified, I try to find it.")

    args = parser.parse_args()

    # Get the directory
    if not args.directory:
        directory = find_portal()
        if directory is None:
            print("Failed to find the Portal 2 folder.  Please specify "
                  "manually using --directory (see --help for more)", 
                  file=sys.stderr)
            sys.exit(1)
    else:
        directory = args.directory

    # Set baseline for existing files
    initial = set(demos_in_directory(directory))

    processed_demos = set()

    #processed_time

    t_start = time.time()
    for i in itertools.count():
        time.sleep(1/15)
        if t_start is not None:
            # clock is running
            clock = time.time() - t_start
            clock_hr = int(clock // 3600)
            clock_min = int((clock // 60) % 60)
            clock_sec = clock % 60
            if clock_hr:
                print('{:2d}:{:02d}:{:05.2f}'.format(clock_hr, clock_min, clock_sec), end='\r')
            elif clock_min:
                print('   {:2d}:{:05.2f}'.format(clock_min, clock_sec), end='\r')
            else:
                print('      {:5.2f}'.format(clock_sec), end='\r')

        if not i % 15:
            continue

        continue
        # find new demos

        # find newly-filled demos

        # process the newly non-empty files and mark as done
        #os.path.getsize(x)...


        # recalculate current clock

        # 


        # Find new demos since start
        active_demos_now = set(demos_in_directory(directory)) - initial

        # Find new demos since last loop
        new_demos = active_demos_now - active_demos

        # Prepare for loop
        active_demos = active_demos_now
        time.sleep(1)

    # if there is a new (empty) file do a split and resync timer to 
    # sum-of-demos plus file creation time
    #sourcedemo.Demo()

if __name__ == '__main__':
    sys.exit(main())
