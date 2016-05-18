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

from logging import DEBUG
import subprocess
from optparse import OptionParser
from joblib import Parallel, delayed

from fuelweb_test.helpers.decorators import retry
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.upload_cases_description \
    import _get_custom_cases_fields


TEST_GROUPS = ["API", "CLI", "Scenario", "ThirdParty"]
TEST_SECTIONS = ["Ceilometer", "Cinder", "Glance", "Heat", "Ironic",
                 "Keystone", "Network", "Nova", "Sahara", "Swift", "Other"]


def generate_groups(line):
    section = "Other"

    for group in [{"names": [".telemetry.", ], "tag": "Ceilometer"},
                  {"names": [".volume.", ], "tag": "Cinder"},
                  {"names": [".image.", ], "tag": "Glance"},
                  {"names": [".orchestration.", ], "tag": "Heat"},
                  {"names": [".baremetal.", ], "tag": "Ironic"},
                  {"names": [".identity.", ], "tag": "Keystone"},
                  {"names": [".network.", ], "tag": "Network"},
                  {"names": [".compute.", ], "tag": "Nova"},
                  {"names": [".data_processing.", ], "tag": "Sahara"},
                  {"names": [".object_storage.", ], "tag": "Swift"}]:
        for name in group["names"]:
            if name in line:
                section = group["tag"]

    for group in TEST_SECTIONS:
        if group.lower() in line and section == "Other":
            section = group

    return section


def get_tests_descriptions(milestone_id, testrail_default_test_priority,
                           testrail_project):
    # To get the Tempest tests list, need to execute the following commands:
    # git clone https://github.com/openstack/tempest & cd tempest & tox -evenv
    # .tox/venv/bin/pip install nose
    get_tempest_tests = ("cd tempest && .tox/venv/bin/nosetests "
                         "--collect-only tempest/{0} -v 2>&1 | grep 'id-.*'")
    get_commit = "cd tempest && git rev-parse HEAD"
    commit = subprocess.Popen(get_commit, shell=True, stdout=subprocess.PIPE)
    logger.info("Generate test suite for tempest"
                " commit:{}".format(commit.stdout.readline()))
    custom_cases_fields = _get_custom_cases_fields(
        case_fields=testrail_project.get_case_fields(),
        project_id=testrail_project.project['id'])
    tests = {}

    for group in TEST_GROUPS:
        p = subprocess.Popen(get_tempest_tests.format(group.lower()),
                             shell=True, stdout=subprocess.PIPE)

        for line in iter(p.stdout.readline, b''):
            section = generate_groups(line) if group == "API" else group

            test_class = []
            for r in line.split("."):
                if "id-" in r:
                    title = r.strip()
                    break
                else:
                    test_class.append(r)

            steps = [{"run this tempest test": "passed"}, ]

            test_case = {
                "title": title,
                "type_id": 1,
                "milestone_id": milestone_id,
                "priority_id": testrail_default_test_priority,
                "estimate": "1m",
                "refs": "",
                "custom_report_label": title.split('id-')[1][:-1],
                "custom_test_group": ".".join(test_class),
                "custom_test_case_description": title,
                "custom_test_case_steps": steps,
                "section": section
            }
            for case_field, default_value in custom_cases_fields.items():
                if case_field not in test_case:
                    test_case[case_field] = default_value
            if section not in tests:
                tests[section] = []
            tests[section].append(test_case)
    logger.debug(tests)
    logger.info("total test cases: "
                "{}".format(sum(map(lambda x: len(x), tests.values()))))
    return tests


def delete_case(testrail_project, test_id):
    testrail_project.delete_case(test_id)


@retry(3, 60)
def add_case(testrail_project, suite, test_case, section, do_check=False):
    try_msg = "try to add test: {} to section: {}"
    miss_msg = "test: {} is already on section: {}"
    if do_check and testrail_project.get_case_by_name(suite['id'],
                                                      test_case['title']):
        logger.debug(miss_msg.format(test_case["title"], test_case["section"]))
        return
    logger.debug(try_msg.format(test_case["title"], test_case["section"]))
    testrail_project.add_case(section_id=section["id"], case=test_case)


def rewrite_tests_descriptions(testrail_project, tests):
    test_suite = TestRailSettings.tests_suite
    suite = testrail_project.get_suite_by_name(test_suite)

    # remove old sections and test cases
    old_sections = testrail_project.get_sections(suite_id=suite['id'])
    for section in old_sections:
        if section["parent_id"] is None:
            testrail_project.delete_section(section["id"])

    # create new groups
    for group in TEST_GROUPS:
        testrail_project.create_section(suite["id"], group)

    api_group = testrail_project.get_section_by_name(suite["id"], "API")
    for section in TEST_SECTIONS:
        testrail_project.create_section(suite["id"], section, api_group["id"])

    # add test cases to test suite in 100 parallel threads
    logger.info("Add cases")
    for test_section, test_list in tests.iteritems():
        section = testrail_project.get_section_by_name(
            suite_id=suite['id'], section_name=test_section)
        Parallel(n_jobs=100)(delayed(add_case)
                             (testrail_project, suite, test_case, section)
                             for test_case in test_list)


def add_new_tests_description(testrail_project, tests):
    test_suite = TestRailSettings.tests_suite
    suite = testrail_project.get_suite_by_name(test_suite)
    logger.info("Update suite sections")
    for group in TEST_GROUPS:
        if not testrail_project.get_section_by_name(suite["id"], group):
            testrail_project.create_section(suite["id"], group)
    api_group = testrail_project.get_section_by_name(suite["id"], "API")
    for section in TEST_SECTIONS:
        if not testrail_project.get_section_by_name(suite["id"], section):
            testrail_project.create_section(suite["id"], section,
                                            api_group["id"])

    # add test cases to test suite in 100 parallel threads
    logger.info("Add cases")
    for test_section, test_list in tests.iteritems():
        section = testrail_project.get_section_by_name(
            suite_id=suite['id'], section_name=test_section)
        Parallel(n_jobs=100)(delayed(add_case)
                             (testrail_project, suite, test_case,
                              section, True)
                             for test_case in test_list)


def main():

    parser = OptionParser(
        description="Upload tests cases to TestRail. "
                    "See settings.py for configuration."
    )
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Enable debug output")
    parser.add_option("-r", "--rewrite", action="store_true",
                      dest="rewrite", default=False, help="Rewrite all suite")
    parser.add_option("-u", "--update", action="store_true",
                      dest="update", default=False,
                      help="Update new cases to suite")

    (options, _) = parser.parse_args()

    if options.verbose:
        logger.setLevel(DEBUG)

    testrail_project = TestRailProject(
        url=TestRailSettings.url,
        user=TestRailSettings.user,
        password=TestRailSettings.password,
        project=TestRailSettings.project
    )

    testrail_milestone = testrail_project.get_milestone_by_name(
        name=TestRailSettings.milestone)

    testrail_default_test_priority = [priority['id'] for priority in
                                      testrail_project.get_priorities() if
                                      priority['is_default'] is True][0]

    tests_descriptions = get_tests_descriptions(testrail_milestone['id'],
                                                testrail_default_test_priority,
                                                testrail_project)

    if options.rewrite:
        rewrite_tests_descriptions(testrail_project=testrail_project,
                                   tests=tests_descriptions)
    if options.update:
        add_new_tests_description(testrail_project=testrail_project,
                                  tests=tests_descriptions)


if __name__ == '__main__':
    main()
