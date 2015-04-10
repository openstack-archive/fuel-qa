#!/usr/bin/env python3

# Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
This tool can extract the useful lines from Astute and Puppet logs
within the Fuel log snapshot or on the live Fuel Master node.

usage: fuel_logs [-h] [--astute] [--puppet] [--clear] [--sort] [--evals]
                 [--mcagent] [--less]
                 [SNAPSHOT [SNAPSHOT ...]]

positional arguments:
  SNAPSHOT       Take logs from these snapshots

optional arguments:
  -h, --help     show this help message and exit
  --astute, -a   Parse Astute log
  --puppet, -p   Parse Puppet logs
  --clear, -c    Clear the logs on the master node
  --sort, -s     Sort Puppet logs by date
  --evals, -e    Show Puppet evaltrace lines
  --mcagent, -m  Show Astute MCAgent calls debug
  --less, -l     Redirect data to the "less" pager

Using anywhere to view Fuel snapshot data:

fuel_logs.py fail_error_deploy_ha_vlan-2015_02_20__20_35_18.tar.gz

Using on the live Fuel Master node:

# View the current Astute log
fuel_logs.py -a
# View the current Puppet logs
fuel_logs.py -p

Using without -a and -p options assumes both options

fuel_logs.py -c Truncates Astute and Puppet logs. Respects -a and -p options.

It you are running and debugging many deployments on a single Fuel Master
node, you may want to truncate the logs from the previous deployments.
Using -l option is also recommended for interactive use.
"""

import argparse
from datetime import datetime
import os
import re
import sys
import tarfile


class IO(object):
    """
    This object does the input, the output and the main application logic
    """
    pipe = None
    args = None

    @classmethod
    def separator(cls):
        """
        Draw a separator line if both Puppet and Astute logs are enabled
        :return:
        """
        if cls.args.puppet and cls.args.astute:
            IO.output('#' * 79 + "\n")

    @classmethod
    def process_snapshots(cls):
        """
        Extract the logs from the snapshots and process the logs
        :return:
        """
        for snapshot in cls.args.snapshots:

            if not os.path.isfile(snapshot):
                continue

            with FuelSnapshot(snapshot) as fuel_snapshot:

                if cls.args.astute:
                    fuel_snapshot.parse_astute_log(
                        show_mcagent=cls.args.mcagent,
                        show_full=cls.args.full,

                    )

                cls.separator()

                if cls.args.puppet:
                    fuel_snapshot.parse_puppet_logs(
                        enable_sort=cls.args.sort,
                        show_evals=cls.args.evals,
                        show_full=cls.args.full,
                    )

    @classmethod
    def process_logs(cls):
        """
        Read the logs on the live Fuel Master node and process them
        :return:
        """
        fuel_logs = FuelLogs()
        if cls.args.astute:
            if cls.args.clear:
                fuel_logs.clear_astute_logs()
            else:
                fuel_logs.parse_astute_logs(
                    show_mcagent=cls.args.mcagent,
                    show_full=cls.args.full,
                )

        cls.separator()

        if cls.args.puppet:
            if cls.args.clear:
                fuel_logs.clear_puppet_logs()
            else:
                fuel_logs.parse_puppet_logs(
                    enable_sort=cls.args.sort,
                    show_evals=cls.args.evals,
                    show_full=cls.args.full,
                )

    @classmethod
    def main(cls):
        """
        The main application workflow
        :return:
        """
        cls.options()

        if cls.args.less:
            cls.open_pager()

        if len(cls.args.snapshots) == 0:
            cls.process_logs()
        else:
            cls.process_snapshots()

        if cls.args.less:
            cls.close_pager()

    @classmethod
    def open_pager(cls):
        """
        Open the pipe to the pager subprocess in order
        to display the output there
        :return:
        """
        cls.pipe = os.popen('less --chop-long-lines', 'w')

    @classmethod
    def close_pager(cls):
        """
        Close the pager process and finish the output
        :return:
        """
        cls.pipe.close()
        cls.pipe = None

    @classmethod
    def output(cls, line):
        """
        Output a single line of text to the console
        or to the pager
        :param line: the line to display
        :type line: str
        :return:
        """
        if not line.endswith('\n'):
            line += '\n'
        if not cls.pipe:
            sys.stdout.write(line)
        else:
            cls.pipe.write(line)

    @classmethod
    def options(cls):
        """
        Parse the input options and parameters
        :return: arguments structure
        """
        parser = argparse.ArgumentParser()
        parser.add_argument("--astute", "-a",
                            action="store_true",
                            default=False,
                            help='Parse Astute log')
        parser.add_argument("--puppet", "-p",
                            action="store_true",
                            default=False,
                            help='Parse Puppet logs')
        parser.add_argument("--clear", "-c",
                            action="store_true",
                            default=False,
                            help='Clear the logs on the Fuel Master node')
        parser.add_argument("--sort", "-s",
                            action="store_true",
                            default=False,
                            help='Sort Puppet logs by date')
        parser.add_argument("--evals", "-e",
                            action="store_true",
                            default=False,
                            help='Show Puppet evaltrace lines')
        parser.add_argument("--mcagent", "-m",
                            action="store_true",
                            default=False,
                            help='Show Astute MCAgent calls debug')
        parser.add_argument("--less", "-l",
                            action="store_true",
                            default=False,
                            help='Redirect data to the "less" pager')
        parser.add_argument("--full", "-f",
                            action="store_true",
                            default=False,
                            help='Full output without filters')
        parser.add_argument('snapshots',
                            metavar='SNAPSHOT',
                            type=str,
                            nargs='*',
                            default=[],
                            help='Take logs from these snapshots')
        cls.args = parser.parse_args()
        if not cls.args.puppet and not cls.args.astute:
            cls.args.puppet = True
            cls.args.astute = True
        return cls.args


class AbstractLog(object):
    """
    The abstract log object with common methods
    Attributes:
        content logging content list
        log     list() of collected logging records
    """

    def __init__(self):
        self.content = []
        self.log = []

    def clear(self):
        """
        Clear the parsed and raw log contents
        :return:
        """
        self.content = []
        self.log = []

    def catch_record(self, record, include_markers=None, exclude_markers=None):
        """
        Add a record to the parsed log if any of the include marker are
        found in the record and any of the exclude markers are not
        :param record The record from the input log
        :type record str
        :param include_markers Array of include markers
        :type include_markers list
        :param exclude_markers Array of exclude markers
        :type exclude_markers list
        """
        match = False
        if not include_markers:
            return
        for marker in include_markers:
            if marker in record:
                match = True
                break
        if exclude_markers:
            for marker in exclude_markers:
                if marker in record:
                    match = False
                    break
        if match:
            self.add_record(record)

    def each_record(self):
        """
        Abstract record iterator that interates
        through the content lines
        :return: iter
        """
        for record in self.content:
            yield record.decode()

    def parse(self, content):
        """
        Abstract parser that adds every line
        :param content: Input log content
        :type content: str
        :return:
        """
        self.content = content.splitlines()
        for record in self.each_record():
            self.add_record(record)

    def output(self):
        """
        Output the parsed log content
        :return:
        """
        for record in self.log:
            IO.output(record)

    @staticmethod
    def normalize_record(record):
        """
        Normalize newlines inside the text of the record
        :param record Record text
        :type record str
        :return Normalized record
        :rtype: str
        """
        record = record.replace('\n', ' ')
        record = record.replace('\\n', ' ')
        record = ' '.join(record.split())
        if not record.endswith('\n'):
            record += '\n'
        return record

    def add_record(self, record):
        """
        Add this record to the result log
        :param record Record text
        :type record str
        """
        record = self.normalize_record(record)
        self.log.append(record)


class AstuteLog(AbstractLog):
    """
    This class is responsible for Astute log parsing
    Attributes:
        show_mcagent    enable or disable MCAgent debug strings
    """

    def __init__(self):
        self.show_mcagent = False
        self.show_full = False
        super(AstuteLog, self).__init__()

    def parse(self, content):
        """
        Parse the string containing the log content
        :param content: the log file content
        :type content: str
        :return:
        """
        self.content = content.splitlines()
        for record in self.each_record():
            if self.show_full:
                self.add_record(record)
            else:
                self.rpc_call(record)
                self.rpc_cast(record)
                self.task_status(record)
                self.task_run(record)
                self.hook_run(record)
                if self.show_mcagent:
                    self.cmd_exec(record)
                    self.mc_agent_results(record)

    def each_record(self):
        """
        Iterates through the multi line records of the log file
        :return: iter
        """
        record = ''
        date_regexp = re.compile(r'^\d+-\d+-\S+\s')
        for bline in self.content:
            line = bline.decode()
            if re.match(date_regexp, line):
                yield record
                record = line
            else:
                record += line
        yield record

    def rpc_call(self, record):
        """
        Catch the lines with RPC calls from Nailgun to Astute
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['Processing RPC call']
        self.catch_record(record, include_markers)

    def rpc_cast(self, record):
        """
        Catch the lines with RPC casts from Astute to Nailgun
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['Casting message to Nailgun']
        exclude_markers = ['deploying', 'provisioning']
        self.catch_record(record, include_markers, exclude_markers)

    def task_status(self, record):
        """
        Catch the lines with modular task status reports
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['Task']
        exclude_markers = ['deploying']
        self.catch_record(record, include_markers, exclude_markers)

    def task_run(self, record):
        """
        Catch the lines with modular task run debug structures
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['run task']
        self.catch_record(record, include_markers)

    def hook_run(self, record):
        """
        Catch the lines with Astute pre/post deploy hooks debug structures
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['Run hook']
        self.catch_record(record, include_markers)

    def cmd_exec(self, record):
        """
        Catch the lines with cmd execution debug reports
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['cmd:', 'stdout:', 'stderr:']
        self.catch_record(record, include_markers)

    def mc_agent_results(self, record):
        """
        Catch the lines with MCAgent call traces
        :param record: log record
        :type record: str
        :return:
        """
        include_markers = ['MC agent']
        exclude_markers = ['puppetd']
        self.catch_record(record, include_markers, exclude_markers)


class PuppetLog(AbstractLog):
    """
    This class is responsible for Puppet log parsing
    Attributes:
        log_name    name for logger
        show_evals  show of Puppet evaltrace lines
        enable_sort sorting log lines by event time
    """

    def __init__(self):
        self.log_name = None
        self.show_evals = False
        self.enable_sort = False
        self.show_full = False
        super(PuppetLog, self).__init__()

    def parse(self, content):
        """
        Parse the sting with Puppet log content
        :param content: Puppet log
        :type content: str
        :return:
        """
        self.content = content.splitlines()
        for record in self.each_record():
            if self.show_full:
                self.add_record(record)
            else:
                self.err_line(record)
                self.catalog_start(record)
                self.catalog_end(record)
                self.catalog_modular(record)
                if self.show_evals:
                    self.resource_evaluation(record)

    @staticmethod
    def node_name(string):
        """
        Extract the node name from the Puppet log name
        It is used to mark log lines in the output
        :param string: log name
        :type string: str
        :return: node name
        :rtype: str
        """
        match = re.search(r'(node-\d+)', string)
        if match:
            return match.group(0)

    def output(self):
        """
        Output the collected log lines sorting
        them if enabled
        :return:
        """
        if self.enable_sort:
            self.sort_log()
        for record in self.log:
            log = record.get('log', None)
            time = record.get('time', None)
            line = record.get('line', None)
            if not (log and time and line):
                continue
            IO.output("%s %s %s" % (self.node_name(log),
                                    time.isoformat(), line))

    def sort_log(self):
        """
        Sort the collected log lines bu the event date and time
        :return:
        """
        self.log = sorted(self.log,
                          key=lambda record: record.get('time', None))

    def convert_record(self, line):
        """
        Split the log line to date, log name and event string
        :param line: log line
        :type line: str
        :return: log record
        :rtype: dict
        """
        fields = line.split()
        time = fields[0]
        line = ' '.join(fields[1:])
        time = time[0:26]
        try:
            time = datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            return
        record = {
            'time': time,
            'line': self.normalize_record(line),
            'log': self.log_name,
        }
        return record

    def add_record(self, record):
        """
        Add this record to the result log
        :param record: Record text
        :type record: str
        :return:
        """
        record = self.convert_record(record)
        if record:
            self.log.append(record)

    def err_line(self, record):
        """
        Catch lines that are marked as 'err:'
        :param record: log line
        :type record: str
        :return:
        """
        include_markers = ['err:']
        self.catch_record(record, include_markers)

    def catalog_end(self, record):
        """
        Catch the end of the catalog run
        :param record: log line
        :type record: str
        :return:
        """
        include_markers = ['Finished catalog run']
        self.catch_record(record, include_markers)

    def catalog_start(self, record):
        """
        Catch the end of the catalog compilation and start of the catalog run
        :param record: log line
        :type record: str
        :return:
        """
        include_markers = ['Compiled catalog for']
        self.catch_record(record, include_markers)

    def catalog_modular(self, record):
        """
        Catch the MODULAR marker of the modular tasks
        :param record: log line
        :type record: str
        :return:
        """
        include_markers = ['MODULAR']
        self.catch_record(record, include_markers)

    def resource_evaluation(self, record):
        """
        Catch the evaltrace lines marking every resource
        processing start and end
        :param record: log line
        :type record: str
        :return:
        """
        include_markers = [
            'Starting to evaluate the resource',
            'Evaluated in',
        ]
        self.catch_record(record, include_markers)


class FuelSnapshot(object):
    """
    This class extracts data from the Fuel log snapshot
    """

    def __init__(self, snapshot):
        if not os.path.isfile(snapshot):
            raise RuntimeError('File "%s" is not found!' % snapshot)
        self.snapshot = snapshot

    def __enter__(self):
        """
        Enter the context manager
        """
        self.open_fuel_snapshot(self.snapshot)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context manager
        """
        self.close_fuel_snapshot()

    def open_fuel_snapshot(self, snapshot):
        """
        Open the Fuel log snapshot file
        :param snapshot: path to file
        :type snapshot: str
        :return:
        """
        self.snapshot = tarfile.open(snapshot)

    def close_fuel_snapshot(self):
        """
        Close the Fuel log snapshot file
        :return:
        """
        if self.snapshot:
            self.snapshot.close()

    def astute_logs(self):
        """
        Find the Astute logs in the snapshot archive
        :return: iter
        """
        for log in self.snapshot.getmembers():
            if not log.isfile():
                continue
            if log.name.endswith('/astute.log'):
                yield log

    def puppet_logs(self):
        """
        Find the Puppet logs inside the snapshot archive
        :return: iter
        """
        for log in self.snapshot.getmembers():
            if not log.isfile():
                continue
            if log.name.endswith('/puppet-apply.log'):
                yield log

    def parse_log(self, log_file, parser):
        """
        Extract from the snapshot and parse the log
        using a given parser object
        :param log_file Path to the log file in the archive
        :type log_file str
        :param parser Parser object
        :type parser PuppetLog, AstuteLog
        """
        log = self.snapshot.extractfile(log_file)
        content = log.read()
        parser.parse(content)

    def parse_astute_log(self,
                         show_mcagent=False,
                         show_full=False):
        """
        Parse the Astute log from the archive
        :param show_mcagent: show or hide MCAgent debug
        :type show_mcagent: bool
        :return:
        """
        astute_logs = AstuteLog()
        astute_logs.show_mcagent = show_mcagent
        astute_logs.show_full = show_full
        for astute_log in self.astute_logs():
            self.parse_log(astute_log, astute_logs)
        astute_logs.output()
        astute_logs.clear()

    def parse_puppet_logs(self,
                          enable_sort=False,
                          show_evals=False,
                          show_full=False):
        """
        Parse the Puppet logs found inside the archive
        :param enable_sort: enable sorting of logs by date
        :type enable_sort: bool
        :param show_evals: show evaltrace lines in the logs
        :type show_evals: bool
        :return:
        """
        puppet_logs = PuppetLog()
        puppet_logs.show_evals = show_evals
        puppet_logs.enable_sort = enable_sort
        puppet_logs.show_full = show_full
        for puppet_log in self.puppet_logs():
            puppet_logs.log_name = puppet_log.name
            self.parse_log(puppet_log, puppet_logs)
        puppet_logs.output()
        puppet_logs.clear()


class FuelLogs(object):
    """
    This class works with Astute and Puppet logs on the
    live Fuel master system
    """

    def __init__(self, log_dir='/var/log'):
        self.log_dir = log_dir

    def find_logs(self, name):
        """
        Find log files with the given name
        :return: iter
        """
        for root, files, files in os.walk(self.log_dir):
            for log_file in files:
                if log_file == name:
                    path = os.path.join(root, log_file)
                    IO.output('Processing: %s' % path)
                    yield path

    def puppet_logs(self):
        """
        Find the Puppet logs in the log directory
        :return: iter
        """
        return self.find_logs('puppet-apply.log')

    def astute_logs(self):
        """
        Find the Astute logs in the log directory
        :return: iter
        """
        return self.find_logs('astute.log')

    @staticmethod
    def truncate_log(log_file):
        """
        Truncate the log in the log dir. It's better to
        truncate the logs between several deployment runs
        to drop all the previous lines.
        :param log_file: path to log file
        :type log_file: str
        :return:
        """
        if not os.path.isfile(log_file):
            return
        IO.output('Clear log: %s' % log_file)
        with open(log_file, 'w') as log:
            log.truncate()

    @staticmethod
    def parse_log(log_file, parser):
        """
        Read the log file and parse it using the given parser object
        :param log_file Opened file object
        :type log_file FileIO
        :param parser Parser object
        :type parser PuppetLog, AstuteLog
        """
        content = log_file.read()
        parser.parse(content)

    def parse_astute_logs(self,
                          show_mcagent=False,
                          show_full=False):
        """
        Parse Astute log on the Fuel Master system
        :param show_mcagent: show MCAgent call debug
        :type show_mcagent: bool
        :return:
        """
        astute_logs = AstuteLog()
        astute_logs.show_mcagent = show_mcagent
        astute_logs.show_full = show_full
        for astute_log in self.astute_logs():
            with open(astute_log, 'r') as log:
                self.parse_log(log, astute_logs)
        astute_logs.output()
        astute_logs.clear()

    def parse_puppet_logs(self,
                          enable_sort=False,
                          show_evals=False,
                          show_full=False):
        """
        Parse Puppet logs on the Fuel Master system
        :param enable_sort: sort log files by date
        :type enable_sort: bool
        :param show_evals: show evaltrace lines
        :type show_evals: bool
        :return:
        """
        puppet_logs = PuppetLog()
        puppet_logs.show_evals = show_evals
        puppet_logs.enable_sort = enable_sort
        puppet_logs.show_full = show_full
        for puppet_log in self.puppet_logs():
            with open(puppet_log, 'r') as log:
                puppet_logs.log_name = puppet_log
                self.parse_log(log, puppet_logs)
        puppet_logs.output()
        puppet_logs.clear()

    def clear_logs(self, iterator):
        """
        Clear all the logs found by the iterator_function
        :param iterator An iterator with a list of files
        :type iterator iter
        """
        for log in iterator:
            self.truncate_log(log)

    def clear_astute_logs(self):
        """
        Clear all Astute logs found in the log dir
        :return:
        """
        self.clear_logs(self.astute_logs())

    def clear_puppet_logs(self):
        """
        Clear all Puppet logs found in the log dir
        :return:
        """
        self.clear_logs(self.puppet_logs())

##############################################################################

if __name__ == '__main__':
    IO.main()
