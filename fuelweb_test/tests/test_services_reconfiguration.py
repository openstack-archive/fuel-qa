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

from __future__ import unicode_literals

import random
import time
import traceback

from devops.helpers.ssh_client import SSHAuth
from devops.helpers import helpers
from keystoneauth1.exceptions import HttpError
from keystoneauth1.exceptions import NotFound
import netaddr
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

cirros_auth = SSHAuth(**settings.SSH_IMAGE_CREDENTIALS)


def get_structured_config_dict(config):
    structured_conf = {}

    def helper(key1, key2):
        structured_conf[key2] = []
        for param, value in config[key1].items():
            d = {}
            param = param.split('/')
            d['section'] = param[0]
            d['option'] = param[1]
            k, v = value.items()[0]
            if k == 'ensure' and v == 'absent':
                d['value'] = None
            if k == 'value':
                d['value'] = str(v)
            structured_conf[key2].append(d)

    for key in config.keys():
        if key == 'neutron_config':
            helper(key, '/etc/neutron/neutron.conf')
        if key == 'neutron_plugin_ml2':
            helper(key, '/etc/neutron/plugins/ml2/ml2_conf.ini')
        if key == 'neutron_dhcp_agent_config':
            helper(key, '/etc/neutron/dhcp_agent.ini')
        if key == 'neutron_l3_agent_config':
            helper(key, '/etc/neutron/l3_agent.ini')
        if key == 'neutron_metadata_agent_config':
            helper(key, '/etc/neutron/metadata_agent.ini')
        if key == 'neutron_api_config':
            helper(key, '/etc/neutron/api-paste.ini')
        if key == 'nova_config':
            helper(key, '/etc/nova/nova.conf')
        if key == 'keystone_config':
            helper(key, '/etc/keystone/keystone.conf')
    return structured_conf


@test(groups=["services_reconfiguration"])
class ServicesReconfiguration(TestBasic):
    """ServicesReconfiguration."""

    def wait_for_node_status(self, devops_node, status, timeout=1200):
        helpers.wait(
            lambda: self.fuel_web.get_nailgun_node_by_devops_node(
                devops_node)['status'] == status, timeout=timeout,
            timeout_msg="Timeout exceeded while waiting for "
                        "node status: {0}".format(status))

    @staticmethod
    def check_response_code(expected_code, err_msg,
                            func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except HttpError as e:
            if e.http_status != expected_code:
                raise
            logger.warning('Ignoring exception: {!r}'.format(e))
            logger.debug(traceback.format_exc())
        else:
            raise Exception(err_msg)

    @staticmethod
    def change_default_range(networks, number_excluded_ips,
                             cut_from_start=True):
        """
        Change IP range for public, management, storage network
        by excluding N of first addresses from default range
        :param networks: a list of environment networks configuration
        :param number_excluded_ips: an integer number of IPs
        :param cut_from_start: a boolean flag that select first part of
        the default range if True and last one if False
        :return:
        """
        for default_network in filter(
                lambda x: ((x['name'] != 'fuelweb_admin')and
                           (x['name'] != 'private')),
                networks):
            default_range = [netaddr.IPAddress(str(ip)) for ip
                             in default_network["ip_ranges"][0]]
            if cut_from_start:
                new_range = [default_range[0],
                             default_range[0] + number_excluded_ips]
            else:
                new_range = [default_range[0] + number_excluded_ips + 1,
                             default_range[1]]
            default_network["ip_ranges"][0] = [str(ip)
                                               for ip in new_range]

    @staticmethod
    def is_update_dnsmasq_running(tasks):
        for task in tasks:
            if task['name'] == "update_dnsmasq" and \
               task["status"] == "running":
                return True
        return False

    def get_service_uptime(self, nodes, service_name):
        """
        :param nodes: a list of nailgun nodes
        :param service_name: a string of service name
        :return: a dictionary of ip nodes and process uptime
        """
        nodes = [x['ip'] for x in nodes]
        uptimes = {}
        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node) as remote:
                uptimes[node] = \
                    utils.get_process_uptime(remote, service_name)
        return uptimes

    def check_config_on_remote(self, nodes, config):
        """
        :param nodes: a list of nailgun nodes
        :param config: a structured dictionary of config
        :return:
        """
        nodes = [x['ip'] for x in nodes]
        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node) as remote:
                for configpath, params in config.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])

    def check_service_was_restarted(self, nodes, uptime_before, service_name):
        """
        :param nodes: a list of nailgun nodes
        :param uptime_before: a dictionary of ip nodes and process uptime
        :param service_name: a string of service name
        :return:
        """
        nodes = [x['ip'] for x in nodes]
        for node in nodes:
            with self.env.d_env.get_ssh_to_remote(node) as remote:
                uptime = utils.get_process_uptime(remote, service_name)
                asserts.assert_true(uptime <= uptime_before[node],
                                    'Service "{0}" was not '
                                    'restarted on {1}'.format(service_name,
                                                              node))

    def check_overcommit_ratio(self, os_conn, cluster_id):
        """
        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :return:
        """
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        server = os_conn.create_instance(neutron_network=True,
                                         label=net_name,
                                         server_name="Test_reconfig",
                                         vcpus=2)
        os_conn.verify_instance_status(server, 'ACTIVE')
        excessive_server = os_conn.create_instance(neutron_network=True,
                                                   label=net_name,
                                                   server_name="excessive_VM",
                                                   flavor_name="overcommit")
        os_conn.verify_instance_status(excessive_server, 'ERROR')
        os_conn.delete_instance(excessive_server)
        os_conn.delete_instance(server)

    def check_nova_ephemeral_disk(self, os_conn, cluster_id,
                                  hypervisor_name=None, fs_type='ext4'):
        """
        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :param hypervisor_name: a string of hypervisor name
        :param fs_type: a string of fs type name
        :return:
        """
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        flavor_id = random.randint(10, 10000)
        os_conn.create_flavor(name='ephemeral{0}'.format(flavor_id),
                              ram=64,
                              vcpus=1,
                              disk=1,
                              flavorid=flavor_id,
                              ephemeral=1)

        kwargs = {}
        if hypervisor_name:
            kwargs['availability_zone'] = "nova:{0}".format(hypervisor_name)
        instance = os_conn.create_server_for_migration(
            neutron=True, label=net_name, flavor=flavor_id, **kwargs)

        floating_ip = os_conn.assign_floating_ip(instance)

        helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22),
                     timeout=120,
                     timeout_msg="Can not ping instance by floating "
                                 "ip {0}".format(floating_ip.ip))

        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]['ip']
        with self.env.d_env.get_ssh_to_remote(controller) as remote:
            res = remote.execute_through_host(
                hostname=floating_ip.ip,
                cmd="mount",
                auth=cirros_auth
            )
            test_substr = '/mnt type {0}'.format(fs_type)
            asserts.assert_true(test_substr in res['stdout_str'],
                                "Ephemeral disk format was not "
                                "changed on instance. "
                                "Please, see details: {0}".format(res))
        os_conn.delete_instance(instance)

    @staticmethod
    def check_ml2_vlan_range(os_conn):
        """
        :param os_conn: an object of connection to openstack services
        :return:
        """
        tenant = os_conn.get_tenant('admin')
        os_conn.create_network('net1', tenant_id=tenant.id)

        try:
            os_conn.create_network('net2', tenant_id=tenant.id)
        except Exception as e:
            if 'No tenant network is available' not in e.message:
                raise
            logger.warning('Ignoring exception: {!r}'.format(e))
            logger.debug(traceback.format_exc())
        else:
            raise Exception("New configuration was not applied")

    def check_nova_quota(self, os_conn, cluster_id):
        """
        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :return:
        """
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        server = os_conn.create_instance(neutron_network=True,
                                         label=net_name,
                                         server_name="Test_reconfig")
        os_conn.verify_instance_status(server, 'ACTIVE')
        try:
            os_conn.create_instance(neutron_network=True,
                                    label=net_name,
                                    server_name="excessive_VM",
                                    flavor_name="nova_quota")
        except Exception as e:
            if 'Quota exceeded for instances' not in e.message:
                raise
            logger.warning('Ignoring exception: {!r}'.format(e))
            logger.debug(traceback.format_exc())
        else:
            raise Exception("New configuration was not applied")

    @staticmethod
    def check_token_expiration(os_conn, time_expiration):
        """
        :param os_conn: an object of connection to openstack services
        :param time_expiration: an integer value of token time expiration
               in seconds
        :return:
        """
        token = os_conn.keystone.tokens.authenticate(username='admin',
                                                     password='admin')
        time.sleep(time_expiration)

        asserts.assert_raises(
            NotFound,
            os_conn.keystone.tokens.validate,
            (token.id, )
        )

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["services_reconfiguration_thread_1",
                  "services_reconfiguration_thread_2",
                  "basic_env_for_reconfiguration"])
    @log_snapshot_after_test
    def basic_env_for_reconfiguration(self):
        """Basic environment for reconfiguration

        Scenario:
            1. Create cluster
            2. Add 1 node with compute role
            3. Add 3 nodes with controller role
            4. Deploy the cluster
            5. Verify network
            6. Run OSTF

        Snapshot: basic_env_for_reconfiguration

        """
        snapshot_name = 'basic_env_for_reconfiguration'
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE,
            }
        )
        self.show_step(2)
        self.show_step(3)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['controller']
            })

        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("basic_env_for_reconfiguration", is_make=True)

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_1",
                  "reconfigure_ml2_vlan_range"])
    @log_snapshot_after_test
    def reconfigure_ml2_vlan_range(self):
        """Reconfigure neutron ml2 VLAN range

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration
            3. Get uptime of process "neutron-server" on each controller
            4. Apply a new VLAN range(minimal range) to all nodes
            5. Wait for configuration applying
            6. Check that service "neutron-server" was restarted
            7. Verify ml2 plugin settings
            8. Create new private network
            9. Try to create one more, verify that it is impossible

        Snapshot: reconfigure_ml2_vlan_range

        """
        self.check_run('reconfigure_ml2_vlan_range')
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        self.show_step(2)
        config = utils.get_config_template('neutron')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(3)
        service_name = 'neutron-server'
        uptimes = self.get_service_uptime(controllers, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(6)
        self.check_service_was_restarted(controllers, uptimes, service_name)

        self.show_step(7)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(8)
        self.show_step(9)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.check_ml2_vlan_range(os_conn)

        self.env.make_snapshot("reconfigure_ml2_vlan_range", is_make=True)

    @test(depends_on_groups=["basic_env_for_reconfiguration"],
          groups=["services_reconfiguration_thread_1",
                  "reconfigure_overcommit_ratio"])
    @log_snapshot_after_test
    def reconfigure_overcommit_ratio(self):
        """Tests for reconfiguration nova CPU overcommit ratio.

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Apply new CPU overcommit ratio for each controller
            3. Verify deployment task is finished
            4. Verify nova-scheduler services uptime
            5. Verify configuration file on each controller
            6. Boot instances with flavor that occupy all CPU,
               boot extra instance and catch the error
            7. Apply old CPU overcommit ratio for each controller
            8. Verify deployment task is finished
            9. Verify nova-scheduler services uptime
            10. Verify configuration file on each controller

        Snapshot: reconfigure_overcommit_ratio

        """
        self.check_run('reconfigure_overcommit_ratio')
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        config_new = utils.get_config_template('nova_cpu')
        structured_config = get_structured_config_dict(config_new)
        self.fuel_web.client.upload_configuration(config_new,
                                                  cluster_id,
                                                  role="controller")

        service_name = "nova-scheduler"

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        uptimes = self.get_service_uptime(controllers, service_name)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(3)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(4)
        self.check_service_was_restarted(controllers, uptimes, service_name)

        self.show_step(5)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(6)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.check_overcommit_ratio(os_conn, cluster_id)

        self.show_step(7)
        config_revert = utils.get_config_template('nova_cpu_old')
        structured_config_revert = get_structured_config_dict(config_revert)
        self.fuel_web.client.upload_configuration(config_revert,
                                                  cluster_id,
                                                  role="controller")
        uptimes = self.get_service_uptime(controllers, service_name)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")
        self.show_step(8)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(9)
        self.check_service_was_restarted(controllers, uptimes, service_name)

        self.show_step(10)
        self.check_config_on_remote(controllers, structured_config_revert)

        self.env.make_snapshot("reconfigure_overcommit_ratio",
                               is_make=True)

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_1",
                  "reconfigure_keystone_to_use_ldap"])
    @log_snapshot_after_test
    def reconfigure_keystone_to_use_ldap(self):
        """Reconfigure keystone to use LDAP

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration
            3. Try to apply a new keystone configuration
            4. Wait for finishing of the apply configuration task
            5. Verify configuration file on primary controller

        Snapshot: reconfigure_keystone_to_use_ldap

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")
        cluster_id = self.fuel_web.get_last_created_cluster()
        devops_pr_controller = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        pr_controller = self.fuel_web.get_nailgun_node_by_devops_node(
            devops_pr_controller)

        self.show_step(2)
        config = utils.get_config_template('keystone_ldap')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(
            config,
            cluster_id)

        self.show_step(3)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(4)
        self.fuel_web.task_wait(task, timeout=3600, interval=30)

        self.show_step(5)
        self.check_config_on_remote([pr_controller], structured_config)
        logger.info("New configuration was applied")

        self.env.make_snapshot("reconfigure_keystone_to_use_ldap")

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_2",
                  "reconfigure_nova_quota"])
    @log_snapshot_after_test
    def reconfigure_nova_quota(self):
        """Tests for reconfiguration nova quota.

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration
            3. Get uptime of process "nova-api" on each controller
            4. Apply a new quota driver and quota_instances to all nodes
            5. Wait for configuration applying
            6. Verify uptime of process "nova-api" on each controller
            7. Verify nova config settings
            8. Create new instance
            9. Try to create one more, verify that it is impossible

        Snapshot: reconfigure_nova_quota

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        self.show_step(2)
        config = utils.get_config_template('nova_quota')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(3)
        uptimes = self.get_service_uptime(controllers, 'nova-api')

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(6)
        self.check_service_was_restarted(controllers, uptimes, 'nova-api')

        self.show_step(7)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(8)
        self.show_step(9)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.check_nova_quota(os_conn, cluster_id)

        self.env.make_snapshot("reconfigure_nova_quota")

    @test(depends_on_groups=['reconfigure_overcommit_ratio'],
          groups=["services_reconfiguration_thread_1",
                  "reconfigure_nova_ephemeral_disk"])
    @log_snapshot_after_test
    def reconfigure_nova_ephemeral_disk(self):
        """Reconfigure nova ephemeral disk format

        Scenario:
            1. Revert snapshot reconfigure_overcommit_ratio
            2. Delete previous OpenStack config
            3. Upload a new openstack configuration for nova on computes
            4. Apply configuration
            5. Wait for configuration applying
            6. Get uptime of process "nova-compute" on each compute
            7. Verify nova-compute settings
            8. Create flavor with ephemral disk,
            9. Boot instance on updated compute with ephemral disk,
            10. Assign floating ip,
            11. Check ping to the instance,
            12. SSH to VM and check ephemeral disk format

        Snapshot: reconfigure_nova_ephemeral_disk

        """
        self.check_run('reconfigure_nova_ephemeral_disk')
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("reconfigure_overcommit_ratio")

        cluster_id = self.fuel_web.get_last_created_cluster()
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])

        self.show_step(2)
        existing_configs = self.fuel_web.client.list_configuration(
            cluster_id)
        for existing_config in existing_configs:
            self.fuel_web.client.delete_configuration(existing_config["id"])

        self.show_step(3)
        config = utils.get_config_template('nova_disk')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config,
                                                  cluster_id,
                                                  role='compute')

        service_name = "nova-compute"

        uptimes = self.get_service_uptime(computes, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role='compute')
        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(6)
        self.check_service_was_restarted(computes, uptimes, service_name)

        self.show_step(7)
        self.check_config_on_remote(computes, structured_config)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.show_step(12)
        self.check_nova_ephemeral_disk(os_conn, cluster_id)

        self.env.make_snapshot("reconfigure_nova_ephemeral_disk",
                               is_make=True)

    @test(depends_on_groups=['reconfigure_ml2_vlan_range'],
          groups=["services_reconfiguration_thread_1",
                  "preservation_config_after_reset_and_preconfigured_deploy"])
    @log_snapshot_after_test
    def preservation_config_after_reset_and_preconfigured_deploy(self):
        """Preservation config after reset of cluster and preconfigured deploy

        Scenario:
            1. Revert snapshot reconfigure_ml2_vlan_range
            2. Reset cluster
            3. Upload a new openstack configuration for nova
            4. Deploy changes
            5. Run OSTF
            6. Verify nova and neutron settings
            7. Create new private network
            8. Try to create one more, verify that it is impossible
            9. Boot instances with flavor that occupy all CPU
            10. Boot extra instance and catch the error

        Snapshot "preservation_config_after_reset_and_preconfigured_deploy"

        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("reconfigure_ml2_vlan_range")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        self.fuel_web.stop_reset_env_wait(cluster_id)

        self.show_step(3)
        config = utils.get_config_template('nova_cpu')
        structured_config_nova = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config,
                                                  cluster_id,
                                                  role='controller')
        config = utils.get_config_template('neutron')
        structured_config_neutron = get_structured_config_dict(config)

        self.show_step(4)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:4], timeout=10 * 60)

        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.show_step(6)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        structured_config = {}
        structured_config.update(structured_config_neutron)
        structured_config.update(structured_config_nova)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(7)
        self.show_step(8)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.check_ml2_vlan_range(os_conn)

        self.show_step(9)
        self.show_step(10)
        self.check_overcommit_ratio(os_conn, cluster_id)

        snapshot = "preservation_config_after_reset_and_preconfigured_deploy"
        self.env.make_snapshot(snapshot, is_make=True)

    @test(depends_on_groups=['reconfigure_nova_ephemeral_disk'],
          groups=["services_reconfiguration_thread_1",
                  "reconfiguration_scalability"])
    @log_snapshot_after_test
    def reconfiguration_scalability(self):
        """Check scalability of configured environment

        Scenario:
            1. Revert snapshot "reconfigure_nova_ephemeral_disk"
            2. Upload a new openstack configuration for keystone
            3. Wait for configuration applying
            4. Verify keystone settings
            5. Keystone actions
            6. Add 1 compute and 1 controller to cluster
            7. Run network verification
            8. Deploy changes
            9. Run OSTF tests
            10. Verify keystone settings
            11. Verify nova settings
            12. Create flavor with ephemral disk
            13. Boot instance on updated compute with ephemral disk
            14. Assign floating ip
            15. Check ping to the instance
            16. SSH to VM and check ephemeral disk format
            17. Keystone actions

        Snapshot "reconfiguration_scalability"
        """

        self.check_run('reconfiguration_scalability')
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("reconfigure_nova_ephemeral_disk")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        config = utils.get_config_template('nova_disk')
        structured_config_nova = get_structured_config_dict(config)
        config = utils.get_config_template('keystone')
        structured_config_keystone = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config,
                                                  cluster_id,
                                                  role='controller')
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        self.show_step(3)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role='controller')
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(4)
        self.check_config_on_remote(controllers, structured_config_keystone)

        self.show_step(5)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        time_expiration = config[
            'keystone_config']['token/expiration']['value']
        self.check_token_expiration(os_conn, time_expiration)

        self.show_step(6)
        bs_nodes = [x for x in self.env.d_env.get_nodes()
                    if x.name == 'slave-05' or x.name == 'slave-06']
        self.env.bootstrap_nodes(bs_nodes)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-05': ['compute', 'cinder']})
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-06': ['controller']})

        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(9)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(10)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        target_controller = [x for x in controllers
                             if 'slave-06' in x['name']]
        target_compute = [x for x in computes
                          if 'slave-05' in x['name']]
        self.check_config_on_remote(target_controller,
                                    structured_config_keystone)

        self.show_step(11)
        self.check_config_on_remote(target_compute, structured_config_nova)

        self.show_step(12)
        self.show_step(13)
        self.show_step(14)
        self.show_step(15)
        self.show_step(16)

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        hypervisor_name = target_compute[0]['fqdn']
        self.check_nova_ephemeral_disk(os_conn, cluster_id,
                                       hypervisor_name=hypervisor_name)

        self.show_step(17)
        self.check_token_expiration(os_conn, time_expiration)

        self.env.make_snapshot("reconfiguration_scalability", is_make=True)

    @test(depends_on_groups=['reconfiguration_scalability'],
          groups=["services_reconfiguration_thread_1",
                  "multiple_apply_config"])
    @log_snapshot_after_test
    def multiple_apply_config(self):
        """Multiple serial applying of configuration

        Scenario:
            1. Revert snapshot "reconfiguration_scalability"
            2. Upload a new openstack configuration for certain compute
            3. Get uptime of process "nova-compute" on target compute
            4. Wait for configuration applying
            5. Get uptime of process "nova-compute" on target compute
            6. Verify nova settings on each compute
            7. Create flavor with ephemeral disk
            8. Boot instance on nontarget compute with ephemral disk
            9. Assign floating ip
            10. Check ping to the instance
            11. SSH to VM and check ephemeral disk format
            12. Boot instance on target compute with ephemeral disk
            13. Assign floating ip
            14. Check ping to the instance
            15. SSH to VM and check ephemeral disk format

        Snapshot "multiple_apply_config"
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("reconfiguration_scalability")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        target_compute = computes[0]
        config = utils.get_config_template('nova_disk')
        structured_config_old = get_structured_config_dict(config)

        config['nova_config'][
            'DEFAULT/default_ephemeral_format']['value'] = 'ext3'
        structured_config_new = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config,
                                                  cluster_id,
                                                  node_id=target_compute['id'])

        self.show_step(3)
        service_name = 'nova-compute'
        uptimes = self.get_service_uptime([target_compute], service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(
            cluster_id,
            node_id=target_compute['id'])
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(5)
        self.check_service_was_restarted([target_compute],
                                         uptimes, service_name)

        self.show_step(6)
        for compute in computes:
            if compute == target_compute:
                self.check_config_on_remote([compute], structured_config_new)
                target_hypervisor_name = compute['fqdn']
            else:
                hypervisor_name = compute['fqdn']
                self.check_config_on_remote([compute], structured_config_old)

        self.show_step(7)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.check_nova_ephemeral_disk(os_conn, cluster_id,
                                       hypervisor_name=target_hypervisor_name,
                                       fs_type='ext3')
        self.show_step(12)
        self.show_step(13)
        self.show_step(14)
        self.show_step(15)
        self.check_nova_ephemeral_disk(os_conn, cluster_id,
                                       hypervisor_name=hypervisor_name)

        self.env.make_snapshot("multiple_apply_config")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["services_reconfiguration_thread_2",
                  "two_clusters_reconfiguration"])
    @log_snapshot_after_test
    def two_clusters_reconfiguration(self):
        """Deploy two clusters with different configs

         Scenario:
             1. Revert snapshot "ready_with_5_slaves"
             2. Divided the IP ranges into two parts
             3. Verify network of the first environment
             4. Verify network of the second environment
             5. Deploy environment with first ranges
             6. Run OSTF on the first environment
             7. Deploy environment with second ranges
             8. Run OSTF on the second environment
             9. Apply new CPU overcommit ratio for first environment
             10. Verify deployment task is finished
             11. Verify nova-scheduler services uptime
             12. Verify configuration file on controller
             13. Boot instances with flavor that occupy all CPU,
                 boot extra instance and catch the error
             14. Apply old CPU overcommit ratio for each controller
             15. Verify deployment task is finished
             16. Verify nova-scheduler services uptime
             17. Verify configuration file on each controller

        Snapshot "two_clusters_reconfiguration"

        """

        self.show_step(1)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(2)
        cluster_id_1 = self.fuel_web.create_cluster(
            name="env1",
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE,
            }
        )
        cluster_id_2 = self.fuel_web.create_cluster(
            name="env2",
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE,
            }
        )

        self.fuel_web.update_nodes(
            cluster_id_1,
            {
                'slave-01': ['compute'],
                'slave-02': ['controller']
            })

        self.fuel_web.update_nodes(
            cluster_id_2,
            {
                'slave-03': ['compute'],
                'slave-04': ['controller']
            })

        networks_1 = self.fuel_web.client.get_networks(
            cluster_id_1)["networks"]
        self.change_default_range(networks_1,
                                  number_excluded_ips=30,
                                  cut_from_start=True)
        helpers.wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")
        floating_list = [self.fuel_web.get_floating_ranges()[0][0]]
        networking_parameters = {
            "floating_ranges": floating_list}
        self.fuel_web.client.update_network(
            cluster_id_1,
            networks=networks_1,
            networking_parameters=networking_parameters
        )

        networks_2 = self.fuel_web.client.get_networks(
            cluster_id_2)["networks"]
        self.change_default_range(networks_2,
                                  number_excluded_ips=30,
                                  cut_from_start=False)
        helpers.wait(lambda: not self.is_update_dnsmasq_running(
            self.fuel_web.client.get_tasks()), timeout=60,
            timeout_msg="Timeout exceeded while waiting for task "
                        "'update_dnsmasq' is finished!")
        floating_list = [self.fuel_web.get_floating_ranges()[0][1]]

        vlan_range_1 = self.fuel_web.client.get_networks(
            cluster_id_1)["networking_parameters"]["vlan_range"]
        vlan_range_2 = [vlan_range_1[-1] + 1, vlan_range_1[-1] + 31]

        networking_parameters = {
            "floating_ranges": floating_list,
            "vlan_range": vlan_range_2}
        self.fuel_web.client.update_network(
            cluster_id_2,
            networks=networks_2,
            networking_parameters=networking_parameters
        )
        self.show_step(3)
        self.fuel_web.verify_network(cluster_id_1)
        self.show_step(4)
        self.fuel_web.verify_network(cluster_id_2)
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id_1, check_services=False)
        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id_1)
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id_2, check_services=False)
        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id_2)

        self.show_step(9)
        config_new = utils.get_config_template('nova_cpu')
        structured_config = get_structured_config_dict(config_new)
        self.fuel_web.client.upload_configuration(config_new,
                                                  cluster_id_1)

        service_name = "nova-scheduler"

        controller_env_1 = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id_1, ['controller'])
        controller_env_2 = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id_2, ['controller'])
        uptimes = self.get_service_uptime(controller_env_1, service_name)
        task = self.fuel_web.client.apply_configuration(cluster_id_1,
                                                        role="controller")

        self.show_step(10)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(11)
        self.check_service_was_restarted(controller_env_1,
                                         uptimes,
                                         service_name)

        self.show_step(12)
        self.check_config_on_remote(controller_env_1, structured_config)

        self.show_step(13)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id_1))

        self.check_overcommit_ratio(os_conn, cluster_id_1)

        self.show_step(14)
        config_revert = utils.get_config_template('nova_cpu_old')
        structured_config_revert = get_structured_config_dict(config_revert)
        self.fuel_web.client.upload_configuration(config_revert,
                                                  cluster_id_2)
        uptimes = self.get_service_uptime(controller_env_2, service_name)
        task = self.fuel_web.client.apply_configuration(cluster_id_2,
                                                        role="controller")
        self.show_step(15)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(16)
        self.check_service_was_restarted(controller_env_2,
                                         uptimes,
                                         service_name)

        self.show_step(17)
        self.check_config_on_remote(controller_env_2,
                                    structured_config_revert)

        self.env.make_snapshot("two_clusters_reconfiguration")

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_2",
                  "upload_config_for_node_and_env_in_transitional_state"])
    @log_snapshot_after_test
    def upload_config_for_node_and_env_in_transitional_state(self):
        """Upload config for node and env in transitional state

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Add 1 compute
            3. Deploy changes
            4. Upload a new openstack configuration for env
            5. Check nailgun response
            6. Wait for added node in provisioning state
            7. Upload a new openstack configuration for node
            8. Check Nailgun response
            9. Wait for added node in deploying state
            10. Upload a new openstack configuration for node
            11. Check Nailgun response
            12. Wait for finishing of deployment

        Snapshot: upload_config_for_node_and_env_in_transitional_state

        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        bs_node = [
            node for node in self.env.d_env.get_nodes()
            if node.name == 'slave-05']
        self.env.bootstrap_nodes(bs_node)
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-05': ['compute']})
        target_node = bs_node[0]
        target_node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            target_node)['id']

        config = {'nova_config': {'foo': {'value': 'bar'}}}

        self.show_step(3)
        task = self.fuel_web.deploy_cluster(cluster_id)
        # wait for creation of child 'deployment' task
        self.fuel_web.wait_for_tasks_presence(self.fuel_web.client.get_tasks,
                                              name='deployment',
                                              parent_id=task.get('id'))

        self.show_step(4)
        self.show_step(5)
        expected_code = 403
        err_msg = 'A configuration was applied for env in deploying state'
        self.check_response_code(
            expected_code, err_msg,
            self.fuel_web.client.upload_configuration,
            config, cluster_id)

        self.show_step(6)
        self.wait_for_node_status(target_node, 'provisioning')

        self.show_step(7)
        self.show_step(8)
        err_msg = 'A configuration was applied for node in provisioning state'
        self.check_response_code(
            expected_code, err_msg,
            self.fuel_web.client.upload_configuration,
            config, cluster_id, node_id=target_node_id)

        self.show_step(9)
        self.wait_for_node_status(target_node, 'deploying')

        self.show_step(10)
        self.show_step(11)
        err_msg = 'A configuration was applied for node in deploying state'
        self.check_response_code(
            expected_code, err_msg,
            self.fuel_web.client.upload_configuration,
            config, cluster_id, node_id=target_node_id)

        self.show_step(12)
        self.fuel_web.assert_task_success(task, timeout=7800, interval=30)

        snapshot_name = "upload_config_for_node_and_env_in_transitional_state"
        self.env.make_snapshot(snapshot_name)

    @test(depends_on_groups=['reconfiguration_scalability'],
          groups=["services_reconfiguration_thread_1",
                  "apply_config_for_node_with_multiple_role"])
    @log_snapshot_after_test
    def apply_config_for_node_with_multiple_role(self):
        """Apply config for node with multiple role

        Scenario:
            1. Revert snapshot "reconfiguration_scalability"
            2. Upload a new openstack configuration for compute role
            3. Upload a new openstack configuration for cinder role
            4. Wait for configuration applying
            5. Get uptime of process "nova-compute"
            6. Check settings on target node

        Snapshot "apply_config_for_node_with_multiple_role"
        """

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("reconfiguration_scalability")

        cluster_id = self.fuel_web.get_last_created_cluster()
        target_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute', 'cinder'])
        config_for_compute_role = utils.get_config_template('nova_disk')
        config_for_compute_role['nova_config'].update(
            {'DEFAULT/debug': {'value': 'False'}})
        config_for_cinder_role = utils.get_config_template(
            'nova_disk_cinder_role')

        self.show_step(2)
        self.fuel_web.client.upload_configuration(config_for_compute_role,
                                                  cluster_id,
                                                  role='compute')

        self.show_step(3)
        self.fuel_web.client.upload_configuration(config_for_cinder_role,
                                                  cluster_id,
                                                  role='cinder')

        # Configs are merging with ID-priority
        general_config = {}
        general_config.update(config_for_compute_role)
        general_config.update(config_for_cinder_role)
        structured_config = get_structured_config_dict(general_config)
        service_name = 'nova-compute'
        uptime = self.get_service_uptime(target_node, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(
            cluster_id,
            node_id=target_node[0]['id'])
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(5)
        self.check_service_was_restarted(target_node,
                                         uptime,
                                         service_name)

        self.show_step(6)
        self.check_config_on_remote(target_node, structured_config)

        snapshot_name = "apply_config_for_node_with_multiple_role"
        self.env.make_snapshot(snapshot_name)

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_2",
                  "reconfigure_with_new_fields"])
    @log_snapshot_after_test
    def reconfigure_with_new_fields(self):
        """Reconfigure services with new fields

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration for controller
            3. Get uptime of processes from config on each controller
            4. Apply a new openstack configuration for controller
            5. Check that neutron related services were restarted
            6. Verify configuration file on each controller
            7. Upload a new openstack configuration for compute
            8. Get uptime of nova-compute on each compute
            9. Apply a new openstack configuration for compute
            10. Check that nova-compute service was restarted
            11. Verify configuration file on each compute

        Snapshot: reconfigure_with_new_fields

        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        self.show_step(2)
        config_controller = utils.get_config_template('new_fields_controller')
        structured_config = get_structured_config_dict(config_controller)
        self.fuel_web.client.upload_configuration(config_controller,
                                                  cluster_id,
                                                  role="controller")

        self.show_step(3)
        service_list = ['neutron-server', 'neutron-dhcp-agent',
                        'neutron-l3-agent', 'neutron-metadata-agent',
                        'nova-scheduler', 'nova-novncproxy', 'nova-conductor',
                        'nova-api', 'nova-consoleauth', 'nova-cert']
        services_uptime = {}
        for service_name in service_list:
            services_uptime[service_name] = self.get_service_uptime(
                controllers, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(5)
        for service_name in service_list:
            self.check_service_was_restarted(
                controllers,
                services_uptime[service_name],
                service_name)

        self.show_step(6)
        self.check_config_on_remote(controllers, structured_config)

        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])

        self.show_step(7)
        config_copmute = utils.get_config_template('new_fields_compute')
        structured_config = get_structured_config_dict(config_copmute)
        self.fuel_web.client.upload_configuration(config_copmute, cluster_id)

        self.show_step(8)
        uptimes_nova = self.get_service_uptime(computes, 'nova-compute')

        self.show_step(9)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role='compute')
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(10)
        self.check_service_was_restarted(computes,
                                         uptimes_nova,
                                         'nova-compute')

        self.show_step(11)
        self.check_config_on_remote(computes, structured_config)
        self.env.make_snapshot("reconfigure_with_new_fields")

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration_thread_2",
                  "reconfigure_ml2_vlan_range_for_suite_of_nodes"])
    @log_snapshot_after_test
    def reconfigure_ml2_vlan_range_for_suite_of_nodes(self):
        """Reconfigure neutron ml2 VLAN range for suite of controller nodes

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new VLAN range(minimal range) for suite of controller
               nodes
            3. Get uptime of process "neutron-server" on each controller
            4. Apply a new openstack configuration to all controller nodes
            5. Wait for configuration applying
            6. Check that service "neutron-server" was restarted
            7. Verify ml2 plugin settings
            8. Try to create two private networks, check that the second
               network is failed to create

        Snapshot: reconfigure_ml2_vlan_range_for_suite_of_nodes

        """
        self.show_step(1)
        self.env.revert_snapshot("basic_env_for_reconfiguration")
        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        controller_ids = [int(ctrl['id']) for ctrl in controllers]

        self.show_step(2)
        config = utils.get_config_template('neutron')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config,
                                                  cluster_id,
                                                  node_ids=controller_ids)

        self.show_step(3)
        service_name = 'neutron-server'
        uptimes = self.get_service_uptime(controllers, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=900, interval=5)

        self.show_step(6)
        self.check_service_was_restarted(controllers, uptimes, service_name)

        self.show_step(7)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(8)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.check_ml2_vlan_range(os_conn)

        snapshotname = "reconfigure_ml2_vlan_range_for_suite_of_nodes"
        self.env.make_snapshot(snapshotname)
