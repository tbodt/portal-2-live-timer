import argparse

import sourcedemo

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('demo_file')
    args = parser.parse_args()

    demo = sourcedemo.Demo(args.demo_file)

    print(demo.header)
    print(demo.tick_start, demo.tick_end, demo.get_ticks())
    print(demo.get_time())
