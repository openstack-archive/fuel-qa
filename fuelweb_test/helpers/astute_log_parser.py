#!/usr/bin/python
#
#    Copyright 2016 Mirantis, Inc.
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
#
# This script can be used to parse the puppet tasks and their summary results
# from an astute.log which can provide insight into the idempotency of the
# tasks as well what resources are touched during the task runs.
#
# This file assumes that the following changes are included in astute:
#  * https://review.openstack.org/#/c/273740/
#  * https://review.openstack.org/#/c/273737/
#

import json
import re
import sys


class NodePuppetStatus(object):
    """ This class is used to collect puppet status data from the astute.log

    The class is assigned to a specific node id to hold PuppetTaskResponse and
    PuppetTaskResult objects that were parsed in chronological order from the
    astute.log. Once the complete list has been collected, you can use the
    print_items function to print a comma separated line with in the following
    format:

    Runtime, Node ID, Modular Task, Total Time, Change Count, Failure Count,
    Changed Resources, Failed Resources
    """
    def __init__(self, node_id):
        """
        :param node_id: ID of the fuel node associated with Puppet task items
        """
        self.node_id = node_id
        self.items = []

    def add_item(self, item):
        """ Add an item to the list of task objects for this node

        :param item: Either a PuppetTaskResponse or PuppetTaskResult for a node
        """
        self.items.append(item)

    def get_node_id(self):
        """ Get the Node ID associated with this object

        :return: integer
        """
        return self.node_id

    def print_items(self):
        """ Iterate through the task items and print a CSV line for for each
        task and the last result for the task

        This function will loop through the tasks and assumes that they are in
        chronological order based on the parsing of the astute.log. For each
        node Puppet must run serially so we should have an ordered list of
        PuppetTaskResponse followed by a number of PuppetTaskResult objects.
        We will print a single CSV line using the PuppetTaskResponse and the
        last PuppetTaskResult object we find prior to the next
        PuppetTaskResponse
        """
        previous_task = None
        last_results = None
        """ Loop through all the items and print a task & last result as a
        single csv line """
        for item in self.items:
            if item.__class__.__name__ == 'PuppetTaskResponse':
                self.print_line(previous_task, last_results)
                previous_task = item
            elif item.__class__.__name__ == 'PuppetTaskResult':
                last_results = item
        # don't forget to print the last set we parsed
        self.print_line(previous_task, last_results)

    def print_line(self, task=None, results=None):
        """ Prints a CSV line with the task and resaults provided

        This function prints a single CSV line using the task and result
        provided in the following format

        Runtime, Node ID, Modular Task, Total Time, Change Count, Failure
        Count, Changed Resources, Failed Resources

        :param task: a PuppetTaskResponse to use for the task information
        :param results: a PuppetTaskResult to use for the task idempotency
        information
        """
        if not task or not results:
            return
        runtime = 0

        if task:
            sender = task.get_sender()
            task_name = task.get_modular_task()
            runtime = task.get_lastrun()
        elif results:
            sender = results.get_sender()
            task_name = 'N/A'
            runtime = results.get_lastrun()
        else:
            sender = 'N/A'
            task_name = 'N/A'

        if results:
            changes = results.get_changed_resources()
            change_count = results.changes
            failures = results.get_failed_resources()
            fail_count = results.failures
            total_time = results.get_total_time()
        else:
            changes = 'N/A'
            change_count = 0
            failures = 'N/A'
            fail_count = 0
            total_time = 0

        print("{runtime},{node},{task},{total_time},{change_count},{fail_count}\
                ,{changes},{failures}".format(
            runtime=runtime, node=sender, task=task_name,
            total_time=total_time, change_count=change_count,
            fail_count=fail_count, changes=changes, failures=failures))


class PuppetTaskResponse:
    """ This class is used to hold and parse the json information provided by
    the runonce mcollective puppetd action
    """
    def __init__(self, json_data=None):
        """ This function initializes the object and will parse the provided
        json_data string

        :param json_data: A json representation of the hash data from the
        runonce mcollective puppetd action
        """

        """ json_data should be of format:
{
  "data": {
    "enabled": 1,
    "idling": 0,
    "lastrun": 1454099779,
    "output": "Called /usr/sbin/daemonize -a -l /tmp/puppetd.lock
-p /tmp/puppetd.lock -c / /usr/bin/puppet apply
/etc/puppet/modules/osnailyfacter/modular/hiera/override_configuration.pp
--modulepath=/etc/puppet/modules --logdest syslog --trace --report --debug
--evaltrace --logdest /var/log/puppet.log, Currently stopped; last completed
run 1 seconds ago",
    "running": 0,
    "runtime": 1,
    "status": "stopped",
    "stopped": 1
  },
  "sender": "1",
  "statuscode": 0,
  "statusmsg": "OK"
}
        """
        self.json_data = json_data
        self.sender = None
        self.last_run = None
        self.modular_task = None
        self.parse()

    def get_lastrun(self):
        """ get the last run timestamp

        :return: integer
        """
        return self.last_run

    def get_modular_task(self):
        """ Returns the modular task puppet path/filename

        :return: string
        """
        return self.modular_task

    def get_sender(self):
        """ Returns the node id associated with the response information

        :return: integer
        """
        return self.sender

    def parse(self):
        """ Parse out the information from the json_data string for this object
        """
        if not self.json_data or 'data' not in self.json_data:
            return
        self.last_run = self.json_data['data']['lastrun']
        self.sender = self.json_data['sender']
        task_regex = re.compile(r"modular/.*\.pp")
        match = task_regex.search(self.json_data['data']['output'])
        if match:
            self.modular_task = match.group(0)


class PuppetTaskResult:
    """ This class is used to hold/parse json information provided by the
    last_run_summary mcollective puppetd action
    """
    def __init__(self, json_data=None):
        """ This function initializes the object and will parse the provided
        json_data string

        :param json_data: A json representation of the hash data from the
        last_run_summary mcollective puppetd action
        """
        """ json_data should be of format:
{
  "data": {
    "changes": {
      "total": 0
    },
    "enabled": 1,
    "events": {
      "failure": 0,
      "success": 0,
      "total": 0
    },
    "idling": 0,
    "lastrun": 1454099775,
    "output": "Currently running; last completed run 3 seconds ago",
    "resources": {
      "changed": 0,
      "changed_resources": "",
      "failed": 0,
      "failed_resources": "",
      "failed_to_restart": 0,
      "out_of_sync": 0,
      "restarted": 0,
      "scheduled": 0,
      "skipped": 0,
      "total": 13
    },
    "running": 1,
    "runtime": 3,
    "status": "running",
    "stopped": 0,
    "time": {
      "config_retrieval": 0.323771903,
      "file": 0.010140943,
      "filebucket": 0.000384625,
      "hiera_config": 0.029874523,
      "last_run": 1454099775,
      "schedule": 0.001356223,
      "total": 0.36552821700000004
    },
    "version": {
      "config": 1454099774,
      "puppet": "3.8.3"
    }
  },
  "sender": "1",
  "statuscode": 0,
  "statusmsg": "OK"
}
        """
        self.json_data = json_data
        self.status = None
        self.sender = None
        self.changes = None
        self.failures = None
        self.total_time = None
        self.last_run = None
        self.changed_resources = []
        self.failed_resources = []
        self.parse()

    def get_changed_resources(self):
        """ Returns space separated list of changed Puppet resources

        :return: string
        """
        return ' '.join(self.changed_resources)

    def get_failed_resources(self):
        """ Returns space separated list of failed Puppet resources

        :return: string
        """
        return ' '.join(self.failed_resources)

    def get_lastrun(self):
        """ get the last run timestamp

        :return: integer
        """
        return self.last_run

    def get_sender(self):
        """ Returns the node id associated with the response information

        :return: integer
        """
        return self.sender

    def get_status(self):
        """ Returns the status string for the response

        :return: string
        """
        return self.status

    def get_total_time(self):
        """ Returns the total time for the last puppet run

        :return: float
        """
        return self.total_time

    def parse(self):
        """ Parses out the information from the provided json data string for
        this object
        """
        if not self.json_data or 'data' not in self.json_data:
            return
        self.sender = self.json_data['sender']
        self.last_run = self.json_data['data']['lastrun']
        self.status = self.json_data['data']['status']

        if 'total' in self.json_data['data']['time']:
            self.total_time = self.json_data['data']['time']['total']

        resources = self.json_data['data']['resources']
        self.changes = resources['changed']
        self.failures = resources['failed']
        if self.changes > 0 and 'changed_resources' in resources:
            self.changed_resources = resources['changed_resources'].split(',')
        if self.failures > 0 and 'failed_resources' in resources:
            self.failed_resources = resources['failed_resources'].split(',')


class AstuteLogEntry:
    """ This class is used to collect and parse the astute.log entries
    """
    def __init__(self):
        """ initialize the log entry
        """
        self.lines = []
        self.content_log = None
        self.content_hash = None
        self.content_json = None
        self.json_data = None

    def add_line(self, line):
        """ This function is used to append a log line to the log entry

        :param line: log line string
        """
        self.lines.append(line)
        # reset parsed items if we add lines
        self.content_log = None
        self.content_hash = None
        self.content_json = None
        self.json_data = None

    def parse(self):
        """ Parse the astute log entry into the log content and attempt to
        parse out hash/json data

        This function will search for a Ruby hash or Json blob from the log
        entry and attempt to convert it into a json object. The json_data
        object can then be used directly.
        """
        # we've already parsed
        if self.content_log:
            return

        # strip out new lines
        self.content_log = "".join(self.lines)
        # find the the hash
        hash_start = self.content_log.find('{')
        hash_end = self.content_log.rfind('}') + 1
        if hash_start > 0:
            self.content_hash = self.content_log[hash_start:hash_end]
            try:
                # Try parsing the hash content to see if it's actually json
                self.json_data = json.loads(self.content_hash)
                self.content_json = self.content_hash
            except Exception:
                # if it fails try converting it to dict assuming it's a hash
                self.convert_ruby_hash_to_dict()

    def get_log(self):
        """ Return the log content as a single string
        :return: string
        """
        return self.content_log.strip()

    def get_json(self):
        """ Return the json data from the log entry
        :return: json object
        """
        if not self.json_data and self.content_json:
            self.json_data = json.loads(self.content_json)
        return self.json_data

    def convert_ruby_hash_to_dict(self):
        """ Attempt to convert the hash data parsed from the log into a json
        object assuming it's a Ruby hash

        This function uses string replace to convert the Ruby hash information
        from the log entry into a json object that can be consumed by python.
        If the conversation process fails, we just assume it wasn't a valid
        hash and remove the json and hash content from this object leaving just
        the log content
        """
        self.content_json = self.content_hash
        mapping = [
            (':', '"'),          # symbol to string
            ('=>', '": '),       # arrow and symbol to string end and colon
            ('"":', '":'),       # fix if wasn't a symbol -^
            (': nil', ': null')  # nil to null
        ]
        for k, v in mapping:
            self.content_json = self.content_json.replace(k, v)
        try:
            # try loading the data
            self.json_data = json.loads(self.content_json)
        except Exception:
            # well it failed, so never mind then
            self.content_hash = None
            self.content_json = None


class AstutePuppetTaskParser:
    """ This class can be used to parse out the puppet responses from an
    astute.log
    """
    def __init__(self):
        """ Initialize our parser and setup our regex objects
        """
        self.linestart_re = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        self.runonce_re = re.compile(r"method 'runonce'")
        self.summary_re = re.compile(r"method 'last_run_summary'")
        self.tasks = {}

    def add_entry(self, entry):
        """ This function takes an AstuteLogEntry and adds it to our tasks list

        This function takes an AstuteLogEntry, converts it to a
        PuppetTaskResponse or PuppetTaskResult object and then adds it to the
        tasks list using the the node id as a key.

        :param entry: AstuteLogEntry
        """
        if not entry:
            return
        entry.parse()
        # figure out if we know how to handle the entry and deal with it
        if self.runonce_re.search(entry.get_log()):
            self.add_task(PuppetTaskResponse(entry.get_json()))
        elif self.summary_re.search(entry.get_log()):
            self.add_result(PuppetTaskResult(entry.get_json()))

    def add_result(self, result):
        """ Add a PuppetTaskResult to the tasks list based using the Node ID
        from the result data

        This function adds a PuppetTaskResult object to the task list if the
        result is a 'stopped' result. This function will add the object to the
        task list for the Node ID (or sender) from the response which allows us
        to track the results based on a node.

        :param result: PuppetTaskResult
        """
        # we only care about results when status is stopped
        if result.get_status() != 'stopped':
            return
        node_id = result.sender
        if not node_id:
            # Missing sender id... (result)
            return
        if node_id not in self.tasks:
            self.tasks[node_id] = NodePuppetStatus(node_id)
        self.tasks[node_id].add_item(result)

    def add_task(self, task):
        """ Add a PuppetTaskResponse to the tasks list based using the Node ID
        from the result data

        This function adds a PuppetTaskResponse object to the task list. This
        function will add the object to the task list for the Node ID
        (or sender) from the response which allows us to track the tasks based
        on a node.

        :param task: PuppetTaskResult
        """
        node_id = task.sender
        if not node_id:
            # Missing sender id... (task)
            return
        if node_id not in self.tasks:
            self.tasks[node_id] = NodePuppetStatus(node_id)
        self.tasks[node_id].add_item(task)

    def parse_log(self, file_name):
        """ This function loops through a file and parses out the entries
        :param file_name: string
        :return:
        """
        log_file = open(file_name, 'r')
        entry = None
        for line in log_file:
            # find the first line of an entry, starts with the date
            if self.linestart_re.match(line):
                self.add_entry(entry)
                # create an entry to add the lines to
                entry = AstuteLogEntry()
            # still working on the last entry, so add the line to the entry
            if entry:
                entry.add_line(line.strip())

    def print_tasks(self):
        """ Print a CSV of the tasks and their puppet results from the
        astute.log
        """
        header = "Runtime, Node ID, Modular Task, Total Time, Change Count, " \
                 "Failure Count, Changed Resources, Failed Resources"
        print(header)
        for item_id in sorted(self.tasks):
            self.tasks[item_id].print_items()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: {} <log file>'.format(sys.argv[0]))
        sys.exit(1)

    parser = AstutePuppetTaskParser()
    parser.parse_log(sys.argv[1])
    parser.print_tasks()
