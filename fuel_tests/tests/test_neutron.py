
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions

import pytest


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.need_ready_cluster
@pytest.mark.ha_neutron
class TestNeutronTunHa(object):
    """NeutronTunHa.

    Old groups: ha_neutron, neutron, ha, classic_provisioning
    """  # TODO documentation

    cluster_config = {
        "name": "NeutronGreHa",
        "mode": settings.DEPLOYMENT_MODE,
        "settings": {
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'haGre',
            'user': 'haGre',
            'password': 'haGre'
        },
        "nodes": {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute'],
            'slave-05': ['compute']
        }
    }

    @pytest.mark.deploy_neutron_gre_ha
    @pytest.mark.ha_neutron_gre
    def test_deploy_neutron_gre_ha(self):
        """Deploy cluster in HA mode with Neutron TUN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_gre_ha

        """
        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        self.manager.show_step(5)

        cluster_id = self._storage['cluster_id']
        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert str(cluster['net_provider']), 'neutron'

        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))

        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            for _ in range(5):
                try:
                    checkers.check_swift_ring(_ip)
                    break
                except AssertionError:
                    result = remote.execute(
                        "/usr/local/bin/swift-rings-rebalance.sh")
                    logger.debug("command execution result is {0}"
                                 .format(result))
            else:
                checkers.check_swift_ring(_ip)

        self.manager.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'])


@pytest.mark.get_logs
@pytest.mark.fail_snapshot
@pytest.mark.need_ready_cluster
@pytest.mark.ha_neutron
class TestNeutronVlanHa(object):
    """NeutronVlanHa.


    Old groups: neutron, ha, ha_neutron

    """  # TODO documentation

    cluster_config = {
        "name": "NeutronGreHa",
        "mode": settings.DEPLOYMENT_MODE,
        "settings": {
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            'tenant': 'haGre',
            'user': 'haGre',
            'password': 'haGre'
        },
        "nodes": {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute'],
            'slave-05': ['compute']
        }
    }

    @pytest.mark.deploy_neutron_vlan_ha
    @pytest.mark.neutron_vlan_ha
    def test_deploy_neutron_vlan_ha(self):
        """Deploy cluster in HA mode with Neutron VLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_vlan_ha

        """
        self.manager.show_step(1)
        self.manager.show_step(2)
        self.manager.show_step(3)
        self.manager.show_step(4)
        self.manager.show_step(5)

        cluster_id = self._storage['cluster_id']

        cluster = self.fuel_web.client.get_cluster(cluster_id)
        assert str(cluster['net_provider']), 'neutron'

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            cluster_id, os_conn)

        self.fuel_web.verify_network(cluster_id)
        devops_node = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        logger.debug("devops node name is {0}".format(devops_node.name))
        _ip = self.fuel_web.get_nailgun_node_by_name(devops_node.name)['ip']
        with self.env.d_env.get_ssh_to_remote(_ip) as remote:
            for _ in range(5):
                try:
                    checkers.check_swift_ring(_ip)
                    break
                except AssertionError:
                    result = remote.execute(
                        "/usr/local/bin/swift-rings-rebalance.sh")
                    logger.debug("command execution result is {0}"
                                 .format(result))
            else:
                checkers.check_swift_ring(_ip)

        self.manager.show_step(6)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])
