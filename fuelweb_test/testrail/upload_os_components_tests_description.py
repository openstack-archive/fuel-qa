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
from joblib import Parallel, delayed
from settings import TestRailSettings
from testrail_client import TestRailProject


def generate_groups(line):
    groups = []
    sections = ["Nova", "Glance", "Heat", "Sahara", "Ceilometer", "Cinder",
                "Network", "Keystone", "Swift"]
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
                  {"names": ["volume", ], "tag": "Cinder"},
                  {"names": ["object_storage", ], "tag": "Swift"}]:
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

    return section


def get_tests_descriptions(milestone_id, tests_include, tests_exclude):
    tests = []
    tempest_cmd = """rm -rf tempest && \\
        git clone https://github.com/openstack/tempest && \\
        cd tempest/tempest && egrep -r \"def test\" ./*
    """
    tempest_cmd = """cd tempest && .tox/venv/bin/nosetests --collect-only \\
        tempest/api tempest/cli tempest/scenario tempest/thirdparty -v 2>&1 \\
        | grep 'id-.*'"""

    for t in [{"suite": "Tempest", "cmd": tempest_cmd}, ]:
        p = subprocess.Popen(t["cmd"], shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

        for line in iter(p.stdout.readline, b''):
            if 'id-' in line:
                section = generate_groups(line)

                for r in line.split("."):
                    if "id-" in r:
                        title = r.strip()

                steps = [{"run this tempest test": "passed"}, ]
                test_case = {
                    "title": title,
                    "type_id": 1,
                    "priority_id": 5,
                    "estimate": "1m",
                    "refs": "",
                    "milestone_id": milestone_id,
                    "custom_test_group": title,
                    "custom_test_case_description": title,
                    "custom_test_case_steps": steps,
                    "section": section
                }
                tests.append(test_case)
    return tests


def delete_case(testrail_project, test_id):
    testrail_project.delete_case(test_id)


def add_case(testrail_project, test_suite, test_case):
    suite = testrail_project.get_suite_by_name(test_suite)
    section = testrail_project.get_section_by_name(
        suite_id=suite['id'], section_name=test_case["section"])
    testrail_project.add_case(section_id=section["id"], case=test_case)


def upload_tests_descriptions(testrail_project, tests):
    test_suite = "Tempest {0}".format(TestRailSettings.milestone)
    suite = testrail_project.get_suite_by_name(test_suite)

    old_tests = testrail_project.get_cases(suite_id=suite['id'])
    Parallel(n_jobs=100)(delayed(delete_case)
                         (testrail_project, test['id']) for test in old_tests)

    Parallel(n_jobs=100)(delayed(add_case)
                         (testrail_project, test_suite, test_case)
                         for test_case in tests)


def main():
    testrail_project = TestRailProject(
        url=TestRailSettings.url,
        user=TestRailSettings.user,
        password=TestRailSettings.password,
        project=TestRailSettings.project
    )

    testrail_milestone = testrail_project.get_milestone_by_name(
        name=TestRailSettings.milestone)

    tests_descriptions = get_tests_descriptions(
        milestone_id=testrail_milestone['id'],
        tests_include=TestRailSettings.tests_include,
        tests_exclude=TestRailSettings.tests_exclude
    )

    upload_tests_descriptions(testrail_project=testrail_project,
                              tests=tests_descriptions)


if __name__ == '__main__':
    main()
