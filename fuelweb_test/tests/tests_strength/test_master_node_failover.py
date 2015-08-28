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

from proboscis.asserts import assert_equal
from proboscis import test
import traceback

from fuelweb_test.helpers import common
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests import base_test_case
import time


@test(groups=["thread_non_func_1"])
class DeployHAOneControllerMasterNodeFail(base_test_case.TestBasic):
    """DeployHAOneControllerMasterNodeFail."""  # TODO documentation

    def resume_admin_node(self):
        logger.info('Start admin node...')
        self.env.d_env.nodes().admin.resume()
        try:
            self.env.d_env.nodes().admin.await(
                self.env.d_env.admin_net, timeout=60, by_port=8000)
        except Exception as e:
            logger.warning(
                "From first time admin isn't reverted: {0}".format(e))
            self.env.d_env.nodes().admin.destroy()
            logger.info('Admin node was destroyed. Wait 10 sec.')
            time.sleep(10)
            self.env.d_env.nodes().admin.start()
            logger.info('Admin node started second time.')
            self.env.d_env.nodes().admin.await(self.env.d_env.admin_net)
            self.env.set_admin_ssh_password()
            self.env.docker_actions.wait_for_ready_containers(
                timeout=600)

        logger.info('Waiting for containers')
        self.env.set_admin_ssh_password()
        self.env.docker_actions.wait_for_ready_containers()

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["non_functional",
                  "deploy_ha_one_controller_neutron_master_node_fail"])
    @log_snapshot_after_test
    def deploy_ha_one_controller_neutron_master_node_fail(self):
        """Deploy HA cluster with neutron and check it without master node

        Scenario:
            1. Create cluster in ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Deploy the cluster
            5. Validate cluster was set up correctly, there are no dead
               services, there are no errors in logs
            6. Verify networks
            7. Verify network configuration on controller
            8. Run OSTF
            9. Shut down master node
            10. Run openstack verification

        Duration 1000m
        """
        self.env.revert_snapshot("ready_with_3_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT_TYPE
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        controller_ip = self.fuel_web.get_public_vip(cluster_id)

        os_conn = os_actions.OpenStackActions(controller_ip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)

        self.fuel_web.verify_network(cluster_id)
        logger.info('PASS DEPLOYMENT')
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)
        logger.info('PASS OSTF')

        logger.info('Destroy admin node...')
        try:
            self.env.d_env.nodes().admin.destroy()
            logger.info('Admin node destroyed')

            common_func = common.Common(
                controller_ip,
                settings.SERVTEST_USERNAME,
                settings.SERVTEST_PASSWORD,
                settings.SERVTEST_TENANT)

            # create instance
            server = common_func.create_instance(neutron_network=True)

            # get_instance details
            details = common_func.get_instance_detail(server)
            assert_equal(details.name, 'test_instance')

            # Check if instacne active
            common_func.verify_instance_status(server, 'ACTIVE')

            # delete instance
            common_func.delete_instance(server)
        except Exception:
            logger.error(
                'Failed to operate with cluster after master node destroy')
            logger.error(traceback.format_exc())
            raise
        finally:
            self.resume_admin_node()

        self.env.make_snapshot(
            "deploy_ha_one_controller_neutron_master_node_fail")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_dns_ntp"])
    @log_snapshot_after_test
    def deploy_ha_dns_ntp(self):
        """Use external ntp and dns in ha mode

        Scenario:
            1. Create cluster
            2  Configure external NTP,DNS settings
            3. Add 3 nodes with controller roles
            4. Add 2 nodes with compute roles
            5. Deploy the cluster

        """

        self.env.revert_snapshot("ready_with_5_slaves")
        external_dns = settings.EXTERNAL_DNS
        if settings.FUEL_USE_LOCAL_DNS:
            public_gw = self.env.d_env.router(router_name="public")
            external_dns += ',' + public_gw

        net_provider_data = {
            'ntp_list': settings.EXTERNAL_NTP,
            'dns_list': external_dns,
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT_TYPE
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings=net_provider_data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        os_conn = os_actions.OpenStackActions(self.fuel_web.
                                              get_public_vip(cluster_id))
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=14)

        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.env.make_snapshot("deploy_ha_dns_ntp", is_make=True)

    @test(depends_on=[deploy_ha_dns_ntp],
          groups=["external_dns_ha"])
    @log_snapshot_after_test
    def external_dns_ha(self):
        """Check external dns in ha mode

        Scenario:
            1. Revert cluster
            2. Shutdown dnsmasq
            3. Check dns resolution

        """

        self.env.revert_snapshot("deploy_ha_dns_ntp")

        remote = self.env.d_env.get_admin_remote()
        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        remote_slave = self.env.d_env.get_ssh_to_remote(_ip)
        remote.execute("dockerctl shell cobbler killall dnsmasq")
        checkers.external_dns_check(remote_slave)

    @test(depends_on=[deploy_ha_dns_ntp],
          groups=["external_ntp_ha"])
    @log_snapshot_after_test
    def external_ntp_ha(self):
        """Check external ntp in ha mode

        Scenario:
            1. Create cluster
            2. Shutdown ntpd
            3. Check ntp update

        """

        self.env.revert_snapshot("deploy_ha_dns_ntp")

        cluster_id = self.fuel_web.get_last_created_cluster()
        remote = self.env.d_env.get_admin_remote()
        _ip = self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']
        remote_slave = self.env.d_env.get_ssh_to_remote(_ip)
        vrouter_vip = self.fuel_web.get_management_vrouter_vip(cluster_id)
        remote.execute("pkill -9 ntpd")
        checkers.external_ntp_check(remote_slave, vrouter_vip)
