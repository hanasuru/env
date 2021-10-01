#!/usr/bin/python2
from datetime import datetime
from datetime import timedelta
from datetime import tzinfo
from calendar import timegm
from argparse import ArgumentParser
from collections import OrderedDict

import struct
import os


HEADER = '\x05\x00\x00\x00\x00\x00\x00\x00\x05\x00\x00\x00\x20\x03\x00\x00\x00\x00\x00\x00'
DEFAULT_DRIVE = 'C'
DEFAULT_DIR = os.getcwd()
RECYCLE_DIR = (
#     DEFAULT_DIR
#   + '/../../'
    '/Recycler'
  + '/S-1-5-21-4120123742-30011560200-102401200-1001/'
)

INFO2DIR = RECYCLE_DIR + 'INFO2'

LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
EPOCH_AS_FILETIME = 116444736000000000  # January 1, 1970 as MS file time
HUNDREDS_OF_NANOSECONDS = 10000000
HOUR = timedelta(hours=1)

def unix2win(path):
    return path.replace('/','\\')

def pad(text, buffer):
    return text.ljust(buffer, '\x00')

def insert(text, buffer):
    return '\x00'.join(text).ljust(buffer, '\x00')

def listing(path, mode):
    result = []

    for r, d, f in os.walk(path):
        for _ in eval(mode):
            abspath = os.path.join(r, _)
            result.append(abspath)

    return result

class UTC(tzinfo):
    def utcoffset(self, dt):
        return timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return timedelta(0)


utc = UTC()


class UTCTime(object):
    @staticmethod
    def time_to_date(ft):
        try:
            return datetime.utcfromtimestamp((ft - EPOCH_AS_FILETIME) / HUNDREDS_OF_NANOSECONDS)
        except ValueError:
            return 'year is out of range'

    @staticmethod
    def date_to_time(dt):
        if (dt.tzinfo is None) or (dt.tzinfo.utcoffset(dt) is None):
            dt = dt.replace(tzinfo=utc)
    
        return EPOCH_AS_FILETIME + (timegm(dt.timetuple()) * HUNDREDS_OF_NANOSECONDS)


class INFO2(object):
    def __init__(self, path, current_id, existed=True):
        self.path = path
        self.existed = existed
        self.current_id = current_id

    @property
    def status(self):
        if os.path.isdir(self.path):
            return 'dir'
        
        return 'file'

    @property
    def content(self):
        if os.path.isfile(self.path):
            with open(self.path, 'rb') as handle:
                return handle.read()

    @property
    def record_id(self):
        return struct.pack('<I', self.current_id)

    @property
    def original_path(self):
        if self.existed:
            rootdir = DEFAULT_DRIVE + ':'
        else:
            rootdir = '\x00:'

        target = [rootdir] + self.path.split('/')

        return unix2win(os.path.join(*target))

    @property
    def original_drive(self):
        return struct.pack(
            '<I', 
            LETTERS.index(DEFAULT_DRIVE)
        )

    @property
    def deleted_time(self):
        current_time = datetime.now()
        return struct.pack(
            '<Q',
            UTCTime.date_to_time(current_time)
        )

    @property
    def filesize(self):
        if os.path.isdir(self.path):
            size = 4096
        else:
            size = os.path.getsize(self.path)

        return struct.pack('<I', size)

    @property
    def unicode_name(self):
        return (
            DEFAULT_DRIVE
          + self.original_path[1:]
        )

    @property
    def records(self):
        template = '%s%s%s%s%s%s'
        content = template % (
            pad(self.original_path, 260),
            self.record_id,
            self.original_drive,
            self.deleted_time,
            self.filesize,
            insert(self.unicode_name, 520)           
        )

        assert (len(content) == 800)

        return content

    @property
    def deleted_name(self):
        if os.path.split(self.path)[-1].startswith('.'):
            target = 'a' + self.path
        else:
            target = self.path

        target = os.path.split(self.path)[-1]
        target = os.path.splitext(target)[-1]

        return 'D%s%s%s' % (DEFAULT_DRIVE, self.current_id, target)


class Recycler(object):
    def __init__(self, path, existed=True):
        self.path = path
        self.info = OrderedDict()
        self.index = self.get_latest_index()
        self.existed = existed

    def get_latest_index(self):
        
        if os.path.exists(INFO2DIR):
            with open(INFO2DIR, 'rb') as handle:
                byte = handle.read()

            if len(byte) == 20:
                return 1

            return struct.unpack('<I', byte[-540:-536])[0] + 1

        return 1

    def run(self):
        root_dir = self.path.split('/')[0]
        self.info[root_dir] = INFO2(root_dir, self.index)
        # self.index += 1

        if os.path.isdir(self.path):
            files = listing(self.path, 'f')
            folder = listing(self.path, 'd')

            for lists in sorted(files + folder):
                if os.path.islink(lists):
                    continue
                # elif os.path.split(lists)[-1].startswith('.'):
                    # continue

                self.info[lists] = INFO2(lists, self.index, self.existed)
                self.index += 1
        elif os.path.isfile(self.path):
            print(self.path)
            self.info[self.path] = INFO2(self.path, self.index, self.existed)
            self.index += 1

    def update(self):
        if not os.path.exists(RECYCLE_DIR):
            os.makedirs(RECYCLE_DIR)

        if not os.path.exists(INFO2DIR):
            with open(INFO2DIR, 'wb') as handle:
                handle.write(HEADER)
 
        with open(INFO2DIR, 'ab') as handle:
            for k,v in self.info.items():
                base = v.path.split('/')
                fullpath = []
                tmp = ''

                for i in base:
                    val = self.info[os.path.join(tmp, i)]
                    fullpath += [val.deleted_name]
                    tmp = os.path.join(tmp, i)

                target = os.path.join(
                    RECYCLE_DIR, *fullpath
                )   

                print target
                print
                print base
                # break
                if v.content:
                    with open(target, 'wb') as file:
                        file.write(v.content)
                elif not self.existed:
                    pass
                else:
                    os.makedirs(target)

                handle.write(v.records)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('path', metavar='pathname', help='target path')
    parser.add_argument('--drive', metavar='drive_letter', default='C', help='drive origin')
    parser.add_argument('--gone', action='store_false', help='Deleted permanently/restored')

    arguments = parser.parse_args()
    DEFAULT_DRIVE = arguments.drive

    r = Recycler(arguments.path, arguments.gone)
    r.run()
    r.update()
