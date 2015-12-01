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
from devops.helpers.helpers import wait
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_true, assert_equal

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import run_on_remote
from fuelweb_test.helpers import fuel_actions
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["bvt_centos_bootstrap"])
class CentosBootstrap(TestBasic):
    def verify_bootstrap_on_node(self, node):
        logger.info("Verify bootstrap on slaves")
        with self.fuel_web.get_ssh_for_node(node.name) as slave_remote:
            cmd = 'cat /etc/*release'
            output = run_on_remote(slave_remote, cmd)[0].lower()
            assert_true("centos" in output,
                        "Slave {0} doesn't use CentOS image for "
                        "bootstrap after CentOS images "
                        "were enabled, /etc/release content: {1}"
                        .format(node.name, output))

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["prepare_centos_bootstrap"])
    @log_snapshot_after_test
    def activate_centos_bootstrap(self):
        """Verify than slaves retrieved CentOS bootstrap instead of Ubuntu

        Scenario:
            1. Revert snapshot ready
            2. Choose CentOS bootstrap on master node
            3. Bootstrap slaves
            4. Verify bootstrap on slaves

        Duration 15m
        Snapshot: prepare_centos_bootstrap
        """
        self.env.revert_snapshot("ready")

        with self.env.d_env.get_admin_remote() as remote:
            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            fuel_bootstrap.activate_bootstrap_image("centos",
                                                    notify_webui=True)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)
        map(self.verify_bootstrap_on_node, nodes)

        self.env.make_snapshot("prepare_centos_bootstrap",
                               is_make=True)

    @test(depends_on_groups=["prepare_centos_bootstrap"],
          groups=["deploy_stop_on_deploying_centos_bootstrap"])
    @log_snapshot_after_test
    def deploy_stop_on_deploying_centos_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on CentOS Bootstrap

        Scenario:
            1. Create cluster in Ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Verify network
            5. Deploy cluster
            6. Stop deployment
            7. Verify bootstrap on slaves
            8. Add 1 node with cinder role
            9. Re-deploy cluster
            10. Verify network
            11. Run OSTF

        Duration 45m
        Snapshot: deploy_stop_on_deploying_centos_bootstrap
        """

        if not self.env.revert_snapshot('prepare_centos_bootstrap'):
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

        self.env.make_snapshot(
            "deploy_stop_on_deploying_centos_bootstrap",
            is_make=True)

    @test(depends_on_groups=['deploy_stop_on_deploying_centos_bootstrap'],
          groups=["deploy_reset_on_ready_centos_bootstrap"])
    @log_snapshot_after_test
    def deploy_reset_on_ready_centos_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on CentOS Bootstrap

        Scenario:
            1. Reset cluster
            2. Verify bootstrap on slaves
            3. Re-deploy cluster
            4. Verify network
            5. Run OSTF

        Duration 30m
        """

        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_centos_bootstrap'):
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Reset environment,
        # then verify bootstrap on slaves and re-deploy cluster
        self.fuel_web.stop_reset_env_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:3], timeout=10 * 60)
        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

    @test(depends_on_groups=['deploy_stop_on_deploying_centos_bootstrap'],
          groups=["delete_on_ready_centos_bootstrap"])
    @log_snapshot_after_test
    def delete_on_ready_centos_bootstrap(self):
        """Delete cluster cluster in HA mode\
        with 1 controller on CentOS Bootstrap

        Scenario:
            1. Delete cluster
            2. Verify bootstrap on slaves

        Duration 30m
        Snapshot: delete_on_ready_centos_bootstrap
        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_centos_bootstrap'):
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        self.fuel_web.client.delete_cluster(cluster_id)

        # wait nodes go to reboot
        wait(lambda: not self.fuel_web.client.list_nodes(), timeout=10 * 60)

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60)

        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[:3])

        self.env.make_snapshot(
            "delete_on_ready_centos_bootstrap",
            is_make=True)

    @test(depends_on_groups=['deploy_stop_on_deploying_centos_bootstrap'],
          groups=["delete_node_on_ready_centos_bootstrap"])
    @log_snapshot_after_test
    def delete_node_on_ready_centos_bootstrap(self):
        """Delete node from cluster in HA mode\
        with 1 controller on CentOS Bootstrap

        Scenario:
            1. Delete node
            2. Verify bootstrap on slaves

        Duration 30m
        Snapshot: delete_on_ready_centos_bootstrap
        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_centos_bootstrap'):
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.fuel_web.run_network_verify(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60)

        self.verify_bootstrap_on_slaves(self.env.d_env.nodes().slaves[2])

    # @test(depends_on_groups=['deploy_stop_on_deploying_centos_bootstrap'],
    #       groups=["delete_node_on_ready_ubuntu_bootstrap"])
    # def rebootstrap_new_node(self):
    #     """Delete node from cluster in HA mode\
    #     with 1 controller on Ubuntu Bootstrap
    #
    #     Scenario:
    #         1. Revert snapshot
    #         2. Build and activate new bootstrap image
    #         3. Restart unallocated node
    #         4. Verify new bootstrap
    #
    #     Duration 30m
    #     Snapshot: delete_on_ready_ubuntu_bootstrap
    #     """
    #
    #     pass
