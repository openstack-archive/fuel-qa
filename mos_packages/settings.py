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


import os

# Default timezone for clear logging
TIME_ZONE = 'UTC'


TEST_PLANS_DIR = os.environ.get('TEST_PLANS_DIR', os.getcwd())
BRANCH_NAME = os.environ.get('BRANCH_NAME', "openstack-ci/fuel-6.1/2014.2")

GERRIT_USER = os.environ.get('GERRIT_USER', "NastyaUrlapova")
GERRIT_HOST = os.environ.get('GERRIT_HOST', "review.fuel-infra.org")
GERRIT_PORT = os.environ.get('GERRIT_PORT', "29418")
GERRIT_URL = os.environ.get('GERRIT_URL', 'ssh://{}@{}:{}'.format(GERRIT_USER,
                                                                  GERRIT_HOST,
                                                                  GERRIT_PORT))

GERRIT_PROJECTS = os.environ.get('GERRIT_PROJECTS', open("/home/alan/gerrit.txt").readlines())
GERRIT_CLONE_DIR = os.environ.get('TEST_PLANS_DIR', "/home/alan/gerrit")
