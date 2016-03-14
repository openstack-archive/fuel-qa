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


from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["cgroup_ha"])
class TestCgroupHa(TestBasic):
    """Tests for verification deployment with enabled cgroup."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_ha_cgroup'])
    @log_snapshot_after_test
    def test_deploy_ha_cgroup(self):
        """Deploy cluster in HA mode with enabled cgroup

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role
            4. Add 1 node with cinder role
            5. Deploy the cluster
            6. Check ceph status
            7. Run OSTF

        Duration 90m
        Snapshot deploy_ha_croup
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'tenant': 'cgroup',
            'user': 'cgroup',
            'password': 'cgroup',
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }

        cgroup_data = {
            'keystone': {
                'type': 'text',
                'value': "{\"cpu\":{\"cpu.shares\":70}}",
                'label': 'keystone'
            }, }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data, cgroup_data=cgroup_data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Check that task cgroup was executed
        cmd = 'fgrep  "MODULAR: cgroups.pp" -q /var/log/puppet.log'
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        for nailgun_node in n_ctrls:
            logger.info('Check cgroups task on controller node {0}'.format(
                nailgun_node))

            self.ssh_manager.check_call(nailgun_node['ip'], cmd)

            check_group_cmd = 'sudo lscgroup | fgrep  -q cpu:/keystone'
            logger.info('Check cpu:/keystone group existence  '
                        'on controller node {0}'.format(nailgun_node))
            self.ssh_manager.check_call(nailgun_node['ip'], check_group_cmd)

        self.env.make_snapshot("deploy_ha_cgroup")
