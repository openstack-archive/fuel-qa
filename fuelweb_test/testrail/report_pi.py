#!/usr/bin/env python
#
# Copyright 2015 Mirantis, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
import urllib2

from logging import DEBUG
from optparse import OptionParser

from builds import Build
from settings import JENKINS
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject
from report import get_tests_results
from report import publish_results


def find_run_by_name(test_plan, run_name):
    """This function finds the test run by its name
    """
    for entry in test_plan['entries']:
        for run in entry['runs']:
            if run['name'] == run_name:
                return run


def get_job_info(url):
    job_url = "/".join([url, 'api/json'])
    logger.debug("Request job info from %s", job_url)
    return json.load(urllib2.urlopen(job_url))


def main():
    parser = OptionParser(
        description="Publish results of system tests from Jenkins build to "
                    "TestRail. See settings.py for configuration."
    )
    parser.add_option('-j', '--job-name', dest='job_name', default=None,
                      help='Jenkins swarm runner job name')
    parser.add_option('-N', '--build-number', dest='build_number',
                      default='latest',
                      help='Jenkins swarm runner build number')
    parser.add_option("-l", "--live", dest="live_report", action="store_true",
                      help="Get tests results from running swarm")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")

    (options, args) = parser.parse_args()

    if options.verbose:
        logger.setLevel(DEBUG)

    if options.live_report and options.build_number == 'latest':
        build_number = 'latest_started'
    else:
        build_number = options.build_number

    # STEP #1
    # Initialize TestRail Project and define configuration
    logger.info('Initializing TestRail Project configuration...')
    project = TestRailProject(url=TestRailSettings.url,
                              user=TestRailSettings.user,
                              password=TestRailSettings.password,
                              project=TestRailSettings.project)
    logger.info('Initializing TestRail Project configuration... done')

    operation_systems = [{'name': config['name'], 'id': config['id'],
                          'distro': config['name'].split()[0].lower()}
                         for config in project.get_config_by_name(
                             'Operation System')['configs']]
    os_mile = {'6.1': ['Centos 6.5', 'Ubuntu 14.04'],
               '6.0.1': ['Centos 6.5', 'Ubuntu 12.04']}

    tests_results = {}

    # STEP #2
    # Get tests results from Jenkins
    runner_build = Build(options.job_name, build_number)
    runs = runner_build.build_data['runs']

    # Analyze each test individually
    for run_one in runs:
        if '5.1' in run_one['url']:
            continue  # Release 5.1 to skip
        tests_result = get_job_info(run_one['url'])
        if not tests_result['description']:
            continue  # Not completed results to skip
        if 'skipping' in tests_result['description']:
            continue  # Not performed tests to skip
        tests_job = {'result': tests_result['result'],
                     'name': (options.job_name + '/' +
                              tests_result['url'].split('/')[-3]),
                     'number': int(tests_result['url'].split('/')[-2]),
                     'mile': (tests_result['description'].
                              split()[0].split('-')[0]),
                     'iso': (int(tests_result['description'].
                             split()[0].split('-')[1]))}
        if tests_job['mile'] not in tests_results:
            tests_results[tests_job['mile']] = {}
        test_mile = tests_results[tests_job['mile']]
        if tests_job['iso'] not in test_mile:
            test_mile[tests_job['iso']] = {}
        test_iso = test_mile[tests_job['iso']]
        for os in operation_systems:
            if os['distro'] in tests_job['name'].lower() and\
                    os['name'] in os_mile[tests_job['mile']]:
                if os['id'] not in test_iso:
                    (test_iso[os['id']]) = []
                test_os_id = test_iso[os['id']]
                test_os_id.extend(get_tests_results(tests_job))

    # STEP #3
    # Create new TestPlan in TestRail (or get existing) and add TestRuns
    for mile in tests_results:
        mile_tests_suite = '{0}{1}'.format(TestRailSettings.tests_suite, mile)
        logger.info(mile_tests_suite)
        tests_suite = project.get_suite_by_name(mile_tests_suite)
        milestone = project.get_milestone_by_name(name=mile)
        for iso_number in tests_results.get(mile, {}):
            # Create new TestPlan name check the same name in testrail
            test_plan_name = '{milestone} iso #{iso_number}'.format(
                milestone=milestone['name'],
                iso_number=iso_number)
            test_plan = project.get_plan_by_name(test_plan_name)
            if not test_plan:
                test_plan = project.add_plan(
                    test_plan_name,
                    description='/'.join([JENKINS['url'],
                                          'job',
                                          '{0}.all'.format(milestone['name']),
                                          str(iso_number)]),
                    milestone_id=milestone['id'],
                    entries=[])
                logger.info('Created new TestPlan "{0}".'
                            .format(test_plan_name))
            else:
                logger.info('Found existing TestPlan "{0}".'
                            .format(test_plan_name))
            plan_entries = []
            # Create a test plan entry
            config_ids = []
            for os in operation_systems:
                if os['name'] in os_mile[mile]:
                    config_ids.append(os['id'])
                    cases_ids = []
                    plan_entries.append(
                        project.test_run_struct(
                            name=tests_suite['name'],
                            suite_id=tests_suite['id'],
                            milestone_id=milestone['id'],
                            description=('Results of system tests ({t_suite})'
                                         ' on iso #"{iso_number}"'
                                         .format(t_suite=tests_suite['name'],
                                                 iso_number=iso_number)),
                            config_ids=[os['id']],
                            include_all=True,
                            case_ids=cases_ids))
            # Create a test plan entry with the test run
            run = find_run_by_name(test_plan, tests_suite['name'])
            if not run:
                logger.info('Adding a test plan entry with test run %s ...',
                            tests_suite['name'])
                entry = project.add_plan_entry(plan_id=test_plan['id'],
                                               suite_id=tests_suite['id'],
                                               config_ids=config_ids,
                                               runs=plan_entries)
                logger.info('The test plan entry has been added.')
                run = entry['runs'][0]
            test_plan = project.get_plan(test_plan['id'])

            # STEP #4
            # Upload tests results to TestRail
            logger.info('Uploading tests results to TestRail...')
            for os_id in tests_results.get(mile, {})\
                    .get(iso_number, {}):
                logger.info('Checking tests results for %s...',
                            project.get_config(os_id)['name'])
                tests_added = publish_results(
                    project=project,
                    milestone_id=milestone['id'],
                    test_plan=test_plan,
                    suite_id=tests_suite['id'],
                    config_id=os_id,
                    results=tests_results[mile][iso_number][os_id])
                logger.debug('Added new results for tests (%s): %s',
                             project.get_config(os_id)['name'],
                             [r.group for r in tests_added])

            logger.info('Report URL: %s', test_plan['url'])


if __name__ == "__main__":
    main()
