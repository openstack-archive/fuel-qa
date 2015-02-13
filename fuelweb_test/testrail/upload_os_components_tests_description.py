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
    section = "Other"

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

                if group["tag"] in sections:
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
    nova_functional_cmd = """rm -rf nova && \\
        git clone https://github.com/openstack/nova && \\
        cd nova/nova/tests/functional && egrep -r \"def test\" ./*
    """

    for t in [{"suite": "Tempest", "cmd": tempest_cmd},
              {"suite": "Nova", "cmd": nova_functional_cmd}]:
        p = subprocess.Popen(t["cmd"], shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        for line in iter(p.stdout.readline, b''):
            if 'test' in line:
                groups, section = generate_groups(line)

                if t["suite"] != "Tempest":
                    section = t["suite"]

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


def upload_tests_descriptions(testrail_project, tests):
    for test_case in tests:
        if "Tempest" in test_case["title"]:
            test_suite = "Tempest Tests"
        else:
            test_suite = "OpenStack Components Functional Automated Tests"

        section = testrail_project.get_section_by_name(
            suite=test_suite, section_name=test_case["custom_test_group"])

        testrail_project.add_case(section_id=section["id"], case=test_case)


def main():
    testrail_project = TestRailProject(
        url=TestRailSettings.url,
        user=TestRailSettings.user,
        password=TestRailSettings.password,
        project=TestRailSettings.project
    )

    testrail_milestone = testrail_project.get_milestone(
        name=TestRailSettings.milestone)['id']

    tests_descriptions = get_tests_descriptions(
        milestone_id=testrail_milestone,
        tests_include=TestRailSettings.test_include,
        tests_exclude=TestRailSettings.test_exclude
    )

    upload_tests_descriptions(testrail_project=testrail_project,
                              tests=tests_descriptions)


if __name__ == '__main__':
    main()
