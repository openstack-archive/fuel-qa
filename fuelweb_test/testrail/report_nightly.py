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

import datetime
from xml.dom import minidom
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject


LOG = logger


def main():

    # STEP #1
    # Initialize TestRail project client
    LOG.info('Initializing TestRail project client...')
    client = TestRailProject(url=TestRailSettings.url,
                             user=TestRailSettings.user,
                             password=TestRailSettings.password,
                             project=TestRailSettings.project)
    LOG.info('TestRail project client has been initialized.')

    # tests_suite = client.get_suite_by_name('[10.0][Fuel] UI testing')
    tests_suite = client.get_suite_by_name(TestRailSettings.tests_suite)
    tests_suite_name = tests_suite['name']
    LOG.info('Tests suite is "{0}".'.format(tests_suite_name))

    # STEP #2
    # Parse the test results
    xml_parse = minidom.parse('nightly_report_example.xml')
    test_suites = xml_parse.getElementsByTagName('testsuite')
    delimiter = '/'
    test_results = list()

    LOG.info('Parsing the test results...')
    for test_suite in test_suites[1:]:
        group_name = test_suite.attributes['name'].value
        test_cases = test_suite.getElementsByTagName('testcase')
        for test_case in test_cases:
            full_name = group_name + delimiter + test_case.attributes['name'].value
            test_results.append([full_name, test_case.attributes['time'].value, test_case.attributes['status'].value])
    LOG.info('The test results have been parsed.')

    # STEP #3
    # Create new test plan
    name = '{0} #{1}'
    now = datetime.datetime.now()

    milestone = client.get_milestone_by_name('10.0')
    test_plan_name = name.format(tests_suite_name, now.strftime("%m/%d/%y %H:%M"))
    LOG.info('Test plan name is "{0}".'.format(test_plan_name))

    LOG.info('Creating new test plan...')
    test_plan = client.add_plan(test_plan_name,
                                description=None,
                                milestone_id=milestone['id'],
                                entries=[])
    LOG.info('The test plan has been created.')

    # # Need to add entries, that has only "Automated" type in Test Rail
    # # Examples are below
    # plan_entries = list()
    # plan_entries.append(
    #     client.test_run_struct(name='Deployment task execution history',
    #                            suite_id=tests_suite['id'],
    #                            milestone_id=milestone['id'],
    #                            description='https://mirantis.jira.com/browse/PROD-6016',
    #                            config_ids=None,
    #                            include_all=False,
    #                            case_ids=tests_ids)
    # )
    #
    # entry = client.add_plan_entry(name='Test_name_1',
    #                               plan_id=test_plan['id'],
    #                               suite_id=tests_suite['id'],
    #                               config_ids=None,
    #                               runs=plan_entries)

    # STEP #4
    # Upload the test results to TestRail for the specified test run
    LOG.info('Uploading the test results to TestRail...')

    # Need to add results mapping from "test_results" to "test_plan"

    LOG.info('The results of Tempest tests have been uploaded.')

if __name__ == "__main__":
    main()
