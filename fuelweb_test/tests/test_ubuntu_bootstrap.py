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

from devops.error import TimeoutError
from devops.helpers.helpers import wait

from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_true, assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["bvt_ubuntu_bootstrap"])
class UbuntuBootstrap(TestBasic):
    # TODO documentation

    # Verify version of bootstrap on slaves function
    def verify_bootstrap_on_slaves(self, slaves):
        logger.info("Verify bootstrap on slaves")
        for slave in slaves:
            with self.fuel_web.get_ssh_for_node(
                    slave.name) as slave_remote:
                cmd = 'cat /etc/*release'
                output = run_on_remote(
                    slave_remote, cmd)[0].lower()
                assert_true(
                    "ubuntu" in output,
                    "Slave {0} doesn't use Ubuntu image for\
                    bootstrap after Ubuntu images \
                    were enabled".format(slave.name))

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["prepare_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def prepare_ubuntu_bootstrap(self):
        """Verify than slaves retrieved ubuntu bootstrap instead CentOS

        Scenario:
            1. Revert snapshot ready
            2. Choose Ubuntu bootstrap on master node
            3. Bootstrap slaves
            4. Verify bootstrap on slaves
            5. Make snapshot "prepare_ubuntu_bootstrap"
        Duration 15m
        """
        self.env.revert_snapshot("ready")

        # Run script on master node to change bootstrap to Ubuntu
        with self.env.d_env.get_admin_remote() as remote:

            cmd = 'fuel-bootstrap-image-set ubuntu'
            run_on_remote(remote, cmd)

        # Should be removed after Bug#1482242 will be fixed
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'dockerctl shell cobbler service dnsmasq restart'
            run_on_remote(remote, cmd)

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:3])

        # Verify version of bootstrap on slaves
        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        self.env.make_snapshot("prepare_ubuntu_bootstrap")

    @test(depends_on_group=['prepare_ubuntu_bootstrap'],
          groups=["deploy_stop_on_deploying_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def deploy_stop_on_deploying_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Create cluster in Ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy cluster
            5. Stop deployment
            6. Verify bootstrap on slaves
            7. Re-deploy cluster
            8. Verify network
            9. Run OSTF

        Duration 45m
        Snapshot: deploy_stop_on_deploying_ubuntu_bootstrap
        """

        if not self.env.revert_snapshot('prepare_ubuntu_bootstrap'):
            raise SkipTest()

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

        # Deploy cluster and stop deployment, then verify bootstrap on slaves
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.fuel_web.deploy_task_wait(cluster_id=cluster_id, progress=10)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)
        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

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

        self.env.make_snapshot("deploy_stop_on_deploying_ubuntu_bootstrap")

    @test(depends_on_group=['deploy_stop_on_deploying_ubuntu_bootstrap'],
          groups=["deploy_reset_on_ready_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def reset_on_ready_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Reset cluster
            2. Verify bootstrap on slaves
            3. Re-deploy cluster
            4. Verify network
            5. Run OSTF

        Duration 30m
        Snapshot: reset_on_ready_ubuntu_bootstrap

        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_ubuntu_bootstrap'):
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Reset environment,
        # then verify bootstrap on slaves and re-deploy cluster
        self.fuel_web.stop_reset_env_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:2], timeout=10 * 60)
        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

        self.env.make_snapshot("reset_on_ready_ubuntu_bootstrap")

    @test(depends_on_group=['deploy_stop_on_deploying_ubuntu_bootstrap'],
          groups=["delete_on_ready_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def delete_on_ready_ubuntu_bootstrap(self):
        """Delete cluster cluster in HA mode\
        with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Delete cluster cluster
            2. Verify bootstrap on slaves

        Duration 30m
        Snapshot: delete_on_ready_ubuntu_bootstrap

        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_ubuntu_bootstrap'):
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        number_of_nodes = len(self.fuel_web.client.list_cluster_nodes(
            cluster_id))
        self.fuel_web.client.delete_cluster(cluster_id)
        try:
            wait((lambda: len(
                self.fuel_web.client.list_nodes()) == number_of_nodes),
                timeout=5 * 60)
        except TimeoutError:
            assert_true(len(
                self.fuel_web.client.list_nodes()) == number_of_nodes,
                'Nodes are not discovered in timeout 5 *60')
        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        self.env.make_snapshot("delete_on_ready_ubuntu_bootstrap")
