"""
applehealthdata.py: Extract data from Apple Health App's export.xml.
Copyright (c) 2016 Nicholas J. Radcliffe
Licence: MIT
"""
import os
import re
import sys
import random

from xml.etree import ElementTree
from collections import Counter, OrderedDict

# install icalender using following command: pip3 install icalendar
from icalendar import Calendar, Event
from datetime import datetime
from pytz import UTC   # timezone

from csv_ical import Convert


__version__ = '1.3'

# Randomly generate a float for deviceID
RAND = str(random.random())

RECORD_FIELDS = OrderedDict((
    #('sourceName', 's'),
    #('sourceVersion', 's'),
    ('device', 's'),
    #('type', 's'),
    #('unit', 's'),
    #('creationDate', 'd'),
    ('startDate', 'd'),
    #('endDate', 'd'),
    ('value', 'n'),
))

ACTIVITY_SUMMARY_FIELDS = OrderedDict((
    ('dateComponents', 'd'),
    ('activeEnergyBurned', 'n'),
    ('activeEnergyBurnedGoal', 'n'),
    ('activeEnergyBurnedUnit', 's'),
    ('appleExerciseTime', 's'),
    ('appleExerciseTimeGoal', 's'),
    ('appleStandHours', 'n'),
    ('appleStandHoursGoal', 'n'),
))

WORKOUT_FIELDS = OrderedDict((
    ('sourceName', 's'),
    ('sourceVersion', 's'),
    ('device', 's'),
    ('creationDate', 'd'),
    ('startDate', 'd'),
    ('endDate', 'd'),
    ('workoutActivityType', 's'),
    ('duration', 'n'),
    ('durationUnit', 's'),
    ('totalDistance', 'n'),
    ('totalDistanceUnit', 's'),
    ('totalEnergyBurned', 'n'),
    ('totalEnergyBurnedUnit', 's'),
))

FIELDS = {
    'Record': RECORD_FIELDS,
    'ActivitySummary': ACTIVITY_SUMMARY_FIELDS,
    'Workout': WORKOUT_FIELDS,
}

PREFIX_RE = re.compile('^HK.*TypeIdentifier(.+)$')
ABBREVIATE = True
VERBOSE = False

1


def format_freqs(counter):
    """
    Format a counter object for display.
    """
    return '\n'.join('%s: %d' % (tag, counter[tag])
                     for tag in sorted(counter.keys()))


def format_value(value, datatype):
    """
    Format a value for a CSV file, escaping double quotes and backslashes.
    None maps to randomly generated float in interval [0,1], converted to a string.
    datatype should be
        's' for string (escaped)
        'n' for number
        'd' for datetime
    """
    if value is None or datatype == 's':  # DeviceID should be a randomized float
        return RAND
    # elif datatype == 's':  # string
    #    return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')
    elif datatype == 'n':  # number (round to nearest int and convert back to string)
        return str(round(float(value)))
    elif datatype == 'd':  # date
        return value
    else:
        raise KeyError('Unexpected format value: %s' % datatype)


def abbreviate(s, enabled=ABBREVIATE):
    """
    Abbreviate particularly verbose strings based on a regular expression
    """
    m = re.match(PREFIX_RE, s)
    return m.group(1) if enabled and m else s


class HealthDataExtractor(object):
    """
    Extract health data from Apple Health App's XML export, export.xml.
    Inputs:
        path:      Relative or absolute path to export.xml
        verbose:   Set to False for less verbose output
    Outputs:
        Writes a CSV file for each record type found, in the same
        directory as the input export.xml. Reports each file written
        unless verbose has been set to False.
    """

    def __init__(self, path, verbose=VERBOSE):
        self.in_path = path
        self.verbose = verbose
        self.directory = os.path.abspath(os.path.split(path)[0])
        with open(path) as f:
            self.report('Reading data from %s . . . ' % path, end='')
            self.data = ElementTree.parse(f)
            self.report('done')
        self.root = self.data._root
        self.nodes = list(self.root)
        self.n_nodes = len(self.nodes)
        self.abbreviate_types()
        self.collect_stats()

    def report(self, msg, end='\n'):
        if self.verbose:
            print(msg, end=end)
            sys.stdout.flush()

    def count_tags_and_fields(self):
        self.tags = Counter()
        self.fields = Counter()
        for record in self.nodes:
            self.tags[record.tag] += 1
            for k in record.keys():
                self.fields[k] += 1

    def count_record_types(self):
        """
        Counts occurrences of each type of (conceptual) "record" in the data.
        In the case of nodes of type 'Record', this counts the number of
        occurrences of each 'type' or record in self.record_types.
        In the case of nodes of type 'ActivitySummary' and 'Workout',
        it just counts those in self.other_types.
        The slightly different handling reflects the fact that 'Record'
        nodes come in a variety of different subtypes that we want to write
        to different data files, whereas (for now) we are going to write
        all Workout entries to a single file, and all ActivitySummary
        entries to another single file.
        """
        self.record_types = Counter()
        self.other_types = Counter()
        for record in self.nodes:
            if record.tag == 'Record':
                self.record_types[record.attrib['type']] += 1
            elif record.tag in ('ActivitySummary', 'Workout'):
                self.other_types[record.tag] += 1
            elif record.tag in ('Export', 'Me'):
                pass
            else:
                self.report('Unexpected node of type %s.' % record.tag)

    def collect_stats(self):
        self.count_record_types()
        self.count_tags_and_fields()

    def open_for_writing(self, user):
        self.handles = {}
        self.paths = []
        for kind in (list(self.record_types) + list(self.other_types)):
            # Only open what I need: Heart Rate
            if kind == "HeartRate":
                path = os.path.join(self.directory, user + '%s.csv' %
                                    abbreviate(kind))
                f = open(path, 'w')
                headerType = (kind if kind in ('Workout', 'ActivitySummary')
                              else 'Record')
                f.write('username,' + ','.join(FIELDS[headerType].keys()) + '\n')
                self.handles[kind] = f
                self.report('Opening %s for writing' % path)

    def abbreviate_types(self):
        """
        Shorten types by removing common boilerplate text.
        """
        for node in self.nodes:
            if node.tag == 'Record':
                if 'type' in node.attrib:
                    node.attrib['type'] = abbreviate(node.attrib['type'])

    def write_records(self,user):
        kinds = FIELDS.keys()
        for node in self.nodes:
            if node.tag in kinds:
                attributes = node.attrib
                kind = attributes['type'] if node.tag == 'Record' else node.tag
                # Only write what I need: Heart Rate
                if kind == "HeartRate":
                    values = [format_value(attributes.get(field), datatype)
                              for (field, datatype) in FIELDS[node.tag].items()]
                    line = user + ',' + ','.join(values) + '\n' #Insert user name at beginning of line
                    self.handles[kind].write(line)

    def close_files(self):
        for (kind, f) in self.handles.items():
            f.close()
            self.report('Written %s data.' % abbreviate(kind))

    def extract(self, user):
        self.open_for_writing(user)
        self.write_records(user)
        self.close_files()

    def report_stats(self):
        print('\nTags:\n%s\n' % format_freqs(self.tags))
        print('Fields:\n%s\n' % format_freqs(self.fields))
        print('Record types:\n%s\n' % format_freqs(self.record_types))


def parseHealthData(users):
    for user in users:
        f = user + ".xml"
        data = HealthDataExtractor(f)
        # data.report_stats()
        print("Extracting data from " + user + "'s file")
        data.extract(user)


def parseCalenderData(users):
    for user in users:
        convert = Convert()
        convert.CSV_FILE_LOCATION = user + 'Cal.csv'
        convert.SAVE_LOCATION = user + '.ics'
        convert.read_ical(convert.SAVE_LOCATION)
        convert.make_csv()
        convert.save_csv(convert.CSV_FILE_LOCATION)

    # https://stackoverflow.com/questions/3408097/parsing-files-ics-icalendar-using-python
   # for user in users:

  #  f = user + ".ics"
   # g = open(f, 'rb')
   # gcal = Calendar.from_ical(g.read())
   # for component in gcal.walk():
   #     if component.name == "VEVENT":
   #         print(component.get('summary'))
   #         start = component.get('dtstart')
   #         end = component.get('dtend')
   #         stamp = component.get('dtstamp')
   #         print(start.dt)
   #         print(end.dt)
   #         print(stamp.dt)
#
   #         # TODO open and write to .csv
   # g.close()


if __name__ == '__main__':
    # if len(sys.argv) != 2:
    #    print('USAGE: python main.py /path/to/export.xml',
    #         file=sys.stderr)
    #   sys.exit(1)
    # enter file to be parsed within quotes here
    users = ["Cam"]
    parseHealthData(users)
    # parseCalenderData(users)
    print("Data extracted")
