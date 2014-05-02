# map sort test
import csv
import itertools
import collections

from p2maps import MAPS

ALL_MAPS = list(itertools.chain.from_iterable(MAPS))
N_MAPS = len(ALL_MAPS)

class DemoParseException(Exception):
    pass

def parse_demodata(file):
    """
    Takes a file path and returns a list of 2-tuples with map name and
    ticks taken.

    Demo file can be 2 or 3 columns and optionally have a header.  The format
    of a 2-column CSV is assumed to be (map name, ticks), and the 3-column
    format to be (map name, start tick, end tick)
    """
    try:
        with open(file, 'r') as f:
            has_header = csv.Sniffer().has_header(f.read(1024))
            f.seek(0)
            print(has_header)

            democsv = csv.reader(f)
            header = next(democsv) if has_header else None

            data = [row for row in democsv]
    except IOError as e:
        raise DemoParseException("Could not read file")
    except csv.Error as e:
        raise DemoParseException("Could not parse file as CSV")

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
        raise DemoParseException("Error converting data, ensure ticks are integers")

    return data

def validate_times(map_times, ignore_credits=True):
    if ignore_credits:
        missing_maps = set(ALL_MAPS[:-1]) - set(map_times)
    else:
        missing_maps = set(ALL_MAPS) - set(map_times)
    unknown_maps = set(map_times) - set(ALL_MAPS)

    if missing_maps:
        raise DemoParseException("Data file missing {} map(s) for complete run: {}".format(len(missing_maps), ', '.join(missing_maps)))
    if unknown_maps:
        raise DemoParseException("Data file contains {} unrecognized map(s): {}".format(len(unknown_maps), ', '.join(unknown_maps)))

def combine_maps(data, validate=True):
    # sum ticks
    map_times = collections.defaultdict(int)
    for mapn, ticks in data:
        map_times[mapn] += ticks

    if validate:
        validate_times(map_times)

    return map_times

def sort_maps(map_times):
    """
    Takes a dictionary with maps as keys and ticks as values and returns a
    sorted list-of-items (tuples) representation.
    """
    map_times_sorted = sorted(map_times.items(), key=lambda x: ALL_MAPS.index(x[0]))
    return map_times_sorted

def chapter_ticks(map_times):
    """
    Takes a dictionary with maps as keys and ticks as values and returns a
    list of ticks based on chapters
    """
    chapter_times = [0 for _ in MAPS]
    for i, chapter in enumerate(MAPS):
        for mapn in chapter:
            chapter_times[i] += map_times[mapn]

    return chapter_times

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('demodata')
    args = parser.parse_args()

    print(chapter_ticks(combine_maps(parse_demodata(args.demodata), validate=False)))

if __name__ == '__main__':
    main()
