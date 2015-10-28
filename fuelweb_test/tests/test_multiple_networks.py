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
from proboscis.asserts import assert_equal

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

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["multiple_cluster_networks", "multiple_cluster_net_setup"])
    @log_snapshot_after_test
    def multiple_cluster_net_setup(self):
        """Check master node deployment and configuration with 2 sets of nets

        Scenario:
            1. Revert snapshot with 9 slaves
            2. Check that slaves got IPs via DHCP from both admin/pxe networks
            3. Make environment snapshot

        Duration 6m
        Snapshot multiple_cluster_net_setup
        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("ready_with_5_slaves")

        # Get network parts of IP addresses with /24 netmask
        admin_net = self.env.d_env.admin_net
        admin_net2 = self.env.d_env.admin_net2
        get_network = lambda x: self.env.d_env.get_network(name=x).ip_network

        # This should be refactored
        networks = ['.'.join(get_network(n).split('.')[0:-1])
                    for n in [admin_net, admin_net2]]
        nodes_addresses = ['.'.join(node['ip'].split('.')[0:-1]) for node in
                           self.fuel_web.client.list_nodes()]

        assert_equal(set(networks), set(nodes_addresses),
                     "Only one admin network is used for discovering slaves:"
                     " '{0}'".format(set(nodes_addresses)))

        self.env.make_snapshot("multiple_cluster_net_setup", is_make=True)

    @test(depends_on=[multiple_cluster_net_setup],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_neutron_tun_ha", "thread_7"])
    @log_snapshot_after_test
    @check_fuel_statistics
    def deploy_neutron_tun_ha_nodegroups(self):
        """Deploy HA environment with NeutronVXLAN and 2 nodegroups

        Scenario:
            1. Revert snapshot with 2 networks sets for slaves
            2. Create cluster (HA) with Neutron VXLAN
            3. Add 3 controller nodes from default nodegroup
            4. Add 2 compute nodes from custom nodegroup
            5. Deploy cluster
            6. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_neutron_tun_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("multiple_cluster_net_setup")

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

        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-05': [['controller'], nodegroup1],
                'slave-03': [['controller'], nodegroup1],
                'slave-02': [['compute', 'cinder'], nodegroup2],
                'slave-04': [['compute', 'cinder'], nodegroup2],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_neutron_tun_ha_nodegroups")

    @test(depends_on=[multiple_cluster_net_setup],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_ceph_ha", "thread_7"])
    @log_snapshot_after_test
    def deploy_ceph_ha_nodegroups(self):
        """Deploy HA environment with Neutron VXLAN, Ceph and 2 nodegroups

        Scenario:
            1. Revert snapshot with 2 networks sets for slaves
            2. Create cluster (HA) with Neutron VXLAN and Ceph
            3. Add 3 controller + ceph nodes from default nodegroup
            4. Add 2 compute + ceph nodes from custom nodegroup
            5. Deploy cluster
            6. Run health checks (OSTF)

        Duration 110m
        Snapshot deploy_ceph_ha_nodegroups

        """

        if not MULTIPLE_NETWORKS:
            raise SkipTest()
        self.env.revert_snapshot("multiple_cluster_net_setup")

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

        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller', 'ceph-osd'], nodegroup1],
                'slave-05': [['controller', 'ceph-osd'], nodegroup1],
                'slave-03': [['controller', 'ceph-osd'], nodegroup1],
                'slave-02': [['compute', 'ceph-osd'], nodegroup2],
                'slave-04': [['compute', 'ceph-osd'], nodegroup2],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=150 * 60)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ceph_ha_nodegroups")

    @test(depends_on=[multiple_cluster_net_setup],
          groups=["multiple_cluster_networks",
                  "multiple_cluster_net_ceph_ha", "thread_7"])
    @log_snapshot_after_test
    def deploy_controllers_from_custom_nodegroup(self):
        """Assigning controllers to non-default nodegroup

        Scenario:
            1. Revert snapshot with 2 networks sets for slaves
            2. Create environment
            3. Create new 'custom' nodegroup for the environment and configure
            its networks (floating ranges and ALL VIPs must be from networks
            which belong to 'custom' nodegroup)
            4. Set IPs for VIPs (use the same subnet, but change addresses
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
        self.env.revert_snapshot("multiple_cluster_net_setup")

        self.show_step(2)
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

        self.show_step(3)
        default_nodegroup = NODEGROUPS[0]['name']
        custom_nodegroup = NODEGROUPS[1]['name']

        '''
        Configure its networks (floating ranges and ALL VIPs must be from
        networks which belong to 'custom' nodegroup)
        '''

        self.show_step(4)
        '''
        Set IPs for VIPs (use the same subnet, but change addresses
        automatically assigned by Nailgun)
        '''

        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], custom_nodegroup],
                'slave-02': [['controller'], custom_nodegroup],
                'slave-03': [['controller'], custom_nodegroup],
                'slave-04': [['compute'], default_nodegroup],
                'slave-05': [['compute'], default_nodegroup],
                'slave-06': [['cinder'], default_nodegroup],
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