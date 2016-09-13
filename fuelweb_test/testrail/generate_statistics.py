#!/usr/bin/env python
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

from __future__ import unicode_literals

import json
import os
import re
import sys
import time

import argparse
from collections import OrderedDict
from logging import CRITICAL
from logging import DEBUG

from fuelweb_test.testrail.builds import Build
from fuelweb_test.testrail.launchpad_client import LaunchpadBug
from fuelweb_test.testrail.report import get_version
from fuelweb_test.testrail.settings import GROUPS_TO_EXPAND
from fuelweb_test.testrail.settings import LaunchpadSettings
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject


def inspect_bug(bug):
    # Return target which matches defined in settings project/milestone and
    # has 'open' status. If there are no such targets, then just return first
    # one available target.
    for target in bug.targets:
        if target['project'] == LaunchpadSettings.project and \
           LaunchpadSettings.milestone in target['milestone'] and\
           target['status'] not in LaunchpadSettings.closed_statuses:
            return target
    return bug.targets[0]


def generate_test_plan_name(job_name, build_number):
    # Generate name of TestPlan basing on iso image name
    # taken from Jenkins job build parameters
    runner_build = Build(job_name, build_number)
    milestone, iso_number, prefix = get_version(runner_build.build_data)
    if 'snapshot' not in prefix:
        return ' '.join(filter(lambda x: bool(x), (milestone,
                                                   prefix, 'iso',
                                                   '#' + str(iso_number))))
    else:
        return ' '.join(filter(lambda x: bool(x), (milestone,
                                                   prefix)))


def get_testrail():
    logger.info('Initializing TestRail Project configuration...')
    return TestRailProject(url=TestRailSettings.url,
                           user=TestRailSettings.user,
                           password=TestRailSettings.password,
                           project=TestRailSettings.project)


class TestRunStatistics(object):
    """Statistics for attached bugs in TestRun
    """

    def __init__(self, project, run_id, check_blocked=False):
        self.project = project
        self.run = self.project.get_run(run_id)
        self.tests = self.project.get_tests(run_id)
        self.results = self.get_results()
        logger.info('Found TestRun "{0}" on "{1}" with {2} tests and {3} '
                    'results'.format(self.run['name'],
                                     self.run['config'] or 'default config',
                                     len(self.tests), len(self.results)))
        self.blocked_statuses = [self.project.get_status(s)['id']
                                 for s in TestRailSettings.stauses['blocked']]
        self.failed_statuses = [self.project.get_status(s)['id']
                                for s in TestRailSettings.stauses['failed']]
        self.check_blocked = check_blocked
        self._bugs_statistics = {}

    def __getitem__(self, item):
        return self.run.__getitem__(item)

    def get_results(self):
        results = []
        stop = 0
        offset = 0
        while not stop:
            new_results = self.project.get_results_for_run(
                self.run['id'],
                limit=TestRailSettings.max_results_per_request,
                offset=offset)
            results += new_results
            offset += len(new_results)
            stop = TestRailSettings.max_results_per_request - len(new_results)
        return results

    def get_test_by_group(self, group, version):
        if group in GROUPS_TO_EXPAND:
            m = re.search(r'^\d+_(\S+)_on_[\d\.]+', version)
            if m:
                tests_thread = m.group(1)
                group = '{0}_{1}'.format(group, tests_thread)
        elif TestRailSettings.extra_factor_of_tc_definition:
            group = '{}_{}'.format(
                group,
                TestRailSettings.extra_factor_of_tc_definition
            )
        for test in self.tests:
            if test['custom_test_group'] == group:
                return test
        logger.error('Test with group "{0}" not found!'.format(group))

    def handle_blocked(self, test, result):
        if result['custom_launchpad_bug']:
            return False
        m = re.search(r'Blocked by "(\S+)" test.', result['comment'] or '')
        if m:
            blocked_test_group = m.group(1)
        else:
            logger.warning('Blocked result #{0} for test {1} does '
                           'not have upstream test name in its '
                           'comments!'.format(result['id'],
                                              test['custom_test_group']))
            return False

        if not result['version']:
            logger.debug('Blocked result #{0} for test {1} does '
                         'not have version, can\'t find upstream '
                         'test case!'.format(result['id'],
                                             test['custom_test_group']))
            return False

        bug_link = None
        blocked_test = self.get_test_by_group(blocked_test_group,
                                              result['version'])
        if not blocked_test:
            return False
        logger.debug('Test {0} was blocked by failed test {1}'.format(
            test['custom_test_group'], blocked_test_group))

        blocked_results = self.project.get_results_for_test(
            blocked_test['id'])

        # Since we manually add results to failed tests with statuses
        # ProdFailed, TestFailed, etc. and attach bugs links to them,
        # we could skip original version copying. So look for test
        # results with target version, but allow to copy links to bugs
        # from other results of the same test (newer are checked first)
        if not any(br['version'] == result['version'] and
                   br['status_id'] in self.failed_statuses
                   for br in blocked_results):
            logger.debug('Did not find result for test {0} with version '
                         '{1}!'.format(blocked_test_group, result['version']))
            return False

        for blocked_result in sorted(blocked_results,
                                     key=lambda x: x['id'],
                                     reverse=True):
            if blocked_result['status_id'] not in self.failed_statuses:
                continue

            if blocked_result['custom_launchpad_bug']:
                bug_link = blocked_result['custom_launchpad_bug']
                break

        if bug_link is not None:
            result['custom_launchpad_bug'] = bug_link
            self.project.add_raw_results_for_test(test['id'], result)
            logger.info('Added bug {0} to blocked result of {1} test.'.format(
                bug_link, test['custom_test_group']))
            return bug_link
        return False

    @property
    def bugs_statistics(self):
        if self._bugs_statistics != {}:
            return self._bugs_statistics
        logger.info('Collecting stats for TestRun "{0}" on "{1}"...'.format(
            self.run['name'], self.run['config'] or 'default config'))

        for test in self.tests:
            logger.debug('Checking "{0}" test...'.format(test['title']))
            test_results = sorted(
                self.project.get_results_for_test(test['id'], self.results),
                key=lambda x: x['id'], reverse=True)

            linked_bugs = []
            is_blocked = False

            for result in test_results:
                if result['status_id'] in self.blocked_statuses:
                    if self.check_blocked:
                        new_bug_link = self.handle_blocked(test, result)
                        if new_bug_link:
                            linked_bugs.append(new_bug_link)
                            is_blocked = True
                            break
                    if result['custom_launchpad_bug']:
                        linked_bugs.append(result['custom_launchpad_bug'])
                        is_blocked = True
                        break
                if result['status_id'] in self.failed_statuses \
                        and result['custom_launchpad_bug']:
                    linked_bugs.append(result['custom_launchpad_bug'])

            bug_ids = set([re.search(r'.*bugs?/(\d+)/?', link).group(1)
                           for link in linked_bugs
                           if re.search(r'.*bugs?/(\d+)/?', link)])

            for bug_id in bug_ids:
                if bug_id in self._bugs_statistics:
                    self._bugs_statistics[bug_id][test['id']] = {
                        'group': test['custom_test_group'] or 'manual',
                        'config': self.run['config'] or 'default',
                        'blocked': is_blocked
                    }

                else:
                    self._bugs_statistics[bug_id] = {
                        test['id']: {
                            'group': test['custom_test_group'] or 'manual',
                            'config': self.run['config'] or 'default',
                            'blocked': is_blocked
                        }
                    }
        return self._bugs_statistics


class StatisticsGenerator(object):
    """Generate statistics for bugs attached to TestRuns in TestPlan
    """

    def __init__(self, project, plan_id, run_ids=(), handle_blocked=False):
        self.project = project
        self.test_plan = self.project.get_plan(plan_id)
        logger.info('Found TestPlan "{0}"'.format(self.test_plan['name']))

        self.test_runs_stats = [
            TestRunStatistics(self.project, r['id'], handle_blocked)
            for e in self.test_plan['entries'] for r in e['runs']
            if r['id'] in run_ids or len(run_ids) == 0
        ]

        self.bugs_statistics = {}

    def generate(self):
        for test_run in self.test_runs_stats:
            test_run_stats = test_run.bugs_statistics
            self.bugs_statistics[test_run['id']] = dict()
            for bug, tests in test_run_stats.items():
                if bug in self.bugs_statistics[test_run['id']]:
                    self.bugs_statistics[test_run['id']][bug].update(tests)
                else:
                    self.bugs_statistics[test_run['id']][bug] = tests
            logger.info('Found {0} linked bug(s)'.format(
                len(self.bugs_statistics[test_run['id']])))

    def update_desription(self, stats):
        old_description = self.test_plan['description']
        new_description = ''
        for line in old_description.split('\n'):
            if not re.match(r'^Bugs Statistics \(generated on .*\)$', line):
                new_description += line + '\n'
            else:
                break
        new_description += '\n' + stats
        return self.project.update_plan(plan_id=self.test_plan['id'],
                                        description=new_description)

    def dump(self, run_id=None):
        stats = dict()

        if not run_id:
            joint_bugs_statistics = dict()
            for run in self.bugs_statistics:
                for bug, tests in self.bugs_statistics[run].items():
                    if bug in joint_bugs_statistics:
                        joint_bugs_statistics[bug].update(tests)
                    else:
                        joint_bugs_statistics[bug] = tests
        else:
            for _run_id, _stats in self.bugs_statistics.items():
                if _run_id == run_id:
                    joint_bugs_statistics = _stats

        for bug_id in joint_bugs_statistics:
            try:
                lp_bug = LaunchpadBug(bug_id).get_duplicate_of()
            except KeyError:
                logger.warning("Bug with ID {0} not found! Most probably it's "
                               "private or private security.".format(bug_id))
                continue
            bug_target = inspect_bug(lp_bug)

            if lp_bug.bug.id in stats:
                stats[lp_bug.bug.id]['tests'].update(
                    joint_bugs_statistics[bug_id])
            else:
                stats[lp_bug.bug.id] = {
                    'title': bug_target['title'],
                    'importance': bug_target['importance'],
                    'status': bug_target['status'],
                    'project': bug_target['project'],
                    'link': lp_bug.bug.web_link,
                    'tests': joint_bugs_statistics[bug_id]
                }
            stats[lp_bug.bug.id]['failed_num'] = len(
                [t for t, v in stats[lp_bug.bug.id]['tests'].items()
                 if not v['blocked']])
            stats[lp_bug.bug.id]['blocked_num'] = len(
                [t for t, v in stats[lp_bug.bug.id]['tests'].items()
                 if v['blocked']])

        return OrderedDict(sorted(stats.items(),
                                  key=lambda x: (x[1]['failed_num'] +
                                                 x[1]['blocked_num']),
                                  reverse=True))

    def dump_html(self, stats=None, run_id=None):
        if stats is None:
            stats = self.dump()

        html = '<html xmlns="http://www.w3.org/1999/xhtml" lang="en">\n'
        html += '<h2>Bugs Statistics (generated on {0})</h2>\n'.format(
            time.strftime("%c"))
        html += '<h3>TestPlan: "{0}"</h3>\n'.format(self.test_plan['name'])
        if run_id:
            test_run = [r for r in self.test_runs_stats if r['id'] == run_id]
            if test_run:
                html += '<h4>TestRun: "{0}"</h4>\n'.format(test_run[0]['name'])

        for values in stats.values():
            if values['status'].lower() in ('invalid',):
                color = 'gray'
            elif values['status'].lower() in ('new', 'confirmed', 'triaged'):
                color = 'red'
            elif values['status'].lower() in ('in progress',):
                color = 'blue'
            elif values['status'].lower() in ('fix committed',):
                color = 'goldenrod'
            elif values['status'].lower() in ('fix released',):
                color = 'green'
            else:
                color = 'orange'

            title = re.sub(r'(Bug\s+#\d+\s+)(in\s+[^:]+:\s+)', '\g<1>',
                           values['title'])
            title = re.sub(r'(.{100}).*', '\g<1>...', title)
            html += '[{0:<3} failed TC(s)]'.format(values['failed_num'])
            html += '[{0:<3} blocked TC(s)]'.format(values['blocked_num'])
            html += ('[{0:^4}][{1:^9}]'
                     '[<b><font color={3}>{2:^13}</font></b>]').format(
                values['project'], values['importance'], values['status'],
                color)
            html += '[<a href="{0}">{1}</a>]'.format(values['link'], title)
            index = 1
            for tid, params in values['tests'].items():
                if index > 1:
                    link_text = '{}'.format(index)
                else:
                    link_text = '{0} on {1}'.format(params['group'],
                                                    params['config'])
                html += ('[<a href="{0}/index.php?/tests/view/{1}">{2}</a>]</'
                         'font>').format(TestRailSettings.url, tid, link_text)
                index += 1
            html += '</br>\n'
        html += '</html>\n'
        return html

    def publish(self, stats=None):
        if stats is None:
            stats = self.dump()

        header = 'Bugs Statistics (generated on {0})\n'.format(
            time.strftime("%c"))
        header += '==================================\n'

        bugs_table = ('|||:Failed|:Blocked|:Project|:Priority'
                      '|:Status|:Bug link|:Tests\n')

        for values in stats.values():
            title = re.sub(r'(Bug\s+#\d+\s+)(in\s+[^:]+:\s+)', '\g<1>',
                           values['title'])
            title = re.sub(r'(.{100}).*', '\g<1>...', title)
            title = title.replace('[', '{')
            title = title.replace(']', '}')
            bugs_table += (
                '||{failed}|{blocked}|{project}|{priority}|{status}|').format(
                failed=values['failed_num'], blocked=values['blocked_num'],
                project=values['project'].upper(),
                priority=values['importance'], status=values['status'])
            bugs_table += '[{0}]({1})|'.format(title, values['link'])
            index = 1
            for tid, params in values['tests'].items():
                if index > 1:
                    link_text = '{}'.format(index)
                else:
                    link_text = '{0} on {1}'.format(params['group'],
                                                    params['config'])
                bugs_table += '[{{{0}}}]({1}/index.php?/tests/view/{2}) '.\
                    format(link_text, TestRailSettings.url, tid)
                index += 1
            bugs_table += '\n'

        return self.update_desription(header + bugs_table)


def save_stats_to_file(stats, file_name, html=''):
    def warn_file_exists(file_path):
        if os.path.exists(file_path):
            logger.warning('File {0} exists and will be '
                           'overwritten!'.format(file_path))

    json_file_path = '{}.json'.format(file_name)
    warn_file_exists(json_file_path)

    with open(json_file_path, 'w+') as f:
        json.dump(stats, f)

    if html:
        html_file_path = '{}.html'.format(file_name)
        warn_file_exists(html_file_path)
        with open(html_file_path, 'w+') as f:
            f.write(html)


def main():
    parser = argparse.ArgumentParser(
        description="Generate statistics for bugs linked to TestRun. Publish "
                    "statistics to testrail if necessary."
    )
    parser.add_argument('plan_id', type=int, nargs='?', default=None,
                        help='Test plan ID in TestRail')
    parser.add_argument('-j', '--job-name',
                        dest='job_name', type=str, default=None,
                        help='Name of Jenkins job which runs tests (runner). '
                             'It will be used for TestPlan search instead ID')
    parser.add_argument('-n', '--build-number', dest='build_number',
                        default='latest', help='Jenkins job build number')
    parser.add_argument('-r', '--run-id',
                        dest='run_ids', type=str, default=None,
                        help='(optional) IDs of TestRun to check (skip other)')
    parser.add_argument('-b', '--handle-blocked', action="store_true",
                        dest='handle_blocked', default=False,
                        help='Copy bugs links to downstream blocked results')
    parser.add_argument('-s', '--separate-runs', action="store_true",
                        dest='separate_runs', default=False,
                        help='Create separate statistics for each test run')
    parser.add_argument('-p', '--publish', action="store_true",
                        help='Publish statistics to TestPlan description')
    parser.add_argument('-o', '--out-file', dest='output_file',
                        default=None, type=str,
                        help='Path to file to save statistics as JSON and/or '
                             'HTML. Filename extension is added automatically')
    parser.add_argument('-H', '--html', action="store_true",
                        help='Save statistics in HTML format to file '
                             '(used with --out-file option)')
    parser.add_argument('-q', '--quiet', action="store_true",
                        help='Be quiet (disable logging except critical) '
                             'Overrides "--verbose" option.')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging.")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(DEBUG)

    if args.quiet:
        logger.setLevel(CRITICAL)

    testrail_project = get_testrail()

    if args.job_name:
        logger.info('Inspecting {0} build of {1} Jenkins job for TestPlan '
                    'details...'.format(args.build_number, args.job_name))
        test_plan_name = generate_test_plan_name(args.job_name,
                                                 args.build_number)
        test_plan = testrail_project.get_plan_by_name(test_plan_name)
        if test_plan:
            args.plan_id = test_plan['id']
        else:
            logger.warning('TestPlan "{0}" not found!'.format(test_plan_name))

    if not args.plan_id:
        logger.error('There is no TestPlan to process, exiting...')
        return 1

    run_ids = () if not args.run_ids else tuple(
        int(arg) for arg in args.run_ids.split(','))

    generator = StatisticsGenerator(testrail_project,
                                    args.plan_id,
                                    run_ids,
                                    args.handle_blocked)
    generator.generate()
    stats = generator.dump()

    if args.publish:
        logger.debug('Publishing bugs statistics to TestRail..')
        generator.publish(stats)

    if args.output_file:
        html = generator.dump_html(stats) if args.html else args.html
        save_stats_to_file(stats, args.output_file, html)

        if args.separate_runs:
            for run in generator.test_runs_stats:
                file_name = '{0}_{1}'.format(args.output_file, run['id'])
                stats = generator.dump(run_id=run['id'])
                html = (generator.dump_html(stats, run['id']) if args.html
                        else args.html)
                save_stats_to_file(stats, file_name, html)

    logger.info('Statistics generation complete!')


if __name__ == "__main__":
    sys.exit(main())
