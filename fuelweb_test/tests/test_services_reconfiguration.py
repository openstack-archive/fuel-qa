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
from devops import error
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

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["services_reconfiguration", "reconfigure_ml2_vlan_range"])
    @log_snapshot_after_test
    def reconfigure_ml2_vlan_range(self):
        """Reconfigure neutron ml2 VLAN range

        Scenario:
            1. Revert snapshot "deploy_neutron_vlan_ha"
            2. Upload a new openstack configuration
            3. Get uptime of process "neutron-server" on each controller
            4. Apply a new VLAN range(minimal range) to all nodes
            5. Wait for configuration applying
            6. Verify ml2 plugin settings
            7. Create new private network
            8. Try to create one more, verify that it is impossible

        Snapshot reconfigure_ml2_vlan_range

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        controllers = [x['ip'] for x in controllers]

        self.show_step(2)
        config = utils.get_config_template('neutron')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(3)
        uptimes = dict(zip(controllers, range(len(controllers))))
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptimes[controller] = \
                    utils.get_process_uptime(remote, 'neutron-server')

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id)

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(6)
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptime = utils.get_process_uptime(remote, 'neutron-server')
                asserts.assert_true(uptime <= uptimes[controller],
                                    'Service "neutron-servers" was not '
                                    'restarted on {0}'.format(controller))
                for configpath, params in structured_config.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])

        self.show_step(7)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        tenant = os_conn.get_tenant('admin')
        os_conn.create_network('net1', tenant_id=tenant.id)

        self.show_step(8)
        try:
            os_conn.create_network('net2', tenant_id=tenant.id)
        except Exception as e:
            if 'No tenant network is available' not in e.message:
                raise e
            pass
        else:
            raise Exception("New configuration was not applied")

        self.env.make_snapshot("reconfigure_ml2_vlan_range", is_make=True)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["services_reconfiguration", "reconfigure_overcommit_ratio"])
    @log_snapshot_after_test
    def reconfigure_overcommit_ratio(self):
        """Tests for reconfiguration nova CPU overcommit ratio.

        Scenario:
            1. Create cluster
            2. Add 1 node with compute role
            3. Add 3 nodes with controller role
            4. Deploy the cluster
            5. Verify network
            6. Run OSTF
            7. Verify configuration file on each controller
            8. Apply new CPU overcommit ratio for each controller
            9. Verify deployment task is finished
            10. Verify nova-scheduler services uptime
            11. Boot instances with flavor that occupy all CPU
            12. Boot extra instance and catch the error
            13. Apply old CPU overcommit ratio for each controller
            14. Verify deployment task is finished
            15. Verify nova-scheduler services uptime

        Snapshot: reconfigure_overcommit_ratio

        """
        snapshot_name = 'reconfigure_overcommit_ratio'
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

        self.show_step(7)
        config_new = utils.get_config_template('nova_cpu')
        structured_config = get_structured_config_dict(config_new)
        self.fuel_web.client.upload_configuration(config_new,
                                                  cluster_id,
                                                  role="controller")

        service_name = "nova-scheduler"

        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        controllers = [x['ip'] for x in controllers]
        uptimes = dict(zip(controllers, range(len(controllers))))
        self.show_step(8)
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptimes[controller] = \
                    utils.get_process_uptime(remote, service_name)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(9)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(10)

        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptime = utils.get_process_uptime(remote, service_name)
                asserts.assert_true(uptime <= uptimes[controller],
                                    "Service {0} was not restarted "
                                    "on {1}".format(controller, service_name))
                for configpath, params in structured_config.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])

        self.show_step(11)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        server = os_conn.create_instance(neutron_network=True,
                                         label=net_name,
                                         server_name="Test_reconfig",
                                         vcpus=2)
        os_conn.verify_instance_status(server, 'ACTIVE')
        self.show_step(12)
        excessive_server = os_conn.create_instance(neutron_network=True,
                                                   label=net_name,
                                                   server_name="excessive_VM",
                                                   flavor_name="overcommit")
        os_conn.verify_instance_status(excessive_server, 'ERROR')
        os_conn.delete_instance(excessive_server)
        os_conn.delete_instance(server)

        self.show_step(13)
        config_revert = utils.get_config_template('nova_cpu_old')
        structured_config_revert = get_structured_config_dict(config_revert)
        self.fuel_web.client.upload_configuration(config_revert,
                                                  cluster_id,
                                                  role="controller")
        uptimes = dict(zip(controllers, range(len(controllers))))
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptimes[controller] = \
                    utils.get_process_uptime(remote, service_name)

        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role="controller")

        self.show_step(14)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(15)
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptime = utils.get_process_uptime(remote, service_name)
                asserts.assert_true(uptime <= uptimes[controller],
                                    "Service {0} was not restarted "
                                    "on {1}".format(controller, service_name))
                for configpath, params in structured_config_revert.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])
        self.env.make_snapshot("reconfigure_overcommit_ratio",
                               is_make=True)

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["services_reconfiguration",
                  "reconfigure_keystone_to_use_ldap"])
    @log_snapshot_after_test
    def reconfigure_keystone_to_use_ldap(self):
        """Reconfigure neutron ml2 VLAN range

        Scenario:
            1. Revert snapshot "deploy_neutron_vlan_ha"
            2. Upload a new openstack configuration
            3. Try to apply a new keystone configuration
            4. Wait for failing of deployment task
            5. Check that reason of failing is impossibility of
               the connection to LDAP server

        Snapshot reconfigure_keystone_to_use_ldap

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

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

        self.env.make_snapshot("reconfigure_keystone_to_use_ldap",
                               is_make=True)

    @test(depends_on_groups=['deploy_neutron_vlan_ha'],
          groups=["reconfiguration", "reconfigure_nova_quota"])
    @log_snapshot_after_test
    def reconfigure_nova_quota(self):
        """Tests for reconfiguration nova quota.

        Scenario:
            1. Revert snapshot "deploy_neutron_vlan_ha"
            2. Upload a new openstack configuration
            3. Get uptime of process "nova-compute" on each controller
            4. Apply a new quota driver and quota_instances to all nodes
            5. Wait for configuration applying
            6. Verify nova config settings
            7. Create new instance
            8. Try to create one more, verify that it is impossible

        Snapshot: reconfigure_nova_quota

        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_neutron_vlan_ha")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        controllers = [x['ip'] for x in controllers]

        self.show_step(2)
        config = utils.get_config_template('nova_quota')
        structured_config = get_structured_config_dict(config)
        self.fuel_web.client.upload_configuration(config, cluster_id)

        self.show_step(3)
        uptimes = dict(zip(controllers, range(len(controllers))))
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptimes[controller] = \
                    utils.get_process_uptime(remote, 'nova-api')

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id)

        self.show_step(5)
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(6)
        for controller in controllers:
            with self.env.d_env.get_ssh_to_remote(controller) as remote:
                uptime = utils.get_process_uptime(remote, 'nova-api')
                asserts.assert_true(uptime <= uptimes[controller],
                                    'Service "nova-api" was not '
                                    'restarted on {0}'.format(controller))
                for configpath, params in structured_config.items():
                    result = remote.open(configpath)
                    conf_for_check = utils.get_ini_config(result)
                    for param in params:
                        utils.check_config(conf_for_check,
                                           configpath,
                                           param['section'],
                                           param['option'],
                                           param['value'])

        self.show_step(7)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        server = os_conn.create_instance(neutron_network=True,
                                         label=net_name,
                                         server_name="Test_reconfig")
        os_conn.verify_instance_status(server, 'ACTIVE')
        self.show_step(8)
        excessive_server = os_conn.create_instance(neutron_network=True,
                                                   label=net_name,
                                                   server_name="excessive_VM")
        asserts.assert_equal(excessive_server['exit_code'], 1,
                             'Quota_instances was not applied')
        self.env.make_snapshot("reconfigure_nova_quota",
                               is_make=True)

    @test(depends_on_groups=['reconfigure_overcommit_ratio'],
          groups=["services_reconfiguration",
                  "reconfigure_nova_ephemeral_disk"])
    @log_snapshot_after_test
    def reconfigure_nova_ephemral_disk(self):
        """Reconfigure nova ephemeral disk format

        Scenario:
            1. Revert snapshot reconfigure_overcommit_ratio
            2. Delete previous OpenStack config
            3. Upload a new openstack configuration for nova on computes
            4. Wait for configuration applying
            5. Get uptime of process "nova-compute" on each compute
            6. Verify nova-compute settings
            7. Create flavor with ephemral disk
            8. Boot instance on updated compute with ephemral disk
            9. Assign floating ip
            10. Check ping to the instance
            11. SSH to VM and check ephemeral disk format

        Snapshot reconfigure_nova_ephemeral_disk"

        """

        self.show_step(1)
        self.env.revert_snapshot("reconfigure_overcommit_ratio")

        cluster_id = self.fuel_web.get_last_created_cluster()
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        computes_ip = compute["ip"]

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

        with self.env.d_env.get_ssh_to_remote(computes_ip) as remote:
            uptime_before = utils.get_process_uptime(remote, service_name)

        self.show_step(4)
        task = self.fuel_web.client.apply_configuration(cluster_id,
                                                        role='compute')
        self.fuel_web.assert_task_success(task, timeout=300, interval=5)

        self.show_step(5)
        self.show_step(6)
        with self.env.d_env.get_ssh_to_remote(computes_ip) as remote:
            uptime_after = utils.get_process_uptime(remote, service_name)
            asserts.assert_true(uptime_after <= uptime_before,
                                "Service {0} was not restarted "
                                "on {1}".format(compute, service_name))
            for configpath, params in structured_config.items():
                result = remote.open(configpath)
                conf_for_check = utils.get_ini_config(result)
                for param in params:
                    utils.check_config(conf_for_check,
                                       configpath,
                                       param['section'],
                                       param['option'],
                                       param['value'])

        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        self.show_step(7)
        os_conn.create_flavor(name='ephemeral',
                              ram=64,
                              vcpus=1,
                              disk=1,
                              flavorid=6,
                              ephemeral=1)
        self.show_step(8)
        instance = os_conn.create_server_for_migration(
            neutron=True, label=net_name, flavor=6)

        self.show_step(9)
        floating_ip = os_conn.assign_floating_ip(instance)

        self.show_step(10)
        try:
            helpers.wait(lambda: helpers.tcp_ping(floating_ip.ip, 22),
                         timeout=120)
        except error.TimeoutError:
            raise error.TimeoutError('Can not ping instance by floating '
                                     'ip {0}'.format(floating_ip.ip))

        self.show_step(11)
        creds = ("cirros", "cubswin:)")
        with self.fuel_web.get_ssh_for_node("slave-02") as remote:
            res = os_conn.execute_through_host(
                remote, floating_ip.ip,
                "mount | grep 'type ext4' "
                " && echo 'OK' || echo 'FAIL'", creds)
            asserts.assert_true('OK' in res['stdout'],
                                "Ephemeral disk format was not "
                                "changed on instance")
        self.env.make_snapshot("reconfigure_nova_ephemeral_disk",
                               is_make=True)
