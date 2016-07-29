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

from devops.error import TimeoutError
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers import common
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import utils
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase


@test(groups=["public_api"])
class TestPublicApi(TestNetworkTemplatesBase):
    """TestPublicApi."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_env_with_public_api'])
    @log_snapshot_after_test
    def deploy_env_with_public_api(self):
        """Deploy environment with enabled DMZ network for API.

        Scenario:
            1. Revert snapshot with ready master node
            2. Create new environment
            3. Run network verification
            4. Deploy the environment
            5. Run network verification
            6. Run OSTF
            7. Reboot cluster nodes
            8. Run OSTF
            9. Create environment snapshot deploy_env_with_public_api

        Duration 120m
        Snapshot deploy_env_with_public_api
        """

        asserts.assert_true(settings.ENABLE_DMZ,
                            "ENABLE_DMZ variable wasn't exported")
        self.check_run('deploy_env_with_public_api')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('ready_with_5_slaves')

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'tenant': 'netTemplate',
                'user': 'netTemplate',
                'password': 'netTemplate',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder'],
            },
            update_interfaces=False
        )

        network_template = utils.get_network_template('public_api')
        self.fuel_web.client.upload_network_template(
            cluster_id=cluster_id, network_template=network_template)

        net = self.fuel_web.get_network_pool('os-api')
        nodegroup = self.fuel_web.get_nodegroup(cluster_id)
        os_api_template = {
            "group_id": nodegroup['id'],
            "name": 'os-api',
            "cidr": net['network'],
            "gateway": net['gateway'],
            "meta": {
                'notation': 'cidr',
                'render_type': None,
                'map_priority': 2,
                'configurable': True,
                'use_gateway': True,
                'name': 'os-api',
                'cidr': net['network'],
                'vlan_start': None,
                'vips': ['haproxy']
            }
        }
        self.fuel_web.client.add_network_group(os_api_template)

        logger.debug('Networks: {0}'.format(
            self.fuel_web.client.get_network_groups()))

        self.show_step(3)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        cluster_slaves = self.env.d_env.nodes().slaves[:3]
        self.fuel_web.warm_shutdown_nodes(cluster_slaves)
        self.fuel_web.warm_start_nodes(cluster_slaves)

        self.fuel_web.assert_cluster_ready(cluster_id)
        self.fuel_web.assert_os_services_ready(cluster_id)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        self.env.make_snapshot('deploy_env_with_public_api')


    @test(depends_on=[deploy_env_with_public_api],
          groups=['public_api_check_security_rules'])
    @log_snapshot_after_test
    def public_api_check_security_rules(self):
        """Check that security rules are properly applied for DMZ network

        Scenario:
            1. Revert snapshot from previous test
            2. Try to access public API from instance (should fail)
            3. ... (to be added after feature spec creation)
        """

        asserts.assert_true(settings.ENABLE_DMZ,
                            "ENABLE_DMZ variable wasn't exported")

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_env_with_public_api')

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)

        os_conn = common.Common(
            controller_ip,
            settings.SERVTEST_USERNAME,
            settings.SERVTEST_PASSWORD,
            settings.SERVTEST_TENANT)

        # create instance
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        vm = os_conn.create_instance(neutron_network=True,
                                             label=net_name)

        # get_instance details
        details = os_conn.get_instance_detail(vm)
        asserts.assert_equal(details.name, 'test_instance')

        # Check if instance active
        os_conn.verify_instance_status(vm, 'ACTIVE')

        vm_floating_ip = os_conn.assign_floating_ip(vm)
        logger.info('Trying to get vm via tcp.')
        try:
            wait(lambda: tcp_ping(vm_floating_ip.ip, 22), timeout=120)
        except TimeoutError:
            raise TimeoutError('Can not ping instance'
                               ' by floating ip {0}'.format(vm_floating_ip.ip))
        logger.info('VM is accessible via ip: {0}'.format(vm_floating_ip.ip))

        horizon_url = 'http://10.200.1.2/horizon'
        cmd = 'curl {}'.format(horizon_url)
        res = os_conn.execute_through_host(controller_ip,
                                           vm_floating_ip,
                                           cmd)
        # TODO(mstrukov): According bp:test-separate-public-floating instance
        # shouldn't access public service without new firewall rules
        asserts.assert_equal(res['exit_code'], 0,
                             "Instance can't access horizon via DMZ network")

        # delete instance
        os_conn.delete_instance(vm)
        os_conn.verify_srv_deleted(vm)

    @test(depends_on=[deploy_env_with_public_api],
          groups=['public_api_check_fw_rules'])
    @log_snapshot_after_test
    def public_api_check_fw_rules(self):
        """Check that custom firewall rules aren't overridden by deployment actions (puppet)

        Scenario
            1. Revert snapshot from previous test
            2. Add some custom firewall rule (e.g. block access to some service API) inside HAProxy namespace
            3. Add new controller node and deploy changes
            4. Check that custom firewall rules are kept
        """

        asserts.assert_true(settings.ENABLE_DMZ,
                            "ENABLE_DMZ variable wasn't exported")

        self.show_step(1, initialize=True)
        self.env.revert_snapshot('deploy_env_with_public_api')

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        # controller_ip = self.fuel_web.get_public_vip(cluster_id)

        logger.warning("Test hasn't implemented yet")