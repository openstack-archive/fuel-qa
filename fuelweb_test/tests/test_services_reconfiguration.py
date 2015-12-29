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

import time
import random

from devops.helpers import helpers
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


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
                d['value'] = v
            structured_conf[key2].append(d)

    for key in config.keys():
        if key == 'neutron_config':
            helper(key, '/etc/neutron/neutron.conf')
        if key == 'neutron_plugin_ml2':
            helper(key, '/etc/neutron/plugins/ml2/ml2_conf.ini')
        if key == 'nova_config':
            helper(key, '/etc/nova/nova.conf')
    return structured_conf


@test(groups=["services_reconfiguration"])
class ServicesReconfiguration(TestBasic):
    """ServicesReconfiguration."""

    def get_service_uptime(self, nodes, service_name):
        """
        :param nodes: a list of nailgun nodes
        :param service_name: a string of service name
        :return: a dictionary of ip nodes and process uptime
        """
        nodes = [x['ip'] for x in nodes]
        uptimes = dict(zip(nodes, range(len(nodes))))
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

        creds = ("cirros", "cubswin:)")
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]['ip']
        with self.env.d_env.get_ssh_to_remote(controller) as remote:
            res = os_conn.execute_through_host(
                remote, floating_ip.ip, "mount", creds)
            asserts.assert_true('/mnt type {0}'.format(fs_type)
                                in res['stdout'],
                                "Ephemeral disk format was not "
                                "changed on instance")
        os_conn.delete_instance(instance)

    def check_ml2_vlan_range(self, os_conn):
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
                raise e
            pass
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
                raise e
            pass
        else:
            raise Exception("New configuration was not applied")

    def check_token_expiration(self, os_conn, time_expiration):
        """
        :param os_conn: an object of connection to openstack services
        :param time_expiration: an integer value of token time expiration
               in seconds
        :return:
        """
        token = os_conn.keystone.tokens.authenticate(username='admin',
                                                     password='admin')
        time.sleep(time_expiration)
        try:
            os_conn.keystone.tokens.validate(token.id)
        except Exception as e:
            if e.http_status != 404:
                raise e
            pass
        else:
            raise Exception("New configuration was not applied")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["services_reconfiguration", "basic_env_for_reconfiguration"])
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

        self.show_step(1)
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
          groups=["services_reconfiguration", "reconfigure_ml2_vlan_range"])
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
        self.show_step(1)
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
        task = self.fuel_web.client.apply_configuration(cluster_id)

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

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
          groups=["services_reconfiguration", "reconfigure_overcommit_ratio"])
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
        self.show_step(1)
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
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

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
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(9)
        self.check_service_was_restarted(controllers, uptimes, service_name)

        self.show_step(10)
        self.check_config_on_remote(controllers, structured_config_revert)

        self.env.make_snapshot("reconfigure_overcommit_ratio",
                               is_make=True)

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration",
                  "reconfigure_keystone_to_use_ldap"])
    @log_snapshot_after_test
    def reconfigure_keystone_to_use_ldap(self):
        """Reconfigure keystone to use LDAP

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration
            3. Try to apply a new keystone configuration
            4. Wait for failing of deployment task
            5. Check that reason of failing is impossibility of
               the connection to LDAP server

        Snapshot: reconfigure_keystone_to_use_ldap

        """
        self.show_step(1)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        ldap_cntrllr = controllers[0]

        self.show_step(2)
        config = utils.get_config_template('keystone_ldap')
        self.fuel_web.client.upload_configuration(
            config,
            cluster_id,
            node_id=ldap_cntrllr['id'])

        self.show_step(3)
        task = self.fuel_web.client.apply_configuration(
            cluster_id,
            node_id=ldap_cntrllr['id'])

        self.show_step(4)
        try:
            self.fuel_web.assert_task_success(task, timeout=1800, interval=30)
        except AssertionError:
            pass
        else:
            raise Exception("New configuration was not applied")

        self.show_step(5)
        with self.env.d_env.get_ssh_to_remote(ldap_cntrllr['ip']) as remote:
            log_path = '/var/log/puppet.log'
            cmd = "grep \"Can't contact LDAP server\" {0}".format(log_path)
            utils.run_on_remote_get_results(remote, cmd)

        self.env.make_snapshot("reconfigure_keystone_to_use_ldap")

    @test(depends_on_groups=['basic_env_for_reconfiguration'],
          groups=["services_reconfiguration", "reconfigure_nova_quota"])
    @log_snapshot_after_test
    def reconfigure_nova_quota(self):
        """Tests for reconfiguration nova quota.

        Scenario:
            1. Revert snapshot "basic_env_for_reconfiguration"
            2. Upload a new openstack configuration
            3. Get uptime of process "nova-api" on each controller
            4. Get uptime of process "nova-compute" on each compute
            5. Apply a new quota driver and quota_instances to all nodes
            6. Wait for configuration applying
            7. Verify uptime of process "nova-api" on each controller
            8. Verify uptime of process "nova-compute" on each compute
            9. Verify nova config settings
            10. Create new instance
            11. Try to create one more, verify that it is impossible

        Snapshot: reconfigure_nova_quota

        """
        self.show_step(1)
        self.env.revert_snapshot("basic_env_for_reconfiguration")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])

        self.show_step(2)
        config = utils.get_config_template('nova_quota')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(3)
        uptimes = self.get_service_uptime(controllers, 'nova-api')

        self.show_step(4)
        uptimes_comp = self.get_service_uptime(computes, 'nova-compute')

        self.show_step(5)
        task = self.fuel_web.client.apply_configuration(cluster_id)

        self.show_step(6)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(7)
        self.check_service_was_restarted(controllers, uptimes, 'nova-api')

        self.show_step(8)
        self.check_service_was_restarted(computes, uptimes_comp,
                                         'nova-compute')

        self.show_step(9)
        self.check_config_on_remote(controllers, structured_config)

        self.show_step(10)
        self.show_step(11)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.check_nova_quota(os_conn, cluster_id)

        self.env.make_snapshot("reconfigure_nova_quota")

    @test(depends_on_groups=['reconfigure_overcommit_ratio'],
          groups=["services_reconfiguration",
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
        self.show_step(1)
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
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

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
          groups=["services_reconfiguration",
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

        self.show_step(1)
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
          groups=["services_reconfiguration",
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
        self.show_step(1)
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
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

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
            {'slave-05': ['compute']})
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

    @test(depends_on_groups=['reconfigurstion_scalability'],
          groups=["services_reconfiguration",
                  "multiple_apply_config"])
    @log_snapshot_after_test
    def multiple_apply_config(self):
        """Multiple serial applying of configuration

        Scenario:
            1. Revert snapshot "reconfigurstion_scalability"
            2. Upload a new openstack configuration for certain compute
            3. Get uptime of process "nova-compute" on target compute
            4. Wait for configuration applying
            5. Get uptime of process "nova-compute" on target compute
            6. Verify nova settings on each compute
            7. Create flavor with ephemral disk
            8. Boot instance on untarget compute with ephemral disk
            9. Assign floating ip
            10. Check ping to the instance
            11. SSH to VM and check ephemeral disk format
            13. Boot instance on target compute with ephemral disk
            14. Assign floating ip
            15. Check ping to the instance
            16. SSH to VM and check ephemeral disk format

        Snapshot "multiple_apply_config"
        """

        self.show_step(1)
        self.env.revert_snapshot("reconfiguration_scalability")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])
        target_compute = [computes[0]]
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
        uptimes = self.get_service_uptime(target_compute, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(
            cluster_id,
            node_id=target_compute['id'])
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(5)
        self.check_service_was_restarted(target_compute,
                                         uptimes, service_name)

        self.show_step(6)
        for compute in computes:
            if compute == target_compute:
                self.check_config_on_remote(compute, structured_config_new)
                taget_hypervisor_name = compute['fqdn']
            else:
                hypervisor_name = compute['fqdn']
                self.check_config_on_remote(compute, structured_config_old)

        self.show_step(7)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.check_nova_ephemeral_disk(os_conn, cluster_id,
                                       hypervisor_name=taget_hypervisor_name,
                                       fs_type='ext3')
        self.show_step(12)
        self.show_step(13)
        self.show_step(14)
        self.show_step(15)
        self.check_nova_ephemral_disk(os_conn, cluster_id,
                                      hypervisor_name=hypervisor_name)

        self.env.make_snapshot("multiple_apply_config")
