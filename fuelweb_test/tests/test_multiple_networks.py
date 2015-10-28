#    Copyright 2014 Mirantis, Inc.
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

from proboscis import SkipTest
from proboscis import test

from fuelweb_test.helpers.decorators import check_fuel_statistics
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests.base_test_case import SetupEnvironment


@test(groups=["multiple_cluster_networks", "thread_7"])
class TestMultipleClusterNets(TestBasic):
    """TestMultipleClusterNets."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["multiple_cluster_networks",
                  "deploy_neutron_tun_ha_nodegroups", "thread_7"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_tun_ha_nodegroups(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN and custom nodegroup
            4. Bootstrap slave nodes from custom nodegroup
            5. Add 3 controller nodes from default nodegroup
            6. Add 2 compute nodes from custom nodegroup
            7. Deploy cluster
            8. Run network verification
            9. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_tun_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:5:2])

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlan',
                'user': 'haVxlan',
                'password': 'haVxlan'
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5:2])

        self.show_step(5)
        self.show_step(6)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup_default],
                'slave-05': [['controller'], nodegroup_default],
                'slave-03': [['controller'], nodegroup_default],
                'slave-02': [['compute', 'cinder'], nodegroup_custom],
                'slave-04': [['compute', 'cinder'], nodegroup_custom],
            }
        )

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_neutron_tun_ha_nodegroups")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["multiple_cluster_networks",
                  "deploy_ceph_ha_nodegroups", "thread_7"])
    @log_snapshot_after_test
    def deploy_ceph_ha_nodegroups(self):
        """Deploy HA environment with Neutron VXLAN, Ceph and 2 nodegroups

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create cluster with Neutron VXLAN, Ceph and custom nodegroup
            4. Bootstrap slave nodes from custom nodegroup
            5. Add 3 controller + ceph nodes from default nodegroup
            6. Add 2 compute + ceph nodes from custom nodegroup
            7. Deploy cluster
            8. Run network verification
            9. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:5:2])

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlanCeph',
                'user': 'haVxlanCeph',
                'password': 'haVxlanCeph'
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:5:2])

        self.show_step(5)
        self.show_step(6)
        nodegroup_default = NODEGROUPS[0]['name']
        nodegroup_custom = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-05': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-03': [['controller', 'ceph-osd'], nodegroup_default],
                'slave-02': [['compute', 'ceph-osd'], nodegroup_custom],
                'slave-04': [['compute', 'ceph-osd'], nodegroup_custom],
            }
        )

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ceph_ha_nodegroups")

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_ceph_ha", "thread_7"])
    @log_snapshot_after_test
    def deploy_controllers_from_custom_nodegroup(self):
        """Assigning controllers to non-default nodegroup

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from custom nodegroup
            3. Create environment with Neutron VXLAN and custom nodegroup
            ?. Create new 'custom' nodegroup for the environment and configure
            its networks (floating ranges and ALL VIPs must be from networks
            which belong to 'custom' nodegroup)
            4. Bootstrap slave nodes from default nodegroup
            ?. Set IPs for VIPs (use the same subnet, but change addresses
            automatically assigned by Nailgun)
            5. Add 3 nodes from 'custom' nodegroup as controllers
            Add 2 nodes from 'default' nodegroup as computes
            Add 2 node from 'default' nodegroup as cinder/ceph
            6. Run network verification
            7. Deploy environment
            8. Run network verification
            9. Run OSTF

        Duration ???m
        Snapshot deploy_controllers_from_custom_nodegroup

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:6:2])  # 246

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlanCeph',
                'user': 'haVxlanCeph',
                'password': 'haVxlanCeph'
            }
        )

        self.show_step(4)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:8:2])  # 1357


        ''' ???
        TODO:
        Configure its networks (floating ranges and ALL VIPs must be from
        networks which belong to 'custom' nodegroup)
        '''

        ''' ???
        TODO:
        Set IPs for VIPs (use the same subnet, but change addresses
        automatically assigned by Nailgun)
        '''

        self.show_step(5)
        default_nodegroup = NODEGROUPS[0]['name']
        custom_nodegroup = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-02': [['controller'], custom_nodegroup],
                'slave-04': [['controller'], custom_nodegroup],
                'slave-06': [['controller'], custom_nodegroup],
                'slave-01': [['compute'], default_nodegroup],
                'slave-03': [['compute'], default_nodegroup],
                'slave-05': [['cinder'], default_nodegroup],
                'slave-07': [['cinder'], default_nodegroup],
            }
        )

        self.show_step(6)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)

        self.show_step(8)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_controllers_from_custom_nodegroup")


    @test(depends_on=[SetupEnvironment.prepare_release],
    groups=["multiple_cluster_networks",
            "multiple_cluster_net_ceph_ha", "thread_7"])
    @log_snapshot_after_test
    def add_nodes_from_custom_nodegroup_to_deployed_env(self):
        '''Add nodes from custom nodegroup to deployed cluster

        Scenario:
            1. Revert snapshot with ready master node
            2. Bootstrap slaves from default nodegroup
            3. Create environment with Neutron VXLAN and default nodegroup
            4. Add nodes from 'default' nodegroup
            5. Run network verification
            6. Deploy environment
            7. Run network verification
            8. Run OSTF
            9. Bootstrap slaves from custom nodegroup
            ?. Create new 'custom' nodegroup for the environment and configure its
            networks
            10. Add nodes from 'custom' nodegroup to the environment
            11. Run network verification
            12. Deploy changes
            13. Run network verification
            14. Run OSTF
            15. Check that nodes from 'default' nodegroup can reach nodes from
            'custom' nodegroup via management and storage networks (check route
            presence, verify by ping)

        Duration ???m
        Snapshot add_nodes_from_custom_nodegroup_to_deployed_env
        '''

        if not MULTIPLE_NETWORKS:
            raise SkipTest()

        self.show_step(1)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:9:2])  # 13579

        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT['tun'],
                'tenant': 'haVxlanCeph',
                'user': 'haVxlanCeph',
                'password': 'haVxlanCeph'
            }
        )

        self.show_step(4)
        default_nodegroup = NODEGROUPS[0]['name']
        custom_nodegroup = NODEGROUPS[1]['name']
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], default_nodegroup],
                'slave-03': [['controller'], default_nodegroup],
                'slave-05': [['controller'], default_nodegroup],
                'slave-07': [['compute'], default_nodegroup],
                'slave-09': [['cinder'], default_nodegroup],
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[1:4:2])  # 24

        self.show_step(10)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], default_nodegroup],
                'slave-03': [['controller'], default_nodegroup],
                'slave-05': [['controller'], default_nodegroup],
                'slave-07': [['compute'], default_nodegroup],
                'slave-09': [['cinder'], default_nodegroup],
                'slave-02': [['compute'], custom_nodegroup],
                'slave-04': [['compute'], custom_nodegroup],
            }
        )

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)

        self.show_step(13)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(14)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(15)
        '''
        TODO:
        Check that nodes from 'default' nodegroup can reach nodes from
        'custom' nodegroup via management and storage networks (check route
        presence, verify by ping)
        '''

        self.env.make_snapshot("add_nodes_from_custom_nodegroup_to_deployed_env")
