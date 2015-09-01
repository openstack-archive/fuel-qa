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

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.tests_strength.test_failover_base\
    import TestHaFailoverBase


@test(groups=["ha_destructive_ceph_neutron"])
class TestHaCephNeutronFailover(TestHaFailoverBase):
    snapshot_name = "prepare_ha_ceph_neutron"

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ceph_ha", "prepare_ha_ceph_neutron"])
    @log_snapshot_after_test
    def prepare_ha_ceph_neutron(self):
        """Prepare cluster in HA/Neutron mode with ceph for failover tests

        Scenario:
            1. Create cluster
            2. Add 2 nodes with controller roles, 1 node controller + ceph-osd
            3. Add 1 node with compute role, 1 node compute + ceph-osd
            4. Deploy the cluster
            5. Make snapshot

        Duration 70m
        Snapshot prepare_ha_ceph_neutron
        """
        super(self.__class__, self).deploy_ha_ceph()

    @test(depends_on_groups=['prepare_ha_ceph_neutron'],
          groups=["ha_ceph_neutron_sequential_destroy_controllers"])
    @log_snapshot_after_test
    def ha_ceph_neutron_rabbit_master_destroy(self):
        """Suspend rabbit master, check neutron cluster,
         resume nodes, check cluster

        Scenario:
            1. Revert snapshot prepare_ha_ceph_neutron
            2. Wait galera is up, keystone re-trigger tokens
            3. Create instance, assign floating ip
            5. Ping instance by floating ip
            6. Suspend rabbit-master controller
            7. Run OSTF ha suite
            8. Ping created instance
            9. Suspend second rabbit-master controller
            10. Turn on controller from step 6
            11. Run OSTF ha suite
            12. Ping instance
            13. Turn on controller from step 9
            14. Run OSTF ha suite
            15. Ping instance
            16. Run OSTF

        Duration 40m
        """
        super(self.__class__, self).ha_sequential_rabbit_master_failover()
