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
from proboscis import TestPlan
from proboscis.decorators import DEFAULT_REGISTRY

from builds import Build
from fuelweb_test.run_tests import import_tests
from fuelweb_test.run_tests import define_custom_groups
from settings import GROUPS_TO_EXPAND
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject


def get_tests_descriptions(milestone_id, tests_include, tests_exclude, groups,
                           default_test_priority):
    from system_test.tests.actions_base import ActionsBase
    import_tests()
    define_custom_groups()
    plan = TestPlan.create_from_registry(DEFAULT_REGISTRY)
    all_plan_tests = plan.tests[:]

    tests = []

    for jenkins_suffix in groups:
        group = groups[jenkins_suffix]
        plan.filter(group_names=[group])
        for case in plan.tests:
            if not case.entry.info.enabled:
                continue
            home = case.entry.home
            if not hasattr(case.entry, 'parent'):
                # Not a real case, some stuff needed by template based tests
                continue
            parent_home = case.entry.parent.home
            case_state = case.state
            if issubclass(parent_home, ActionsBase):
                case_name = parent_home.__name__
                test_group = parent_home.__name__
                if any([x['custom_test_group'] == test_group for x in tests]):
                    continue
            else:
                case_name = home.func_name
                test_group = case.entry.home.func_name
            if tests_include:
                if tests_include not in case_name:
                    logger.debug("Skipping '{0}' test because it doesn't "
                                 "contain '{1}' in method name"
                                 .format(case_name,
                                         tests_include))
                    continue
            if tests_exclude:
                if tests_exclude in case_name:
                    logger.debug("Skipping '{0}' test because it contains"
                                 " '{1}' in method name"
                                 .format(case_name,
                                         tests_exclude))
                    continue

            if issubclass(parent_home, ActionsBase):
                docstring = parent_home.__doc__.split('\n')
                case_state.instance._load_config()
                configuration = case_state.instance.config_name
                docstring[0] = "{0} on {1}".format(docstring[0], configuration)
                docstring = '\n'.join(docstring)
            else:
                docstring = home.func_doc or ''
                configuration = None
            docstring = '\n'.join([s.strip() for s in docstring.split('\n')])

            steps = [{"content": s, "expected": "pass"} for s in
                     docstring.split('\n') if s and s[0].isdigit()]

            test_duration = re.search(r'Duration\s+(\d+[s,m])\b', docstring)
            title = docstring.split('\n')[0] or case.entry.home.func_name

            if case.entry.home.func_name in GROUPS_TO_EXPAND:
                """Expand specified test names with the group names that are
                   used in jenkins jobs where this test is started.
                """
                title = ' - '.join([title, jenkins_suffix])
                test_group = '_'.join([case.entry.home.func_name,
                                       jenkins_suffix])

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

        plan.tests = all_plan_tests[:]

    return tests


def upload_tests_descriptions(testrail_project, section_id,
                              tests, check_all_sections):
    tests_suite = testrail_project.get_suite_by_name(
        TestRailSettings.tests_suite)
    check_section = None if check_all_sections else section_id
    existing_cases = [case['custom_test_group'] for case in
                      testrail_project.get_cases(suite_id=tests_suite['id'],
                                                 section_id=check_section)]
    custom_cases_fields = {}
    for field in testrail_project.get_case_fields():
        for config in field['configs']:
            if ((testrail_project.project['id'] in
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

    for test_case in tests:
        if test_case['custom_test_group'] in existing_cases:
            logger.debug('Skipping uploading "{0}" test case because it '
                         'already exists in "{1}" tests section.'.format(
                             test_case['custom_test_group'],
                             TestRailSettings.tests_suite))
            continue

        for case_field, default_value in custom_cases_fields.items():
            if case_field not in test_case:
                test_case[case_field] = default_value

        logger.debug('Uploading test "{0}" to TestRail project "{1}", '
                     'suite "{2}", section "{3}"'.format(
                         test_case["custom_test_group"],
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
        groups = [keyword.split('=')[1]
                  for line in console
                  for keyword in line.split()
                  if 'run_tests.py' in line and '--group=' in keyword]
        if not groups:
            logger.error("No test group found in console of the job {0}/{1}"
                         .format(b['jobName'], b['buildNumber']))
            continue
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
