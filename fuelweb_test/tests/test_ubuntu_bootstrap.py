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

from proboscis import test
from proboscis.asserts import assert_true, assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["bvt_ubuntu_bootstrap"])
class UbuntuBootstrap(TestBasic):
    """CephRadosGW."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["deploy_neutron_stop_on_deploying_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def deploy_neutron_stop_on_deploying_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with neutron

        Scenario:
            1. Create cluster in HA mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Run provisioning task
            5. Run deployment task
            6. Stop deployment
            7. Add 1 node with cinder role
            8. Re-deploy cluster
            9. Run OSTF

        Duration 55m
        Snapshot: deploy_neutron_stop_on_deploying_ubuntu_bootstrap
        """
        self.env.revert_snapshot("ready")

        # Run script on master node to change bootstrap to Ubuntu
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'fuel-bootstrap-image-set ubuntu'
            result = remote.execute(cmd)
            assert_equal(
                result['exit_code'],
                0,
                'Command {0} execution failed with non-zero exit code. '
                'Actual result {1} stderr {2}'
                'Log info {3}'.format(
                    cmd, result['exit_code'],
                    result['stderr'], result['stdout']))

        # Need to remove after Bug#1482242 will be fixed
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'dockerctl shell cobbler service dnsmasq restart'
            result = remote.execute(cmd)
            assert_equal(
                result['exit_code'],
                0,
                'Command {0} execution failed with non-zero exit code. '
                'Actual result {1} stderr {2}'
                'Log info {3}'.format(
                    cmd, result['exit_code'],
                    result['stderr'], result['stdout']))

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:3])

        # Verify version of bootstrap on slaves function
        def verify_bootstrap_on_slaves(slaves):
            for slave in slaves:
                with self.fuel_web.get_ssh_for_remote(slave) as slave_remote:
                    cmd = slave_remote.execute('uname -a')
                    assert_true(
                        "Ubuntu" in ''.join(remote.execute(cmd)['stdout']),
                        "Slave use Centos bootstrap instead of Ubuntu")

        # Verify version of bootstrap on slaves
        verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'stop_deploy',
                'user': 'stop_deploy',
                'password': 'stop_deploy',
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # Deploy cluster and stop deployment, then verify bootstrap
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)
        verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

        self.env.make_snapshot(
            "deploy_neutron_stop_on_deploying_ubuntu_bootstrap")
