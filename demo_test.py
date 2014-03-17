import argparse

import sourcedemo

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('demo_file')
    args = parser.parse_args()

    demo = sourcedemo.Demo(args.demo_file)

    print(demo.header)
