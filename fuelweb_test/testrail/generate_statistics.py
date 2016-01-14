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

import os
import re

import argparse
from logging import DEBUG
from launchpad_client import LaunchpadBug
from settings import GROUPS_TO_EXPAND
from settings import LaunchpadSettings
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject


def inspect_bug(bug):
    for target in bug.targets:
        if target['project'] == LaunchpadSettings.project and \
           target['milestone'] == LaunchpadSettings.milestone and\
           target['status'] not in LaunchpadSettings.closed_statuses:
            return target
    return bug.targets[0]


class StatisticsGenerator(object):

    def __init__(self, run_id):
        logger.info('Initializing TestRail Project configuration...')
        self.project = TestRailProject(url=TestRailSettings.url,
                                       user=TestRailSettings.user,
                                       password=TestRailSettings.password,
                                       project=TestRailSettings.project)

        self.test_run = self.project.get_run(run_id)
        logger.info('Found TestRun with ID #{0}: {1}'.format(
            run_id, self.test_run['name']))
        self.test_plan = self.project.get_plan(self.test_run['plan_id'])
        logger.info('TestPlan is {0}'.format(self.test_plan['name']))
        self.tests = self.project.get_tests(self.test_run['id'])
        logger.info('Found {0} tests, checking results...'.format(
            len(self.tests)))
        self.results = self.project.get_results_for_run(self.test_run['id'])
        self.blocked_status = self.project.get_status('blocked')['id']
        self.failed_statuses = [self.project.get_status(s)['id']
                                for s in ('failed', 'product_failed',
                                          'test_failed', 'infra_failed')]
        self.bugs_statistics = {}

    def get_test_by_group(self, group, version):
        if group in GROUPS_TO_EXPAND:
            m = re.search(r'^\d+_(\S+)_on_[\d\.]+', version)
            if m:
                tests_thread = m.group(1)
                group = '{0}_{1}'.format(group, tests_thread)
        for test in self.tests:
            if test['custom_test_group'] == group:
                return test
        logger.error('Test with group "{0}" not found!'.format(group))

    def handle_blocked(self, test, result):
        if result['custom_launchpad_bug']:
            return False
        m = re.search(r'Blocked by "(\S+)" test.', result['comment'])
        if m:
            blocked_test_group = m.group(1)
        else:
            blocked_test_group = None
        logger.info('%s %s' % (test['custom_test_group'], blocked_test_group))

        if blocked_test_group and result['version']:
            bug_link = None
            blocked_test = self.get_test_by_group(blocked_test_group,
                                                  result['version'])
            if not blocked_test:
                return False
            blocked_results = self.project.get_results_for_test(
                blocked_test['id'])

            if not any(br['version'] == result['version']
                       and br['status_id'] in self.failed_statuses
                       for br in blocked_results):
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
                logger.debug('Added bug {0} to blocked result of {1}.'.format(
                    bug_link, test['custom_test_group']))
                return bug_link
            return False

    def generate(self, handle_blocked=False):
        for test in self.tests:
            logger.debug('Checking "{0}" test...'.format(test['title']))
            test_results = sorted(
                self.project.get_results_for_test(test['id']),
                key=lambda x: x['id'], reverse=True
            )

            linked_bugs = []

            for result in test_results:
                if result['status_id'] == self.blocked_status:
                    if handle_blocked:
                        new_bug_link = self.handle_blocked(test, result)
                        if new_bug_link:
                            linked_bugs.append(new_bug_link)
                            break
                    if result['custom_launchpad_bug']:
                        linked_bugs.append(result['custom_launchpad_bug'])
                if result['status_id'] in self.failed_statuses \
                        and result['custom_launchpad_bug']:
                    linked_bugs.append(result['custom_launchpad_bug'])

            bug_ids = set([re.search(r'.*bug/(\d+)/?', link).group(1)
                           for link in linked_bugs
                           if re.search(r'.*bug/(\d+)/?', link)])

            for bug_id in bug_ids:
                if bug_id in self.bugs_statistics:
                    self.bugs_statistics[bug_id].add(test['id'])
                else:
                    self.bugs_statistics[bug_id] = {test['id']}

    def dump(self, html=False):
        if html:
            stats = '<html xmlns="http://www.w3.org/1999/xhtml" lang="en">\n'
        else:
            stats = '======================================================='
        for bug_id in sorted(self.bugs_statistics,
                             key=lambda x: len(self.bugs_statistics[x]),
                             reverse=True):
            try:
                lp_bug = LaunchpadBug(bug_id)
            except KeyError:
                logger.warning("Bug with ID {0} not found! Most probably it's "
                               "private or private security.".format(bug_id))
                continue
            bug = inspect_bug(lp_bug)
            if html:
                stats += '[{0}]'.format(len(self.bugs_statistics[bug_id]))
                stats += '[{0}][{1}]'.format(bug['project'], bug['status'])
                stats += ('[<a href="https://bugs.launchpad.net/'
                          '{0}/+bug/{1}">{2}</a>]').format(
                    bug['project'], bug_id, bug['title'])
            else:
                stats += '[{0}]'.format(len(self.bugs_statistics[bug_id]))
                stats += '[{0}][{1}]'.format(bug['project'], bug['status'])
                stats += '[#{0}]["{2}"]'.format(bug_id, bug['title'])
            index = 1
            for test in self.bugs_statistics[bug_id]:
                if html:
                    stats += ('[<a href="https://mirantis.testrail.com/'
                              'index.php?/tests/view/{0}">{1}</a>]').format(
                        test, index)
                else:
                    test_groups = [t['custom_test_group'] for t in self.tests
                                   if t['id'] == test] or [None]
                    stats += '[{0}]'.format(test_groups[0])
                index += 1
            if html:
                stats += '</br>\n'
            else:
                stats += '\n'
        if html:
            stats += '</html>\n'
        else:
            stats += '======================================================='
        return stats

    def publish(self):
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Generate statistics for bugs linked to TestRun. Publish "
                    "statistics to testrail if necessary."
    )
    parser.add_argument('run_id', type=int, help='Test run ID in TestRail')
    parser.add_argument('-b', '--handle-blocked', action="store_true",
                        dest='handle_blocked', default=False,
                        help='Copy bugs links to downstream blocked results')
    parser.add_argument('-p', '--publish', action="store_true",
                        help='Publish statistics to TestPlan description')
    parser.add_argument('-o', '--out-file', dest='output_file',
                        default=None, type=str,
                        help='Path to file to save statistics as HTML')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug output.")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(DEBUG)

    if args.publish:
        logger.debug('Publisher to TestRail is enabled!')
        # TODO: add publishing to testrail (TestPlan description)

    generator = StatisticsGenerator(args.run_id)
    generator.generate(handle_blocked=args.handle_blocked)

    if args.output_file:
        html = generator.dump(html=True)
        if not os.path.exists(args.output_file):
            logger.debug('File {0} doesn\'t exist! '
                         'Creating...'.format(args.output_file))
        with open(args.output_file, 'w+') as f:
            f.write(html)
    else:
        print generator.dump()

    logger.info('Statistics generation complete!')


if __name__ == "__main__":
    main()
