#!/usr/bin/env python
#
#    Copyright 2015 Mirantis, Inc.
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

from __future__ import unicode_literals

import optparse
from xml.etree import ElementTree

# pylint: disable=import-error
from six.moves import urllib
# pylint: enable=import-error

from fuelweb_test.testrail import report
from fuelweb_test.testrail.settings import JENKINS
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject


LOG = logger


def parse_xml_report(path_to_report):
    """This function parses the Tempest XML report and returns the list with
    TestResult objects. Each TestResult object corresponds to one of the tests
    and contains all the result information for the respective test.
    """

    tree = ElementTree.parse(path_to_report)
    test_results = []
    for elem in tree.findall('testcase'):
        status = 'passed'
        description = None
        child_elem = elem.getchildren()
        if child_elem:
            status = child_elem[0].tag
            description = child_elem[0].text

        test_result = report.TestResult(name=elem.get('name'),
                                        group=elem.get('classname'),
                                        status='failed'
                                        if status == 'failure' else status,
                                        description=description,
                                        duration=1)
        test_results.append(test_result)

    return test_results


def mark_all_tests_as_blocked(client, tests_suite):
    """This function marks all Tempest tests as blocked and returns the list
    with TestResult objects. Each TestResult object corresponds to one of
    the tests and contains the information that the test is blocked.
    """

    test_results = []
    for case in client.get_cases(tests_suite['id']):
        test_result = report.TestResult(name=case['title'],
                                        group=case['custom_test_group'],
                                        status='blocked',
                                        description=None,
                                        duration=1)
        test_results.append(test_result)

    return test_results


def mark_all_tests_as_in_progress(client, tests_suite):
    """This function marks all Tempest tests as "in progress" and returns
    the list with TestResult objects. Each TestResult object corresponds
    to one of the tests and contains the information that the test is
    "in progress" status.
    """

    test_results = []
    for case in client.get_cases(tests_suite['id']):
        test_result = report.TestResult(name=case['title'],
                                        group=case['custom_test_group'],
                                        status='in_progress',
                                        description=None,
                                        duration=1)
        test_results.append(test_result)

    return test_results


def find_run_by_name_and_config_in_test_plan(test_plan, run_name, config):
    """This function finds the test run by its name and the specified
    configuration (for example, Centos 6.5) in the specified test plan.
    """

    for entry in test_plan['entries']:
        for run in entry['runs']:
            if run['name'] == run_name and run['config'] == config:
                return run


def find_run_by_config_in_test_plan_entry(test_plan_entry, config):
    """This function finds the test run by the specified configuration
    (for example, Ubuntu 14.04) in the specified test plan entry.
    """

    for run in test_plan_entry['runs']:
        if run['config'] == config:
            return run


def upload_test_results(client, test_run, suite_id, test_results):
    """ This function allows to upload large number of test results
        with the minimum number of APi requests to TestRail.
    """

    test_cases = client.get_cases(suite_id)
    results = []
    statuses = {}

    for test_result in test_results:
        if test_result.status in statuses:
            status_id = statuses[test_result.status]
        else:
            status_id = client.get_status(test_result.status)['id']
            statuses[test_result.status] = status_id

        if 'setUpClass' in test_result.name:
            i = test_result.name.find('tempest')
            group = test_result.name[i:-1]
            for test in test_cases:
                if group in test.get("custom_test_group"):
                    results.append({"case_id": test['id'],
                                    "status_id": status_id})
        else:
            for test in test_cases:
                if test_result.name in test.get("title"):
                    results.append({"case_id": test['id'],
                                    "status_id": status_id})

    client.add_results_for_tempest_cases(test_run['id'], results)


def main():
    parser = optparse.OptionParser(
        description='Publish the results of Tempest tests in TestRail')
    parser.add_option('-r', '--run-name', dest='run_name',
                      help='The name of a test run. '
                           'The name should describe the configuration '
                           'of the environment where Tempest tests were run')
    parser.add_option('-i', '--iso', dest='iso_number', help='ISO number')
    parser.add_option('-p', '--path-to-report', dest='path',
                      help='The path to the Tempest XML report')
    parser.add_option('-c', '--conf', dest='config', default='Ubuntu 14.04',
                      help='The name of one of the configurations')
    parser.add_option('-m', '--multithreading', dest='threads_count',
                      default=100, help='The count of threads '
                                        'for uploading the test results')
    parser.add_option('-b', '--block-all-tests',
                      dest='all_tests_blocked', action='store_true',
                      help='Mark all Tempest tests as "blocked"')
    parser.add_option('-t', '--tests-in-progress',
                      dest='tests_in_progress', action='store_true',
                      help='Mark all Tempest tests as "in progress"')
    parser.add_option('--prefix',
                      dest='prefix', action='store_true', default='',
                      help='Add some prefix to test run')

    (options, _) = parser.parse_args()

    if options.run_name is None:
        raise optparse.OptionValueError('No run name was specified!')
    if options.iso_number is None:
        raise optparse.OptionValueError('No ISO number was specified!')
    if (options.path is None and
            not options.all_tests_blocked and not options.tests_in_progress):
        raise optparse.OptionValueError('No path to the Tempest '
                                        'XML report was specified!')

    # STEP #1
    # Initialize TestRail project client
    LOG.info('Initializing TestRail project client...')
    client = TestRailProject(url=TestRailSettings.url,
                             user=TestRailSettings.user,
                             password=TestRailSettings.password,
                             project=TestRailSettings.project)
    LOG.info('TestRail project client has been initialized.')

    tests_suite = client.get_suite_by_name(TestRailSettings.tests_suite)
    LOG.info('Tests suite is "{0}".'.format(tests_suite['name']))

    # STEP #2
    # Parse the test results
    if options.all_tests_blocked:
        test_results = mark_all_tests_as_blocked(client, tests_suite)
    elif options.tests_in_progress:
        test_results = mark_all_tests_as_in_progress(client, tests_suite)
    else:
        LOG.info('Parsing the test results...')
        test_results = parse_xml_report(options.path)
        LOG.info('The test results have been parsed.')

    # STEP #3
    # Create new test plan (or find existing)
    name = '{0} {1}iso #{2}'
    if options.prefix is not '':
        options.prefix += ' '

    milestone = client.get_milestone_by_name(TestRailSettings.milestone)
    test_plan_name = name.format(milestone['name'], options.prefix,
                                 options.iso_number)
    LOG.info('Test plan name is "{0}".'.format(test_plan_name))

    LOG.info('Trying to find test plan "{0}"...'.format(test_plan_name))
    test_plan = client.get_plan_by_name(test_plan_name)
    if not test_plan:
        LOG.info('The test plan not found. Creating one...')
        url = '/job/{0}.all/{1}'.format(milestone['name'], options.iso_number)
        description = urllib.parse.urljoin(JENKINS['url'], url)
        test_plan = client.add_plan(test_plan_name,
                                    description=description,
                                    milestone_id=milestone['id'],
                                    entries=[])
        LOG.info('The test plan has been created.')
    else:
        LOG.info('The test plan found.')

    # Get ID of each OS from list "TestRailSettings.operation_systems"
    config_ids = []
    for os_name in TestRailSettings.operation_systems:
        for conf in client.get_config_by_name('Operation System')['configs']:
            if conf['name'] == os_name:
                config_ids.append(conf['id'])
                break

    # Define test runs for CentOS and Ubuntu
    run_name = 'Tempest - ' + options.run_name
    runs = []
    for conf_id in config_ids:
        run = client.test_run_struct(name=run_name,
                                     suite_id=tests_suite['id'],
                                     milestone_id=milestone['id'],
                                     description='Tempest results',
                                     config_ids=[conf_id])
        runs.append(run)

    # Create a test plan entry with the test runs
    run = find_run_by_name_and_config_in_test_plan(test_plan,
                                                   run_name, options.config)
    if not run:
        LOG.info('Adding a test plan entry with test run '
                 '"{0} ({1})" ...'.format(run_name, options.config))
        entry = client.add_plan_entry(plan_id=test_plan['id'],
                                      suite_id=tests_suite['id'],
                                      config_ids=config_ids,
                                      runs=runs,
                                      name=run_name)
        LOG.info('The test plan entry has been added.')
        run = find_run_by_config_in_test_plan_entry(entry, options.config)

    # STEP #4
    # Upload the test results to TestRail for the specified test run
    LOG.info('Uploading the test results to TestRail...')

    upload_test_results(client, run, tests_suite['id'], test_results)

    LOG.info('The results of Tempest tests have been uploaded.')
    LOG.info('Report URL: {0}'.format(test_plan['url']))

if __name__ == "__main__":
    main()
