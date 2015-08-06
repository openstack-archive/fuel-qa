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

from proboscis import test
from proboscis import asserts

from fuelweb_test import logger
from fuelweb_test import settings as CONF
from fuelweb_test.helpers import decorators
from fuelweb_test.tests import base_test_case


@test(groups=["rally"])
class BaseRallyTest(base_test_case.TestBasic):
    def __init__(self):
        super(BaseRallyTest, self).__init__()

    def pull_image(self, container_repo):
        cmd = 'docker pull {0}'.format(container_repo)
        logger.debug('Downloading Rally repository/image from registry')
        result = self.admin_remote.execute(cmd)
        logger.debug(result)

    def run_container(self, image_name, image_tag="latest", env_vars=None):
        options = ""
        if env_vars is not None:
            for var, value in env_vars.items():
                options += "-e {0}={1}".format(var, value)

        cmd = ("docker run -d {env_vars} "
               "-p 0.0.0.0:20000:8001 "
               "{image_name}:{tag}"
               .format(env_vars=options,
                       image_name=image_name,
                       tag=image_tag))
        logger.debug('Running Rally container {0}'.format(image_name))
        result = self.admin_remote.execute(cmd)
        logger.debug(result)
        return result

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=['prepare_rally_environment'])
    @decorators.log_snapshot_after_test
    def prepare_rally_environment(self):
        """Title

        Scenario:
        1.

        Duration: 10m
        Snapshot: ready_rally
        """
        self.check_run("ready_rally")
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        if CONF.REPLACE_DEFAULT_REPOS:
            self.fuel_web.replace_default_repos()

        self.pull_image("dkalashnik/rallyd")
        self.run_container("rallyd")

        self.env.make_snapshot("ready_rally", is_make=True)

    @test(depends_on=[prepare_rally_environment],
          groups=["prepare_rally_slaves_3"])
    @decorators.log_snapshot_after_test
    def prepare_rally_slaves_3(self):
        """Bootstrap 3 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 3 slave nodes

        Snapshot: ready_rally_with_3_slaves

        """
        self.check_run("ready_rally_with_3_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_rally_with_3_slaves", is_make=True)

    @test(depends_on=[prepare_rally_environment],
          groups=["prepare_rally_slaves_3"])
    @decorators.log_snapshot_after_test
    def prepare_rally_slaves_5(self):
        """Bootstrap 5 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 5 slave nodes

        Snapshot: ready_rally_with_5_slaves

        """
        self.check_run("ready_rally_with_5_slaves")
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:5],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_rally_with_5_slaves", is_make=True)
