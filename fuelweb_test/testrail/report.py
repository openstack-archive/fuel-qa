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

import functools
import re
import time
import yaml

from logging import DEBUG
from optparse import OptionParser
from builds import Build
from builds import get_build_artifact
from builds import get_downstream_builds_from_html
from builds import get_jobs_for_view
from launchpad_client import LaunchpadBug
from settings import JENKINS
from settings import GROUPS_TO_EXPAND
from settings import LaunchpadSettings
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject


class TestResult(object):
    """TestResult."""  # TODO documentation

    def __init__(self, name, group, status, duration, url=None,
                 version=None, description=None, comments=None,
                 launchpad_bug=None, steps=None):
        self.name = name
        self.group = group
        self._status = status
        self.duration = duration
        self.url = url
        self._version = version
        self.description = description
        self.comments = comments
        self.launchpad_bug = launchpad_bug
        self.launchpad_bug_status = None
        self.launchpad_bug_importance = None
        self.launchpad_bug_title = None
        self.available_statuses = {
            'passed': ['passed', 'fixed'],
            'failed': ['failed', 'regression'],
            'skipped': ['skipped'],
            'blocked': ['blocked'],
            'custom_status2': ['in_progress']
        }
        self._steps = steps

    @property
    def version(self):
        # Version string length is limited by 250 symbols because field in
        # TestRail has type 'String'. This limitation can be removed by
        # changing field type to 'Text'
        return (self._version or '')[:250]

    @version.setter
    def version(self, value):
        self._version = value[:250]

    @property
    def status(self):
        for s in self.available_statuses.keys():
            if self._status in self.available_statuses[s]:
                return s
        logger.error('Unsupported result status: "{0}"!'.format(self._status))
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def steps(self):
        return self._steps

    def __str__(self):
        result_dict = {
            'name': self.name,
            'group': self.group,
            'status': self.status,
            'duration': self.duration,
            'url': self.url,
            'version': self.version,
            'description': self.description,
            'comments': self.comments
        }
        return str(result_dict)


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
    version = get_version_from_parameters(jenkins_build_data)
    if not version:
        version = get_version_from_artifacts(jenkins_build_data)
    if not version:
        version = get_version_from_upstream_job(jenkins_build_data)
    if not version:
        raise Exception('Failed to get iso version from Jenkins jobs '
                        'parameters/artifacts!')
    return version


def get_version_from_upstream_job(jenkins_build_data):
    upstream_job = get_job_parameter(jenkins_build_data, 'UPSTREAM_JOB_URL')
    if not upstream_job:
        return
    causes = [a['causes'] for a in jenkins_build_data['actions']
              if 'causes' in a.keys()][0]
    if len(causes) > 0:
        upstream_job_name = causes[0]['upstreamProject']
        upstream_build_number = causes[0]['upstreamBuild']
        upstream_build = Build(upstream_job_name, upstream_build_number)
        return (get_version_from_artifacts(upstream_build.build_data) or
                get_version_from_parameters(upstream_build.build_data))


def get_job_parameter(jenkins_build_data, parameter):
    parameters = [a['parameters'] for a in jenkins_build_data['actions']
                  if 'parameters' in a.keys()][0]
    target_params = [p['value'] for p in parameters
                     if p['name'].lower() == str(parameter).lower()]
    if len(target_params) > 0:
        return target_params[0]


def get_version_from_parameters(jenkins_build_data):
    custom_version = get_job_parameter(jenkins_build_data, 'CUSTOM_VERSION')
    if custom_version:
        swarm_timestamp = jenkins_build_data['timestamp'] / 1000 \
            if 'timestamp' in jenkins_build_data else None
        return (TestRailSettings.milestone,
                time.strftime("%D %H:%M", time.localtime(swarm_timestamp)),
                custom_version)

    iso_link = get_job_parameter(jenkins_build_data, 'magnet_link')
    if iso_link:
        return get_version_from_iso_name(iso_link)


def get_version_from_artifacts(jenkins_build_data):
    if not any([artifact for artifact in jenkins_build_data['artifacts']
                if artifact['fileName'] == JENKINS['version_artifact']]):
        return
    version = yaml.load(get_build_artifact(
        url=jenkins_build_data['url'], artifact=JENKINS['version_artifact']))
    return version['VERSION']['release'], \
        int(version['VERSION']['build_number']), \
        ''


def get_version_from_iso_name(iso_link):
    match = re.search(r'.*\bfuel-(?P<prefix1>[a-zA-Z]*)-?(?P<version>\d+'
                      r'(?P<version2>\.\d+)+)-(?P<prefix2>[a-zA-Z]*)-?'
                      r'(?P<buildnum>\d+)-.*', iso_link)
    if match:
        return (match.group('version'),
                int(match.group('buildnum')),
                match.group('prefix1') or match.group('prefix2'))


def expand_test_group(group, systest_build_name, os):
    """Expand specified test names with the group name of the job
       which is taken from the build name, for example:
       group: 'setup_master'
       systest_build_name: '7.0.system_test.ubuntu.bonding_ha_one_controller'
       os: str, release name in lower case, for example: 'ubuntu'
       return: 'setup_master_bonding_ha_one_controller'
    """
    if group in GROUPS_TO_EXPAND:
        if os in systest_build_name:
            sep = '.' + os + '.'
        else:
            sep = '.'
        systest_group_name = systest_build_name.split(sep)[-1]

        if systest_group_name:
            group = '_'.join([group, systest_group_name])
    return group


def check_blocked(test):
    """Change test result status to 'blocked' if it was
    skipped due to failure of another dependent test
    :param test: dict, test result info
    :return: None
    """
    if test['status'].lower() != 'skipped':
        return
    match = re.match(r'^Failure in <function\s+(\w+)\s+at\s0x[a-f0-9]+>',
                     test['skippedMessage'])
    if match:
        failed_func_name = match.group(1)
        if test['name'] != failed_func_name:
            test['status'] = 'blocked'
            test['skippedMessage'] = 'Blocked by "{0}" test.'.format(
                failed_func_name)


def check_untested(test):
    """Check if test result is fake
    :param test: dict
    :return: bool
    """
    if test['name'] == 'jenkins' and 'skippedMessage' not in test:
        return True
    return False


@retry(count=3)
def get_tests_results(systest_build, os):
    tests_results = []
    test_build = Build(systest_build['name'], systest_build['number'])
    run_test_data = test_build.test_data()
    test_classes = {}
    for one in run_test_data['suites'][0]['cases']:
        className = one['className']
        if className not in test_classes:
            test_classes[className] = {}
            test_classes[className]['child'] = []
            test_classes[className]['duration'] = 0
            test_classes[className]["failCount"] = 0
            test_classes[className]["passCount"] = 0
            test_classes[className]["skipCount"] = 0
        else:
            if one['className'] == one['name']:
                logger.warning("Found duplicate test in run - {}".format(
                    one['className']))
                continue

        test_class = test_classes[className]
        test_class['child'].append(one)
        test_class['duration'] += float(one['duration'])
        if one['status'].lower() in ('failed', 'error'):
            test_class["failCount"] += 1
        if one['status'].lower() == 'passed':
            test_class["passCount"] += 1
        if one['status'].lower() == 'skipped':
            test_class["skipCount"] += 1

    for klass in test_classes:
        klass_result = test_classes[klass]
        if len(klass_result['child']) == 1:
            test = klass_result['child'][0]
            if check_untested(test):
                continue
            check_blocked(test)
            test_result = TestResult(
                name=test['name'],
                group=expand_test_group(test['className'],
                                        systest_build['name'],
                                        os),
                status=test['status'].lower(),
                duration='{0}s'.format(int(test['duration']) + 1),
                url='{0}testReport/(root)/{1}/'.format(test_build.url,
                                                       test['name']),
                version='_'.join(
                    [test_build.build_data["id"]] + (
                        test_build.build_data["description"] or
                        test['name']).split()),
                description=test_build.build_data["description"] or
                    test['name'],
                comments=test['skippedMessage']
            )
        else:
            case_steps = []
            test_duration = sum(
                [float(c['duration']) for c in klass_result['child']])
            steps = [c for c in klass_result['child']
                     if c['name'].startswith('Step')]
            steps = sorted(steps, key=lambda k: k['name'])
            test_name = steps[0]['className']
            test_group = steps[0]['className']
            test_comments = None
            is_test_failed = any([s['status'].lower() in ('failed', 'error')
                                  for s in steps])

            for step in steps:
                if step['status'].lower() in ('failed', 'error'):
                    case_steps.append({
                        "content": step['name'],
                        "actual": step['errorStackTrace'] or
                        step['errorDetails'],
                        "status": step['status'].lower()})
                    test_comments = "{err}\n\n\n{stack}".format(
                        err=step['errorDetails'],
                        stack=step['errorStackTrace'])
                else:
                    case_steps.append({
                        "content": step['name'],
                        "actual": "pass",
                        "status": step['status'].lower()
                    })
            test_result = TestResult(
                name=test_name,
                group=expand_test_group(test_group,
                                        systest_build['name'],
                                        os),
                status='failed' if is_test_failed else 'passed',
                duration='{0}s'.format(int(test_duration) + 1),
                url='{0}testReport/(root)/{1}/'.format(test_build.url,
                                                       test_name),
                version='_'.join(
                    [test_build.build_data["id"]] + (
                        test_build.build_data["description"] or
                        test_name).split()),
                description=test_build.build_data["description"] or
                    test_name,
                comments=test_comments,
                steps=case_steps,
            )
        tests_results.append(test_result)
    return tests_results


def publish_results(project, milestone_id, test_plan,
                    suite_id, config_id, results):
    test_run_ids = [run['id'] for entry in test_plan['entries']
                    for run in entry['runs'] if suite_id == run['suite_id'] and
                    config_id in run['config_ids']]
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
        case_id = project.get_case_by_group(suite_id=suite_id,
                                            group=result.group,
                                            cases=cases)['id']
        if result.version in existing_results_versions or not result.status:
            if result.status != 'passed':
                previous_results = project.get_all_results_for_case(
                    run_ids=[test_run_ids[0]],
                    case_id=case_id)
                lp_bug = get_existing_bug_link(previous_results)
                if lp_bug:
                    result.launchpad_bug = lp_bug['bug_link']
                    result.launchpad_bug_status = lp_bug['status']
                    result.launchpad_bug_importance = lp_bug['importance']
                    result.launchpad_bug_title = lp_bug['title']
            continue
        if result.status != 'passed':
            run_ids = [run['id'] for run in previous_tests_runs[0:
                       int(TestRailSettings.previous_results_depth)]]
            previous_results = project.get_all_results_for_case(
                run_ids=run_ids,
                case_id=case_id)
            lp_bug = get_existing_bug_link(previous_results)
            if lp_bug:
                result.launchpad_bug = lp_bug['bug_link']
                result.launchpad_bug_status = lp_bug['status']
                result.launchpad_bug_importance = lp_bug['importance']
                result.launchpad_bug_title = lp_bug['title']
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


def make_bug_statistics(test_results, test_plan, tests_suite,
                        project, operation_systems):
    bugs = {}
    cases = project.get_cases(suite_id=tests_suite['id'])

    for os in operation_systems:
        test_run_ids = [run['id'] for entry in test_plan['entries']
                        for run in entry['runs']
                        if tests_suite['id'] == run['suite_id'] and
                        os['id'] in run['config_ids']]

        for result in test_results[os['distro']]:
            try:
                case_id = project.get_case_by_group(suite_id=tests_suite['id'],
                                                    group=result.group,
                                                    cases=cases)['id']
            except:
                logger.info("group {} has no test".format(result.group))
                continue
            case_result = project.get_all_results_for_case(
                run_ids=test_run_ids, case_id=case_id)
            lp_bug = get_existing_bug_link(case_result)
            bug = lp_bug['bug_link'] if lp_bug else None
            if not bug:
                continue    # Bug is not linked to the test case result.
            distro = os['distro']
            if bug not in bugs:
                bugs[bug] = {}
                bugs[bug]['distro'] = {}
                bugs[bug]['count'] = 0
                bugs[bug]['status'] = lp_bug['status']
                bugs[bug]['importance'] = lp_bug['importance']
                bugs[bug]['title'] = lp_bug['title']
            if distro not in bugs[bug]['distro']:
                bugs[bug]['distro'][distro] = {}
            bugs[bug]['count'] += 1
            bugs[bug]['distro'][distro][result.url] = {}
            bugs[bug]['distro'][distro][result.url]['status'] = result.status
            bugs[bug]['distro'][distro][result.url]['group'] = result.group

    bugs_sorted = sorted(bugs.keys(), key=lambda x: bugs[x]['count'],
                         reverse=True)

    if bugs_sorted:
        bugs_string = ''
        bugs_string += "Summary of bugs in TestRail at" \
                       " {0}\n".format(time.strftime("%c"))
        for bug in bugs_sorted:
            jresults = ""
            for distro in bugs[bug]['distro'].keys():
                jresults += " {0}: ".format(distro)
                bugs_distro = bugs[bug]['distro'][distro]
                for res in bugs_distro:
                    jresults += (
                        '[{hint}]({res}) '
                        .format(res=res,
                                hint=bugs_distro[res]['group']))
            line = ('[{affected} TC(s)] [{importance}] [{status}] '
                    '[{title}]({link}) [{jresults}]\n'
                    .format(affected=bugs[bug]['count'],
                            importance=bugs[bug]['importance'],
                            status=bugs[bug]['status'],
                            link=bug,
                            title=bugs[bug]['title'],
                            jresults=jresults))
            bugs_string += line
        return bugs_string
    else:
        logger.info("No linked to test cases bugs found")
        return ''


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
            logger.warning("Bug with id '{bug_id}' is private or \
                doesn't exist.".format(bug_id=bug_id))
            continue
        except Exception:
            logger.exception("Strange situation with '{bug_id}' \
                issue".format(bug_id=bug_id))
            continue

        for target in bug.targets:
            if target['project'] == LaunchpadSettings.project and\
               target['milestone'] == LaunchpadSettings.milestone and\
               target['status'] not in LaunchpadSettings.closed_statuses:
                target['bug_link'] = result["custom_launchpad_bug"]
                return target


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
    parser.add_option('-o', '--one-job', dest='one_job_name',
                      default=None,
                      help=('Process only one job name from the specified '
                            'parent job or view'))
    parser.add_option("-w", "--view", dest="jenkins_view", default=False,
                      help="Get system tests jobs from Jenkins view")
    parser.add_option("-l", "--live", dest="live_report", action="store_true",
                      help="Get tests results from running swarm")
    parser.add_option("-m", "--manual", dest="manual_run", action="store_true",
                      help="Manually add tests cases to TestRun (tested only)")
    parser.add_option("-s", "--statistics", action="store_true",
                      dest="bug_statistics", default=False,
                      help="Make a statistics for bugs linked to TestRail for "
                      "the test run")
    parser.add_option('-c', '--create-plan-only', action="store_true",
                      dest="create_plan_only", default=False,
                      help='Jenkins swarm runner job name')
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")

    (options, args) = parser.parse_args()

    if options.verbose:
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

    tests_suite = project.get_suite_by_name(TestRailSettings.tests_suite)
    operation_systems = [{'name': config['name'], 'id': config['id'],
                         'distro': config['name'].split()[0].lower()}
                         for config in project.get_config_by_name(
                             'Operation System')['configs'] if
                         config['name'] in TestRailSettings.operation_systems]
    tests_results = {os['distro']: [] for os in operation_systems}

    # STEP #2
    # Get tests results from Jenkins
    logger.info('Getting tests results from Jenkins...')
    if options.jenkins_view:
        jobs = get_jobs_for_view(options.jenkins_view)
        tests_jobs = [{'name': j, 'number': 'latest'}
                      for j in jobs if 'system_test' in j] if \
            not options.create_plan_only else []
        runner_job = [j for j in jobs if 'runner' in j][0]
        runner_build = Build(runner_job, 'latest')
    elif options.job_name:
        runner_build = Build(options.job_name, options.build_number)
        tests_jobs = get_downstream_builds(runner_build.build_data) if \
            not options.create_plan_only else []
    else:
        logger.error("Please specify either Jenkins swarm runner job name (-j)"
                     " or Jenkins view with system tests jobs (-w). Exiting..")
        return

    is_running_builds = False

    for systest_build in tests_jobs:
        if (options.one_job_name and
                options.one_job_name != systest_build['name']):
            logger.debug("Skipping '{0}' because --one-job is specified"
                         .format(systest_build['name']))
            continue
        if options.job_name:
            if 'result' not in systest_build.keys():
                logger.debug("Skipping '{0}' job because it does't run tests "
                             "(build #{1} contains no results)".format(
                                 systest_build['name'],
                                 systest_build['number']))
                continue
            if systest_build['result'] is None:
                logger.debug("Skipping '{0}' job (build #{1}) because it's sti"
                             "ll running...".format(systest_build['name'],
                                                    systest_build['number'],))
                is_running_builds = True
                continue
        for os in tests_results.keys():
            if os in systest_build['name'].lower():
                tests_results[os].extend(get_tests_results(systest_build, os))

    # STEP #3
    # Create new TestPlan in TestRail (or get existing) and add TestRuns
    milestone, iso_number, prefix = get_version(runner_build.build_data)
    milestone = project.get_milestone_by_name(name=milestone)

    test_plan_name = ' '.join(
        filter(lambda x: bool(x),
               (milestone['name'], prefix, 'iso', '#' + str(iso_number))))

    test_plan = project.get_plan_by_name(test_plan_name)
    iso_link = '/'.join([JENKINS['url'], 'job',
                         '{0}.all'.format(milestone['name']), str(iso_number)])
    test_run = TestRailSettings.tests_description
    description = test_run if test_run else iso_link
    if not test_plan:
        test_plan = project.add_plan(test_plan_name,
                                     description=description,
                                     milestone_id=milestone['id'],
                                     entries=[]
                                     )
        logger.info('Created new TestPlan "{0}".'.format(test_plan_name))
    else:
        logger.info('Found existing TestPlan "{0}".'.format(test_plan_name))
        test_plan_description = test_plan.get('description')
        if description not in test_plan_description:
            new_description = test_plan_description + '\n' + description
            logger.info('Update description for existing TestPlan "{0}" '
                        'from "{1}" to {2}.'.format(test_plan_name,
                                                    test_plan_description,
                                                    new_description))
            project.update_plan(test_plan.get('id'),
                                description=new_description)

    if options.create_plan_only:
        return

    plan_entries = []
    all_cases = project.get_cases(suite_id=tests_suite['id'])
    for os in operation_systems:
        cases_ids = []
        if options.manual_run:
            all_results_groups = [r.group for r in tests_results[os['distro']]]
            for case in all_cases:
                if case['custom_test_group'] in all_results_groups:
                    cases_ids.append(case['id'])
        plan_entries.append(
            project.test_run_struct(
                name='{suite_name}'.format(suite_name=tests_suite['name']),
                suite_id=tests_suite['id'],
                milestone_id=milestone['id'],
                description='Results of system tests ({tests_suite}) on is'
                'o #"{iso_number}"'.format(tests_suite=tests_suite['name'],
                                           iso_number=iso_number),
                config_ids=[os['id']],
                include_all=True,
                case_ids=cases_ids
            )
        )

    if not any(entry['suite_id'] == tests_suite['id']
               for entry in test_plan['entries']):
        if project.add_plan_entry(plan_id=test_plan['id'],
                                  suite_id=tests_suite['id'],
                                  config_ids=[os['id'] for os
                                              in operation_systems],
                                  runs=plan_entries):
            test_plan = project.get_plan(test_plan['id'])

    # STEP #4
    # Upload tests results to TestRail
    logger.info('Uploading tests results to TestRail...')
    for os in operation_systems:
        logger.info('Checking tests results for "{0}"...'.format(os['name']))
        results_to_publish = publish_results(
            project=project,
            milestone_id=milestone['id'],
            test_plan=test_plan,
            suite_id=tests_suite['id'],
            config_id=os['id'],
            results=tests_results[os['distro']]
        )
        logger.debug('Added new results for tests ({os}): {tests}'.format(
            os=os['name'], tests=[r.group for r in results_to_publish]
        ))

    logger.info('Report URL: {0}'.format(test_plan['url']))

    # STEP #5
    # Provide the bugs linked in TestRail for current run as a short statistics
    if options.bug_statistics:
        if is_running_builds:
            logger.info("Some jobs are still running. "
                        "Skipping bug statistics report, please try later.")
        else:
            logger.info("Generating a bug statistics report...")
            bug_results = make_bug_statistics(tests_results, test_plan,
                                              tests_suite, project,
                                              operation_systems)
            project.update_plan(plan_id=test_plan['id'],
                                description=test_plan['description'] + '\n' +
                                bug_results)


if __name__ == "__main__":
    main()
