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

import subprocess
from settings import logger
from settings import TestRailSettings
from testrail_client import TestRailProject


def generate_groups(line):
    groups = []
    sections = ["Nova", "Glance", "Heat", "Sahara", "Ceilometer", "Cinder",
                "Network", "Keystone"]
    section = "Others"

    for group in [{"names": ["compute", ], "tag": "Nova"},
                  {"names": ["image", ], "tag": "Glance"},
                  {"names": ["orchestration", ], "tag": "Heat"},
                  {"names": ["baremetal", ], "tag": "Ironic"},
                  {"names": ["data_processing", ], "tag": "Sahara"},
                  {"names": ["identity", "tenant", "auth", "account",
                             "credentials"],
                   "tag": "Keystone"},
                  {"names": ["telemetry", ], "tag": "Ceilometer"},
                  {"names": ["volume", ], "tag": "Cinder"}]:
        for name in group["names"]:
            if name in line:
                groups.append(group["tag"])

                if name in sections:
                    section = group["tag"]

    for group in ["Heat", "Database", "Messaging", "Network", "Object_storage",
                  "Scenario", "Stress", "Boto", "Cli", "Negative", "Ssh",
                  "Rest_client", "Remote_client", "Linux"]:
        if group.lower() in line:
            groups.append(group)

            if group in sections:
                section = group

    return groups, section


def get_tests_descriptions(milestone_id, tests_include, tests_exclude):
    tests = []
    tempest_cmd = """rm -rf tempest && \\
                     git clone https://github.com/openstack/tempest && \\
                     cd tempest/tempest && egrep -r \"def test\" ./*
                  """

    for t in [{"suite": "Tempest", "cmd": tempest_cmd}, ]:
        p = subprocess.Popen(t["cmd"], shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        for line in iter(p.stdout.readline, b''):
            if 'test' in line:
                groups, section = generate_groups(line)

                # just for debug, let's use this check to find all tests
                # without category
                if len(groups) == 0:
                    print line

                title = line.replace(" def ", "", 5)
                title = title.replace(".py: ", ":", 5)
                title = "".join(title.split()).split('(')[0].split(':')[1]
                title = title.replace(" ", "")
                title = title.replace(".", "")

                title = title.replace("/", "_")

                steps = [{"run this tempest test": "pass"}, ]
                tc_title = "[%s] " % t["suite"]
                for group in groups:
                    tc_title = tc_title + "[" + group + "] "

                test_case = {
                    "title": tc_title + title,
                    "type_id": 1,
                    "priority_id": 5,
                    "estimate": "1m",
                    "refs": "",
                    "custom_test_group": section,
                    "custom_test_case_description": title.replace("_", " "),
                    "custom_test_case_steps": steps
                }
                tests.append(test_case)
    return tests


def upload_tests_descriptions(testrail_project, section_id, tests):
    existing_cases = [case['title'] for case in
                      testrail_project.get_cases(TestRailSettings.test_suite,
                                                 section_id=section_id)]

    print "TESTS COUNT: ", len(tests)
    for test_case in tests:
        if test_case['title'] in existing_cases:
            logger.debug('Skipping uploading "{0}" test case because it '
                         'already exists in "{1}" tests section.'.format(
                             test_case['custom_test_group'],
                             TestRailSettings.test_suite))
            continue

        logger.debug('Uploading test "{0}" to TestRail project "{1}", '
                     'suite "{2}", section "{3}"'.format(
                         test_case["custom_test_group"],
                         TestRailSettings.project,
                         TestRailSettings.test_suite,
                         TestRailSettings.test_section))

        section = testrail_project.get_section_by_name(
            suite=TestRailSettings.test_suite,
            section_name=test_case["custom_test_group"])

        testrail_project.add_case(section_id=section.id, case=test_case)


def main():
    testrail_project = TestRailProject(
        url=TestRailSettings.url,
        user=TestRailSettings.user,
        password=TestRailSettings.password,
        project=TestRailSettings.project
    )

    testrail_section = testrail_project.get_section_by_name(
        suite=TestRailSettings.test_suite,
        section_name=TestRailSettings.test_section
    )

    testrail_milestone = testrail_project.get_milestone(
        name=TestRailSettings.milestone)['id']

    tests_descriptions = get_tests_descriptions(
        milestone_id=testrail_milestone,
        tests_include=TestRailSettings.test_include,
        tests_exclude=TestRailSettings.test_exclude
    )

    upload_tests_descriptions(testrail_project=testrail_project,
                              section_id=testrail_section['id'],
                              tests=tests_descriptions)


if __name__ == '__main__':
    main()
