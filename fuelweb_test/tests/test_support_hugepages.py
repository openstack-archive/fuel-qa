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

from proboscis import asserts
from proboscis import SkipTest
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["support_hugepages"])
class SupportHugepages(TestBasic):
    """SupportHugepages."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["basic_env_for_hugepages"])
    @log_snapshot_after_test
    def basic_env_for_hugepages(self):
        """Basic environment for hugepages

        Scenario:
            1. Create cluster
            2. Add 3 node with compute role
            3. Add 1 nodes with controller role
            4. Check what type of HugePages do support 2M and 1GB
            5. Verify the same HP size is present in CLI
            6. Download attributes for computes

        Snapshot: basic_env_for_hugepages

        """
        snapshot_name = 'basic_env_for_hugepages'
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE,
            }
        )
        self.show_step(2)
        self.show_step(3)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute'],
                'slave-02': ['compute'],
                'slave-03': ['compute'],
                'slave-04': ['controller']
            })

        self.show_step(4)
        flag = False
        with self.env.d_env.get_admin_remote() as remote:
            log_path = '/proc/cpuinfo'
            cmd1 = "grep \"pse\" {0}".format(log_path)
            cmd2 = "grep \"pdpe1gb\" {0}".format(log_path)
            result1 = remote.execute(cmd1)
            result2 = remote.execute(cmd2)
            if result1['exit_code'] != 0 and result2['exit_code'] != 0:
                flag = True

        asserts.assert_true(flag, 'HugePages do support 2M and 1GB')

        self.show_step(5)
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        for compt in computes:
            flag = False
            with self.env.d_env.get_admin_remote() as remote:
                cmd = "fuel2 node show {0} | grep huge".format(compt['id'])
                result = remote.execute(cmd)
                if result['exit_code'] != 0:
                    flag = True
            asserts.assert_true(flag, 'HP size is present in CLI')

        self.show_step(6)
        for compt in computes:
            with self.env.d_env.get_admin_remote() as remote:
                cmd = "cat /root/node_{0}/attributes.yaml".format(compt['id'])
                result = remote.execute(cmd)
                logger.info(result, "result attributes")
                self.fuel_web.client.get_node_attributes(compt['id'])

        self.env.make_snapshot("basic_env_for_hugepages", is_make=True)
