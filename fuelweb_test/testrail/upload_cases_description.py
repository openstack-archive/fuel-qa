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

import re

from logging import DEBUG
from optparse import OptionParser
from proboscis import TestProgram

from builds import Build
from fuelweb_test.run_tests import import_tests
from settings import GROUPS_TO_EXPAND
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject


def get_tests_descriptions(milestone_id, tests_include, tests_exclude, groups,
                           default_test_priority):
    import_tests()

    tests = []

    for group in groups:
        for case in TestProgram(groups=[group]).cases:
            if not case.entry.info.enabled:
                continue
            if tests_include:
                if tests_include not in case.entry.home.func_name:
                    logger.debug("Skipping '{0}' test because it doesn't "
                                 "contain '{1}' in method name"
                                 .format(case.entry.home.func_name,
                                         tests_include))
                    continue
            if tests_exclude:
                if tests_exclude in case.entry.home.func_name:
                    logger.debug("Skipping '{0}' test because it contains"
                                 " '{1}' in method name"
                                 .format(case.entry.home.func_name,
                                         tests_exclude))
                    continue

            docstring = case.entry.home.func_doc or ''
            docstring = '\n'.join([s.strip() for s in docstring.split('\n')])

            steps = [{"content": s, "expected": "pass"} for s in
                     docstring.split('\n') if s and s[0].isdigit()]

            test_duration = re.search(r'Duration\s+(\d+[s,m])\b', docstring)
            title = docstring.split('\n')[0] or case.entry.home.func_name
            test_group = case.entry.home.func_name

            if case.entry.home.func_name in GROUPS_TO_EXPAND:
                """Expand specified test names with the group names that are
                   used in jenkins jobs where this test is started.
                """
                title = ' - '.join([title, group])
                test_group = '_'.join([case.entry.home.func_name, group])

            test_case = {
                "title": title,
                "type_id": 1,
                "milestone_id": milestone_id,
                "priority_id": default_test_priority,
                "estimate": test_duration.group(1) if test_duration else "3m",
                "refs": "",
                "custom_test_group": test_group,
                "custom_test_case_description": docstring or " ",
                "custom_test_case_steps": steps
            }

            if not any([x['custom_test_group'] == test_group for x in tests]):
                tests.append(test_case)
            else:
                logger.warning("Testcase '{0}' run in multiple Jenkins jobs!"
                               .format(test_group))
    return tests


def upload_tests_descriptions(testrail_project, section_id,
                              tests, check_all_sections):
    tests_suite = testrail_project.get_suite_by_name(
        TestRailSettings.tests_suite)
    check_section = None if check_all_sections else section_id
    existing_cases = [case['custom_test_group'] for case in
                      testrail_project.get_cases(suite_id=tests_suite['id'],
                                                 section_id=check_section)]
    for test_case in tests:
        if test_case['custom_test_group'] in existing_cases:
            logger.debug('Skipping uploading "{0}" test case because it '
                         'already exists in "{1}" tests section.'.format(
                             test_case['custom_test_group'],
                             TestRailSettings.tests_suite))
            continue

        logger.debug('Uploading test "{0}" to TestRail project "{1}", '
                     'suite "{2}", section "{3}"'.format(
                         test_case["custom_test_group"],
                         TestRailSettings.project,
                         TestRailSettings.tests_suite,
                         TestRailSettings.tests_section))
        testrail_project.add_case(section_id=section_id, case=test_case)


def get_tests_groups_from_jenkins(runner_name, build_number, distros):
    runner_build = Build(runner_name, build_number)
    res = []
    for b in runner_build.build_data['subBuilds']:
        job_name = b['jobName']
        for distro in distros:
            if distro in job_name:
                sep = '.' + distro + '.'
                res.append(job_name.split(sep)[-1])
                break
        else:
            res.append(job_name.split('.')[-1])
    return res


def main():
    parser = OptionParser(
        description="Upload tests cases to TestRail. "
                    "See settings.py for configuration."
    )
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")
    parser.add_option('-j', '--job-name', dest='job_name', default=None,
                      help='Jenkins swarm runner job name')
    parser.add_option('-N', '--build-number', dest='build_number',
                      default='latest',
                      help='Jenkins swarm runner build number')
    parser.add_option('-o', '--check_one_section', action="store_true",
                      dest='check_one_section', default=False,
                      help='Look for existing test case only in specified '
                           'section of test suite.')

    (options, args) = parser.parse_args()

    if options.verbose:
        logger.setLevel(DEBUG)

    project = TestRailProject(
        url=TestRailSettings.url,
        user=TestRailSettings.user,
        password=TestRailSettings.password,
        project=TestRailSettings.project
    )

    testrail_section = project.get_section_by_name(
        suite_id=project.get_suite_by_name(TestRailSettings.tests_suite)['id'],
        section_name=TestRailSettings.tests_section
    )

    testrail_milestone = project.get_milestone_by_name(
        name=TestRailSettings.milestone)

    testrail_default_test_priority = [priority['id'] for priority in
                                      project.get_priorities() if
                                      priority['is_default'] is True][0]

    distros = [config['name'].split()[0].lower()
               for config in project.get_config_by_name(
                   'Operation System')['configs']
               if config['name'] in TestRailSettings.operation_systems]

    tests_groups = get_tests_groups_from_jenkins(
        options.job_name,
        options.build_number,
        distros) if options.job_name else []

    # If Jenkins job build is specified, but it doesn't have downstream builds
    # with tests groups in jobs names, then skip tests cases uploading because
    # ALL existing tests cases will be uploaded
    if options.job_name and not tests_groups:
        return

    tests_descriptions = get_tests_descriptions(
        milestone_id=testrail_milestone['id'],
        tests_include=TestRailSettings.tests_include,
        tests_exclude=TestRailSettings.tests_exclude,
        groups=tests_groups,
        default_test_priority=testrail_default_test_priority
    )

    upload_tests_descriptions(testrail_project=project,
                              section_id=testrail_section['id'],
                              tests=tests_descriptions,
                              check_all_sections=not options.check_one_section)

if __name__ == '__main__':
    main()
