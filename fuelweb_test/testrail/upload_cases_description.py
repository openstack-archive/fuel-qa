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

import re
import string

from logging import DEBUG
from optparse import OptionParser
from proboscis import TestPlan
from proboscis.decorators import DEFAULT_REGISTRY

from fuelweb_test.testrail.builds import Build
from fuelweb_test.testrail.settings import GROUPS_TO_EXPAND
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject
from fuelweb_test.testrail import datetime_util
from system_test import define_custom_groups
from system_test import discover_import_tests
from system_test import register_system_test_cases
from system_test import tests_directory
from system_test import get_basepath
from system_test.tests.base import ActionTest


GROUP_FIELD = 'custom_test_group'

STEP_NUM_PATTERN = re.compile(r'^(\d{1,3})[.].+')
DURATION_PATTERN = re.compile(r'Duration:?\s+(\d+(?:[sm]|\s?m))(?:in)?\b')
TEST_GROUP_PATTERN = re.compile(r'run_system_test.py\s+.*--group=(\S+)\b')


def get_tests_descriptions(milestone_id, tests_include, tests_exclude, groups,
                           default_test_priority):
    plan = _create_test_plan_from_registry(groups=groups)
    all_plan_tests = plan.tests[:]

    tests = []

    for jenkins_suffix in groups:
        group = groups[jenkins_suffix]
        plan.filter(group_names=[group])
        for case in plan.tests:
            if not _is_case_processable(case=case, tests=tests):
                continue

            case_name = test_group = _get_test_case_name(case)

            if _is_not_included(case_name, tests_include) or \
                    _is_excluded(case_name, tests_exclude):
                continue

            docstring = _get_docstring(parent_home=case.entry.parent.home,
                                       case_state=case.state,
                                       home=case.entry.home)

            title, steps, duration = _parse_docstring(docstring, case)

            if case.entry.home.func_name in GROUPS_TO_EXPAND:
                """Expand specified test names with the group names that are
                   used in jenkins jobs where this test is started.
                """
                title = ' - '.join([title, jenkins_suffix])
                test_group = '_'.join([case.entry.home.func_name,
                                       jenkins_suffix])
            elif TestRailSettings.extra_factor_of_tc_definition:
                title = '{} - {}'.format(
                    title,
                    TestRailSettings.extra_factor_of_tc_definition
                )
                test_group = '{}_{}'.format(
                    test_group,
                    TestRailSettings.extra_factor_of_tc_definition
                )

            test_case = {
                "title": title,
                "type_id": 1,
                "milestone_id": milestone_id,
                "priority_id": default_test_priority,
                "estimate": duration,
                "refs": "",
                "custom_test_group": test_group,
                "custom_test_case_description": docstring or " ",
                "custom_test_case_steps": steps
            }

            if not any([x[GROUP_FIELD] == test_group for x in tests]):
                tests.append(test_case)
            else:
                logger.warning("Testcase '{0}' run in multiple Jenkins jobs!"
                               .format(test_group))

        plan.tests = all_plan_tests[:]

    return tests


def upload_tests_descriptions(testrail_project, section_id,
                              tests, check_all_sections):
    tests_suite = testrail_project.get_suite_by_name(
        TestRailSettings.tests_suite)
    check_section = None if check_all_sections else section_id
    cases = testrail_project.get_cases(suite_id=tests_suite['id'],
                                       section_id=check_section)
    existing_cases = [case[GROUP_FIELD] for case in cases]
    custom_cases_fields = _get_custom_cases_fields(
        case_fields=testrail_project.get_case_fields(),
        project_id=testrail_project.project['id'])

    for test_case in tests:
        if test_case[GROUP_FIELD] in existing_cases:
            testrail_case = _get_testrail_case(testrail_cases=cases,
                                               test_case=test_case,
                                               group_field=GROUP_FIELD)
            fields_to_update = _get_fields_to_update(test_case, testrail_case)

            if fields_to_update:
                logger.debug('Updating test "{0}" in TestRail project "{1}", '
                             'suite "{2}", section "{3}". Updated fields: {4}'
                             .format(
                                 test_case[GROUP_FIELD],
                                 TestRailSettings.project,
                                 TestRailSettings.tests_suite,
                                 TestRailSettings.tests_section,
                                 ', '.join(fields_to_update.keys())))
                testrail_project.update_case(case_id=testrail_case['id'],
                                             fields=fields_to_update)
            else:
                logger.debug('Skipping "{0}" test case uploading because '
                             'it is up-to-date in "{1}" suite'
                             .format(test_case[GROUP_FIELD],
                                     TestRailSettings.tests_suite))

        else:
            for case_field, default_value in custom_cases_fields.items():
                if case_field not in test_case:
                    test_case[case_field] = default_value

            logger.debug('Uploading test "{0}" to TestRail project "{1}", '
                         'suite "{2}", section "{3}"'.format(
                             test_case[GROUP_FIELD],
                             TestRailSettings.project,
                             TestRailSettings.tests_suite,
                             TestRailSettings.tests_section))
            testrail_project.add_case(section_id=section_id, case=test_case)


def get_tests_groups_from_jenkins(runner_name, build_number, distros):
    runner_build = Build(runner_name, build_number)
    res = {}
    for b in runner_build.build_data['subBuilds']:

        if b['result'] is None:
            logger.debug("Skipping '{0}' job (build #{1}) because it's still "
                         "running...".format(b['jobName'], b['buildNumber'],))
            continue

        # Get the test group from the console of the job
        z = Build(b['jobName'], b['buildNumber'])
        console = z.get_job_console()
        groups = re.findall(TEST_GROUP_PATTERN, console)

        if not groups:
            # maybe it's failed baremetal job?
            # because of a design baremetal tests run pre-setup job
            # and when it fails there are no test groups in common meaning:
            # groups which could be parsed by TEST_GROUP_PATTERN
            baremetal_pattern = re.compile(r'Jenkins Build.*jenkins-(.*)-\d+')
            baremetal_groups = re.findall(baremetal_pattern, console)
            if not baremetal_groups:
                logger.error(
                    "No test group found in console of the job {0}/{1}".format
                    (b['jobName'], b['buildNumber']))
                continue
            # we should get the group via jobName because the test group name
            # inside the log could be cut and some symbols will be changed to *
            groups = b['jobName'].split('.')
        # Use the last group (there can be several groups in upgrade jobs)
        test_group = groups[-1]

        # Get the job suffix
        job_name = b['jobName']
        for distro in distros:
            if distro in job_name:
                sep = '.' + distro + '.'
                job_suffix = job_name.split(sep)[-1]
                break
        else:
            job_suffix = job_name.split('.')[-1]
        res[job_suffix] = test_group
    return res


def _create_test_plan_from_registry(groups):
    discover_import_tests(get_basepath(), tests_directory)
    define_custom_groups()
    for one in groups:
        register_system_test_cases(one)
    return TestPlan.create_from_registry(DEFAULT_REGISTRY)


def _is_case_processable(case, tests):
    if not case.entry.info.enabled or not hasattr(case.entry, 'parent'):
        return False

    parent_home = case.entry.parent.home
    if issubclass(parent_home, ActionTest) and \
            any([test[GROUP_FIELD] == parent_home.__name__ for test in tests]):
        return False

    # Skip @before_class methods without doc strings:
    # they are just pre-checks, not separate tests cases
    if case.entry.info.before_class:
        if case.entry.home.func_doc is None:
            logger.debug('Skipping method "{0}", because it is not a '
                         'test case'.format(case.entry.home.func_name))
            return False

    return True


def _get_test_case_name(case):
    """Returns test case name
    """
    parent_home = case.entry.parent.home
    return parent_home.__name__ if issubclass(parent_home, ActionTest) \
        else case.entry.home.func_name


def _is_not_included(case_name, include):
    if include and include not in case_name:
        logger.debug("Skipping '{0}' test because it doesn't "
                     "contain '{1}' in method name".format(case_name, include))
        return True
    else:
        return False


def _is_excluded(case_name, exclude):
    if exclude and exclude in case_name:
        logger.debug("Skipping '{0}' test because it contains"
                     " '{1}' in method name".format(case_name, exclude))
        return True
    else:
        return False


def _get_docstring(parent_home, case_state, home):
    if issubclass(parent_home, ActionTest):
        docstring = parent_home.__doc__.split('\n')
        case_state.instance._load_config()
        configuration = case_state.instance.config_name
        docstring[0] = '{0} on {1}'.format(docstring[0], configuration)
        docstring = '\n'.join(docstring)
    else:
        docstring = home.func_doc or ''
    return docstring


def _parse_docstring(s, case):
    split_s = s.strip().split('\n\n')
    title_r, steps_r, duration_r = _unpack_docstring(split_s)
    title = _parse_title(title_r, case) if title_r else ''
    steps = _parse_steps(steps_r) if steps_r else ''
    duration = _parse_duration(duration_r)
    return title, steps, duration


def _unpack_docstring(items):
    count = len(items)
    title = steps = duration = ''
    if count > 3:
        title, steps, duration, _ = _unpack_list(*items)
    elif count == 3:
        title, steps, duration = items
    elif count == 2:
        title, steps = items
    elif count == 1:
        title = items[0]
    return title, steps, duration


def _unpack_list(title, steps, duration, *other):
    return title, steps, duration, other


def _parse_title(s, case):
    title = ' '.join(map(string.strip, s.split('\n')))
    return title if title else case.entry.home.func_name


def _parse_steps(strings):
    steps = []
    index = -1
    for s_raw in strings.strip().split('\n'):
        s = s_raw.strip()
        _match = STEP_NUM_PATTERN.search(s)
        if _match:
            steps.append({'content': _match.group(), 'expected': 'pass'})
            index += 1
        else:
            if index > -1:
                steps[index]['content'] = ' '.join([steps[index]['content'],
                                                    s])
    return steps


def _parse_duration(s):
    match = DURATION_PATTERN.search(s)
    return match.group(1).replace(' ', '') if match else '3m'


def _get_custom_cases_fields(case_fields, project_id):
    custom_cases_fields = {}
    for field in case_fields:
        for config in field['configs']:
            if ((project_id in
                    config['context']['project_ids'] or
                    not config['context']['project_ids']) and
                    config['options']['is_required']):
                try:
                    custom_cases_fields[field['system_name']] = \
                        int(config['options']['items'].split(',')[0])
                except:
                    logger.error("Couldn't find default value for required "
                                 "field '{0}', setting '1' (index)!".format(
                                     field['system_name']))
                    custom_cases_fields[field['system_name']] = 1
    return custom_cases_fields


def _get_fields_to_update(test_case, testrail_case):
    """Produces dictionary with fields to be updated
    """
    fields_to_update = {}
    for field in ('title', 'estimate', 'custom_test_case_description',
                  'custom_test_case_steps'):
        if test_case[field] and \
                test_case[field] != testrail_case[field]:
            if field == 'estimate':
                testcase_estimate_raw = int(test_case[field][:-1])
                testcase_estimate = \
                    datetime_util.duration_to_testrail_estimate(
                        testcase_estimate_raw)
                if testrail_case[field] == testcase_estimate:
                    continue
            elif field == 'custom_test_case_description' and \
                    test_case[field] == testrail_case[field].replace('\r', ''):
                continue
            fields_to_update[field] = test_case[field]
    return fields_to_update


def _get_testrail_case(testrail_cases, test_case, group_field):
    """Returns testrail case that corresponds to test case from repo
    """
    return next((case for case in testrail_cases
                 if case[group_field] == test_case[group_field]))


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
    parser.add_option("-l", "--live", dest="live_upload", action="store_true",
                      help="Get tests results from running swarm")

    (options, _) = parser.parse_args()

    if options.verbose:
        logger.setLevel(DEBUG)

    if options.live_upload and options.build_number == 'latest':
        options.build_number = 'latest_started'

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
