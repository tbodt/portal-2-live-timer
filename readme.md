Portal 2 Live Timer
===================

A timer for those who complain "Portal 2 isn't timed as RTA".

Usage
-----
1. Tell the program where your Portal 2 demo folder is (if it didn't detect it)
2. Start recording demos in Portal 2.
3. Go fast.

What it's doing
---------------
The program checks the demo folder every so often for new, recorded demos.  When it finds one that has been written out, it processes it to find the number of ticks within, and adds them to the split timer.  It also resets the counting timer to that split, so there is no accumulated error between real-time and demo time.  The most the timer *should* be off is a single map load.
    
It's broken/It doesn't X
------------------------
Report bugs and feature requests [here][issues].

[issues]: https://bitbucket.org/nick_timkovich/portal-2-live-timer/issues
