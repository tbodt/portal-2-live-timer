# map sort test
import csv
import itertools
import collections

from p2maps import MAPS

ALL_MAPS = list(itertools.chain.from_iterable(MAPS))
N_MAPS = len(ALL_MAPS)

def sort_maps(data):
    pass

def group_maps(data):
    pass

class DemoParseException(Exception):
    pass

def parse_demodata(democsvfn):

    with open(democsvfn, 'r') as f:
        has_header = csv.Sniffer().has_header(f.read(1024))
        f.seek(0)
        print(has_header)

        democsv = csv.reader(f)
        header = next(democsv) if has_header else None

        data = [row for row in democsv]

    problems = []

    data_len = len(data)
    if data_len == 0:
        raise DemoParseException("Empty data file")

    field_len = len(header if header else data[0])
    if not (2 <= field_len <= 3):
        raise DemoParseException("Data file must have 2 (map/ticks) or 3 (map/start tick/stop tick) fields ({} detected)".format(field_len))

    # make sure it's all the same size
    for i, row in enumerate(data, start=1):
        if len(row) != field_len:
            raise DemoParseException("Row {} is differently sized than other rows ({} long, expected {})".format(i+1 if header else i, len(row), field_len))

    # convert strings into numbers
    try:
        if field_len == 3:
            data = [(mapn, int(stop) - int(start)) for mapn, start, stop in data]
        elif field_len == 2:
            data = [(mapn, int(ticks)) for mapn, ticks in data]
    except ValueError as e:
        raise DemoParseException("Error when converting data, ensure the ticks are provided as integers")

    # sum ticks
    map_times = collections.defaultdict(int)
    for mapn, ticks in data:
        map_times[mapn] += ticks

    missing_maps = set(ALL_MAPS) - set(map_times)
    unknown_maps = set(map_times) - set(ALL_MAPS)

    # if missing_maps:
    #     raise DemoParseException("Data file missing {} map(s) for complete run: {}".format(len(missing_maps), ', '.join(missing_maps)))
    if unknown_maps:
        raise DemoParseException("Data file contains {} unrecognized map(s): {}".format(len(unknown_maps), ', '.join(unknown_maps)))

    map_times_sorted = sorted(map_times.items(), key=lambda x: ALL_MAPS.index(x[0]))

    chapter_times = [0 for _ in MAPS]
    for i, chapter in enumerate(MAPS):
        for mapn in chapter:
            chapter_times[i] += map_times[mapn]

    print(map_times_sorted)
    print(chapter_times)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('demodata')
    args = parser.parse_args()

    parse_demodata(args.demodata)

if __name__ == '__main__':
    main()