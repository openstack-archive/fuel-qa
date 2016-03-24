import time
import pytest
from fuelweb_test import settings
from fuelweb_test.helpers import os_actions


class BaseNeutronFailover(object):

    def prepare(self):
        self.manager.get_ready_cluster(config=self.cluster_config)
        public_vip = self.fuel_web.get_public_vip(self._storage['cluster_id'])
        os_conn = os_actions.OpenStackActions(public_vip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)


    def destroy_controllers(self, num):

        def get_needed_controllers(cluster_id):
            n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id=cluster_id,
                roles=['controller'])
            ret = []
            d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)
            p_d_ctrl = self.fuel_web.get_nailgun_primary_node(d_ctrls[0])
            ret.append(p_d_ctrl)
            ret.append((set(d_ctrls) - {p_d_ctrl}).pop())

            return ret

        # STEP: Revert environment
        # if num==0: show_step(1); if num==1: show_step(5)
        self.show_step([1, 5][num])
        self.env.revert_snapshot(self.snapshot_name)

        cluster_id = self.fuel_web.client.get_cluster_id(
            self.__class__.__name__)
        controllers = list(get_needed_controllers(cluster_id))

        # STEP: Destroy first/second controller
        devops_node = controllers[num]
        # if num==0: show_step(2); if num==1: show_step(6)
        self.show_step([2, 6][num], details="Destroying node: "
                       "{0}".format(devops_node.name))
        devops_node.destroy(False)

        # STEP: Check pacemaker status
        self.show_step([3, 7][num])
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=cluster_id,
            roles=['controller'])
        d_ctrls = self.fuel_web.get_devops_nodes_by_nailgun_nodes(n_ctrls)

        self.fuel_web.assert_pacemaker(
            (set(d_ctrls) - {devops_node}).pop().name,
            set(d_ctrls) - {devops_node},
            [devops_node])

        # Wait until Nailgun marked suspended controller as offline
        wait(lambda: not self.fuel_web.get_nailgun_node_by_devops_node(
            devops_node)['online'],
            timeout=60 * 5)

        # Wait the pacemaker react to changes in online nodes
        time.sleep(60)
        # Wait for HA services ready
        self.fuel_web.assert_ha_services_ready(cluster_id, should_fail=1)
        # Wait until OpenStack services are UP
        self.fuel_web.assert_os_services_ready(cluster_id, should_fail=1)

        logger.info("Waiting 300 sec before MySQL Galera will up, "
                    "then run OSTF")

        # Wait until MySQL Galera is UP on online controllers
        self.fuel_web.wait_mysql_galera_is_up(
            [n.name for n in set(d_ctrls) - {devops_node}],
            timeout=300)

        # STEP: Run OSTF
        self.show_step([4, 8][num])
        # should fail 2 according to haproxy backends marked as fail
        self.fuel_web.run_ostf(
            cluster_id=cluster_id,
            test_sets=['ha', 'smoke', 'sanity'],
            should_fail=2)

    def disconnect_controllers(self):

        cluster_id = self._storage['cluster_id']

        p_d_ctrl = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])
        with self.fuel_web.get_ssh_for_node(p_d_ctrl.name) as remote:

            cmd = ('iptables -I INPUT -i br-mgmt -j DROP && '
                   'iptables -I OUTPUT -o br-mgmt -j DROP')
            remote.check_call(cmd)

        # Wait until MySQL Galera is UP on some controller
        self.fuel_web.wait_mysql_galera_is_up(['slave-02'])
        # should fail 2 according to haproxy backends marked as fail
        try:
            self.fuel_web.run_ostf(
                cluster_id=cluster_id,
                test_sets=['sanity', 'smoke'], should_fail=2)
        except AssertionError:
            time.sleep(600)
            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['smoke', 'sanity'],
                                   should_fail=2)

@pytest.mark.ha
@pytest.mark.neutron_failover
@pytest.mark.ha_neutron_destructive
@pytest.mark.usefixtures("manager")
@pytest.mark.incremental
class TestHaNeutronFailover2(BaseNeutronFailover):

    cluster_config = {
        'name': "TestHaNeutronFailover2",
        'mode': settings.DEPLOYMENT_MODE,
        'nodes': {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['compute'],
            'slave-05': ['compute'],
            'slave-06': ['cinder']
        }
    }

    def setup_method(self, method):
        # Revert or setup cluster for tests
        if 'prepare' not in method.func_name:
            self.manager.get_ready_cluster(config=self.cluster_config)
            public_vip = self.fuel_web.get_public_vip(
                self.manager._storage['cluster_id'])
            os_conn = os_actions.OpenStackActions(public_vip)
            self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)

    @pytest.mark.prepare_ha_neutron
    def test_prepare_ha_neutron(self):
        self.prepare()

    @pytest.mark.ha_neutron_destroy_controllers
    @pytest.mark.parametrize('num', range(2))
    def test_ha_neutron_destroy_controllers(self, num):
        self.neutron_destroy_controllers(num)

    @pytest.mark.ha_neutron_disconnect_controllers
    def test_ha_neutron_disconnect_controllers(self):
        self.disconnect_controllers()
