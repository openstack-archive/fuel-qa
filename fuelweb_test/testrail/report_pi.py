#!/usr/bin/env python
#
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

import functools
import re
import yaml

import json
import urllib2

from logging import DEBUG
from optparse import OptionParser

from builds import Build
from builds import get_build_artifact
from builds import get_downstream_builds_from_html
from builds import get_jobs_for_view
from builds import get_test_for_view
from launchpad_client import LaunchpadBug
from settings import JENKINS
from settings import LaunchpadSettings
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject
from report import TestResult

# My metods

def find_run_by_name_and_config(test_plan, run_name):
    """This function finds the test run by its name and the specified
    configuration (for example, Centos 6.5).
    """

    for entry in test_plan['entries']:
        for run in entry['runs']:
            if run['name'] == run_name:
                return run


def retry(count=3):
    def wrapped(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            i = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except:
                    i += 1
                    if i >= count:
                        raise

        return wrapper

    return wrapped


def get_downstream_builds(jenkins_build_data, status=None):
    if 'subBuilds' not in jenkins_build_data.keys():
        return get_downstream_builds_from_html(jenkins_build_data['url'])

    return [{'name': b['jobName'], 'number': b['buildNumber'],
             'result': b['result']} for b in jenkins_build_data['subBuilds']]


def get_version(jenkins_build_data):
    if any([artifact for artifact in jenkins_build_data['artifacts']
            if artifact['fileName'] == JENKINS['version_artifact']]):
        return get_version_from_artifacts(jenkins_build_data)
    else:
        return get_version_from_parameters(jenkins_build_data)


def get_job_parameter(jenkins_build_data, parameter):
    parameters = [a['parameters'] for a in jenkins_build_data['actions']
                  if 'parameters' in a.keys()][0]
    target_params = [p['value'] for p in parameters
                     if p['name'].lower() == str(parameter).lower()]
    if len(target_params) > 0:
        return target_params[0]


def get_version_from_parameters(jenkins_build_data):
    iso_link = get_job_parameter(jenkins_build_data, 'magnet_link')
    if iso_link:
        match = re.search(r'.*\bfuel-(\d+(\.\d+)+)-(\d+)-.*', iso_link)
        if match:
            return match.group(1), int(match.group(3))
    upstream_job = get_job_parameter(jenkins_build_data, 'UPSTREAM_JOB_URL')
    if upstream_job:
        causes = [a['causes'] for a in jenkins_build_data['actions']
                  if 'causes' in a.keys()][0]
        if len(causes) > 0:
            upstream_job_name = causes[0]['upstreamProject']
            upstream_build_number = causes[0]['upstreamBuild']
            upstream_build = Build(upstream_job_name, upstream_build_number)
            return get_version_from_artifacts(upstream_build.build_data)


def get_version_from_artifacts(jenkins_build_data):
    version = yaml.load(get_build_artifact(
        url=jenkins_build_data['url'], artifact=JENKINS['version_artifact']))
    return version['VERSION']['release'], \
           int(version['VERSION']['build_number'])


@retry(count=3)
def get_tests_results(systest_build):
    tests_results = []
    test_build = Build(systest_build['name'], systest_build['number'])
    for test in test_build.test_data()['suites'][0]['cases']:
        test_result = TestResult(
            name=test['name'],
            group=test['className'],
            status=test['status'].lower(),
            duration='{0}s'.format(int(test['duration']) + 1),
            url='{0}testReport/(root)/{1}/'.format(test_build.url,
                                                   test['name']),
            version='_'.join([test_build.build_data["id"]] +
                             (test_build.build_data["description"]
                              or test['name']).split()),
            description=test_build.build_data["description"] or
                        test['name'],
        )
        tests_results.append(test_result)
    return tests_results


def publish_results(project, milestone_id, test_plan,
                    suite_id, config_id, results):
    test_run_ids = [run['id'] for entry in test_plan['entries']
                    for run in entry['runs'] if suite_id == run['suite_id']
                    and config_id in run['config_ids']]
    logger.debug('Looking for previous tests runs on "{0}" using tests suite '
                 '"{1}"...'.format(project.get_config(config_id)['name'],
                                   project.get_suite(suite_id)['name']))
    previous_tests_runs = project.get_previous_runs(milestone_id=milestone_id,
                                                    suite_id=suite_id,
                                                    config_id=config_id)
    cases = project.get_cases(suite_id=suite_id)
    tests = project.get_tests(run_id=test_run_ids[0])
    results_to_publish = []

    for result in results:
        test = project.get_test_by_group(run_id=test_run_ids[0],
                                         group=result.group,
                                         tests=tests)
        if not test:
            logger.error("Test for '{0}' group not found: {1}".format(
                result.group, result.url))
            continue
        existing_results_versions = [r['version'] for r in
                                     project.get_results_for_test(test['id'])]
        if result.version in existing_results_versions:
            continue
        if result.status != 'passed':
            run_ids = [run['id'] for run in previous_tests_runs[0:
            int(TestRailSettings.previous_results_depth)]]
            case_id = project.get_case_by_group(suite_id=suite_id,
                                                group=result.group,
                                                cases=cases)['id']
            previous_results = project.get_all_results_for_case(
                run_ids=run_ids,
                case_id=case_id)
            result.launchpad_bug = get_existing_bug_link(previous_results)
        results_to_publish.append(result)
    try:
        if len(results_to_publish) > 0:
            project.add_results_for_cases(run_id=test_run_ids[0],
                                          suite_id=suite_id,
                                          tests_results=results_to_publish)
    except:
        logger.error('Failed to add new results for tests: {0}'.format(
            [r.group for r in results_to_publish]
        ))
        raise
    return results_to_publish


@retry(count=3)
def get_existing_bug_link(previous_results):
    results_with_bug = [result for result in previous_results if
                        result["custom_launchpad_bug"] is not None]
    if not results_with_bug:
        return
    for result in sorted(results_with_bug,
                         key=lambda k: k['created_on'],
                         reverse=True):
        try:
            bug_id = int(result["custom_launchpad_bug"].strip('/').split(
                '/')[-1])
        except ValueError:
            logger.warning('Link "{0}" doesn\'t contain bug id.'.format(
                result["custom_launchpad_bug"]))
            continue
        try:
            bug = LaunchpadBug(bug_id).get_duplicate_of()
        except KeyError:
            logger.error("Bug with id '{bug_id}' is private or "
                         "doesn't exist.".format(bug_id=bug_id))
            return

        for target in bug.targets:
            if target['project'] == LaunchpadSettings.project and \
                            target['milestone'] == LaunchpadSettings.milestone and \
                            target['status'] not in LaunchpadSettings.closed_statuses:
                return result["custom_launchpad_bug"]


def get_job_info(url):
    job_url = "/".join([url, 'api/json'])
    logger.debug("Request job info from {}".format(job_url))
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
    parser.add_option("-w", "--view", dest="jenkins_view", default=False,
                      help="Get system tests jobs from Jenkins view")
    parser.add_option("-l", "--live", dest="live_report", action="store_true",
                      help="Get tests results from running swarm")
    parser.add_option("-m", "--manual", dest="manual_run", action="store_true",
                      help="Manually add tests cases to TestRun (tested only)")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")

    (options, args) = parser.parse_args()

    # if options.verbose:
    logger.setLevel(DEBUG)

    if options.live_report and options.build_number == 'latest':
        options.build_number = 'latest_started'

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
    operation_systems_mile = {'6.1': ['Centos 6.5', 'Ubuntu 14.04'],
                              '6.0.1': ['Centos 6.5', 'Ubuntu 12.04']}

    tests_results = {}

    # STEP #2
    # Get tests results from Jenkins
    runner_build = Build(options.job_name, options.build_number)
    runs = runner_build.build_data['runs']  # Eto vse moi testi is jenkinsa

    # Vibrasivaem nenuznoe i formiruem rezultati trestov iz nuznogo
    for run_one in runs:
        if '5.1' in run_one['url']:
            continue
        tests_result = get_job_info(run_one['url'])
        if 'skipping' in tests_result['description']:
            continue
        tests_job = {'result': tests_result['result'],
                     'name': options.job_name + '/' + tests_result['url'].split('/')[-3],
                     'number': int(tests_result['url'].split('/')[-2]),
                     'mile': tests_result['description'].split()[0].split('-')[0],
                     'iso': int(tests_result['description'].split()[0].split('-')[1])}
        if not tests_results.has_key(tests_job['mile']):
            tests_results[tests_job['mile']] = {}
        if not tests_results[tests_job['mile']].has_key(tests_job['iso']):
            tests_results[tests_job['mile']][tests_job['iso']] = {}
        for os in operation_systems:
            if os['distro'] in tests_job['name'].lower() and os['name'] in operation_systems_mile[tests_job['mile']]:
                if not tests_results[tests_job['mile']][tests_job['iso']].has_key(os['id']):
                    tests_results[tests_job['mile']][tests_job['iso']][os['id']] = []
                tests_results[tests_job['mile']][tests_job['iso']][os['id']]. \
                    extend(get_tests_results(tests_job))

    # STEP #3
    # Create new TestPlan in TestRail (or get existing) and add TestRuns
    for mile in tests_results.keys():
        mile_tests_suite = TestRailSettings.tests_suite + mile
        logger.info(mile_tests_suite)
        tests_suite = project.get_suite_by_name(mile_tests_suite)
        suite_name = '{suite_name}'.format(suite_name=tests_suite['name'])
        for iso_number in tests_results[mile].keys():
            milestone = project.get_milestone_by_name(name=mile)
            config_ids = tests_results[mile][iso_number].keys()
            # Pridumivaem imja testplana
            test_plan_name = '{milestone} iso #{iso_number}'.format(
                milestone=milestone['name'],
                iso_number=iso_number)
            # Uznaem est li takoy test_plan v testrail
            test_plan = project.get_plan_by_name(test_plan_name)
            # Esli takogo test_plan net, to sozdaem ego
            if not test_plan:
                test_plan = project.add_plan(test_plan_name,
                                             description='/'.join([
                                                 JENKINS['url'],
                                                 'job',
                                                 '{0}.all'.format(milestone['name']),
                                                 str(iso_number)]),
                                             milestone_id=milestone['id'],
                                             entries=[]
                                             )
                logger.info('Created new TestPlan "{0}".'.format(test_plan_name))
            else:
                logger.info('Found existing TestPlan "{0}".'.format(test_plan_name))
            plan_entries = []
            for os_id in tests_results[mile][iso_number].keys():
                cases_ids = []
                plan_entries.append(
                    project.test_run_struct(
                        name=suite_name,
                        suite_id=tests_suite['id'],
                        milestone_id=milestone['id'],
                        description='Results of system tests ({tests_suite}) on is'
                        'o #"{iso_number}"'.format(tests_suite=tests_suite['name'],
                                                   iso_number=iso_number),
                        config_ids=[os_id],
                        include_all=True,
                        case_ids=cases_ids
                    )
                )
            # Create a test plan entry with the test run
            run = find_run_by_name_and_config(test_plan, suite_name)
            if not run:
                logger.info('Adding a test plan entry with test run '
                            '"{0} " ...'.format(suite_name))
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
            for os_id in tests_results[mile][iso_number].keys():
                logger.info('Checking tests results for "{0}"...'.format(os_id))
                tests_results[mile][iso_number][os_id] = publish_results(
                    project=project,
                    milestone_id=milestone['id'],
                    test_plan=test_plan,
                    suite_id=tests_suite['id'],
                    config_id=os_id,
                    results=tests_results[mile][iso_number][os_id]
                )
                logger.debug('Added new results for tests ({os}): {tests}'.format(
                    os=os_id, tests=[r.group for r in tests_results[mile][iso_number][os_id]]
                ))

            logger.info('Report URL: {0}'.format(test_plan['url']))

if __name__ == "__main__":
    main()
