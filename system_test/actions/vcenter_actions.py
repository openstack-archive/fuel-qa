#    Copyright 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time

from random import randrange

from fuelweb_test.helpers.os_actions import OpenStackActions
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import NEUTRON, SERVTEST_PASSWORD, SERVTEST_TENANT,\
    SERVTEST_USERNAME
from ostf_actions import HealthCheckActions

from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true

from system_test import action
from system_test import deferred_decorator
from system_test import logger
from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
class VMwareActions(object):
    """VMware vCenter/DVS related actions."""

    plugin_version = None

    vms_to_ping = []  # instances which should ping each other
    vip_contr = None  # controller with VIP resources
    primary_ctlr_ng = None  # nailgun primary controller

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def enable_plugin(self):
        """Enable plugin for Fuel."""
        assert_true(self.plugin_name, "plugin_name is not specified")

        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)

        plugin_data = self.fuel_web.get_plugin_data(self.cluster_id,
                                                    self.plugin_name,
                                                    self.plugin_version)
        options = {'metadata/enabled': True,
                   'metadata/chosen_id': plugin_data['metadata']['plugin_id']}
        self.fuel_web.update_plugin_data(self.cluster_id,
                                         self.plugin_name, options)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_dvs_plugin(self):
        """Configure DVS plugin."""
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(
                self.cluster_id,
                self.plugin_name),
            msg)

        options = {
            'vmware_dvs_fw_driver/value': self.full_config[
                'template']['cluster_template']['settings']['vmware_dvs'][
                'dvs_fw_driver'],
            'vmware_dvs_net_maps/value': self.full_config[
                'template']['cluster_template']['settings']['vmware_dvs'][
                'dvswitch_name']
        }
        self.fuel_web.update_plugin_settings(
            self.cluster_id, self.plugin_name, self.plugin_version, options)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def configure_vcenter(self):
        """Configure vCenter settings."""
        vmware_vcenter = self.env_settings['vmware_vcenter']

        vcenter_value = {
            "glance": {"vcenter_username": "",
                       "datacenter": "",
                       "vcenter_host": "",
                       "vcenter_password": "",
                       "datastore": ""
                       },
            "availability_zones": [
                {"vcenter_username": vmware_vcenter['settings']['user'],
                 "nova_computes": [],
                 "vcenter_host": vmware_vcenter['settings']['host'],
                 "az_name": vmware_vcenter['settings']['az'],
                 "vcenter_password": vmware_vcenter['settings']['pwd']
                 }]
        }

        clusters = vmware_vcenter['nova-compute']
        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        roles = ['compute-vmware']
        comp_vmware_nodes = [n for n in nodes if set(roles) <=
                             set(n['pending_roles'])]

        for cluster in clusters:
            cluster_name = cluster['cluster']
            srv_name = cluster['srv_name']
            datastore = cluster['datastore']
            if cluster['target_node'] == 'compute-vmware':
                node = comp_vmware_nodes.pop()
                target_node = node['hostname']
            else:
                target_node = cluster['target_node']

            vcenter_value["availability_zones"][0]["nova_computes"].append(
                {"vsphere_cluster": cluster_name,
                 "service_name": srv_name,
                 "datastore_regex": datastore,
                 "target_node": {
                     "current": {"id": target_node,
                                 "label": target_node},
                     "options": [{"id": target_node,
                                  "label": target_node}, ]},
                 }
            )

        if vmware_vcenter['glance']['enable']:
            attributes = self.fuel_web.client.get_cluster_attributes(
                self.cluster_id)
            attributes['editable']['storage']['images_vcenter']['value'] =\
                vmware_vcenter['glance']['enable']
            self.fuel_web.client.update_cluster_attributes(self.cluster_id,
                                                           attributes)

            vcenter_value["glance"]["vcenter_host"] = vmware_vcenter[
                'glance']['host']
            vcenter_value["glance"]["vcenter_username"] = vmware_vcenter[
                'glance']['user']
            vcenter_value["glance"]["vcenter_password"] = vmware_vcenter[
                'glance']['pwd']
            vcenter_value["glance"]["datacenter"] = vmware_vcenter[
                'glance']['datacenter']
            vcenter_value["glance"]["datastore"] = vmware_vcenter[
                'glance']['datastore']

        logger.info('Configuring vCenter...')

        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value'] = vcenter_value
        logger.debug("Try to update cluster with next "
                     "vmware_attributes {0}".format(vmware_attr))
        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)

        logger.debug("Attributes of cluster have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def set_custom_node_names(self):
        """Set custom node names."""
        custom_hostnames = []
        for node in self.fuel_web.client.list_cluster_nodes(self.cluster_id):
            custom_hostname = "{0}-{1}".format(
                node['pending_roles'][0], randrange(0, 0xffff))
            custom_hostnames.append(custom_hostname)
            self.fuel_web.client.set_hostname(node['id'], custom_hostname)

    @staticmethod
    def get_nova_conf_dict(az, nova):
        """Return nova conf_dict.

        :param az: vcenter az (api), dict
        :param nova:  nova (api), dict
        :return: dict
        """
        conf_dict = {
            'host': 'vcenter-{}'.format(nova['service_name']),
            'cluster_name': nova['vsphere_cluster'],
            'datastore_regex': nova['datastore_regex'],
            'host_username': az['vcenter_username'],
            'host_password': az['vcenter_password'],
            'host_ip': az['vcenter_host']
        }
        return conf_dict

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_conf(self):
        """Verify nova-compute vmware configuration."""
        nodes = self.fuel_web.client.list_cluster_nodes(self.cluster_id)
        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        az = vmware_attr['editable']['value']['availability_zones'][0]
        nova_computes = az['nova_computes']

        data = []
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        for nova in nova_computes:
            target_node = nova['target_node']['current']['id']
            if target_node == 'controllers':
                conf_path = '/etc/nova/nova-compute.d/vmware-vcenter_{0}.' \
                            'conf'.format(nova['service_name'])
                for node in ctrl_nodes:
                    hostname = node['hostname']
                    ip = node['ip']
                    conf_dict = self.get_nova_conf_dict(az, nova)
                    params = (hostname, ip, conf_path, conf_dict)
                    data.append(params)
            else:
                conf_path = '/etc/nova/nova-compute.conf'
                for node in nodes:
                    if node['hostname'] == target_node:
                        hostname = node['hostname']
                        ip = node['ip']
                        conf_dict = self.get_nova_conf_dict(az, nova)
                        params = (hostname, ip, conf_path, conf_dict)
                        data.append(params)

        for hostname, ip, conf_path, conf_dict in data:
            logger.info("Check nova conf of {0}".format(hostname))
            for key in conf_dict.keys():
                cmd = 'cat {0} | grep {1}={2}'.format(conf_path, key,
                                                      conf_dict[key])
                logger.debug('CMD: {}'.format(cmd))
                SSHManager().execute_on_remote(ip, cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_nova_srv(self):
        """Verify nova-compute service for each vSphere cluster."""
        vmware_attr = self.fuel_web.client.get_cluster_vmware_attributes(
            self.cluster_id)
        az = vmware_attr['editable']['value']['availability_zones'][0]
        nova_computes = az['nova_computes']

        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        for nova in nova_computes:
            srv_name = nova['service_name']
            cmd = '. openrc; nova-manage service describe_resource ' \
                  'vcenter-{}'.format(srv_name)
            logger.debug('CMD: {}'.format(cmd))
            SSHManager().execute_on_remote(ctrl_nodes[0]['ip'],
                                           cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_cinder_vmware_srv(self):
        """Verify cinder-vmware service."""
        ctrl_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["controller"])
        cmd = '. openrc; cinder-manage service list | grep vcenter | ' \
              'grep ":-)"'
        logger.debug('CMD: {}'.format(cmd))
        SSHManager().execute_on_remote(ctrl_nodes[0]['ip'], cmd)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def deploy_changes(self):
        """Deploy environment."""
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=False)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_neutron_public(self):
        """Check that public network was assigned to all nodes."""
        cluster = self.fuel_web.client.get_cluster(self.cluster_id)
        assert_equal(str(cluster['net_provider']), NEUTRON)
        os_conn = OpenStackActions(
            self.fuel_web.get_public_vip(self.cluster_id))
        self.fuel_web.check_fixed_network_cidr(
            self.cluster_id, os_conn)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_gw_on_vmware_nodes(self):
        """Check that default gw != fuel node ip."""
        vmware_nodes = []
        vmware_nodes.extend(self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["compute-vmware"]))
        vmware_nodes.extend(self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ["cinder-vmware"]))
        logger.debug('Fuel ip is {0}'.format(self.fuel_web.admin_node_ip))
        for node in vmware_nodes:
            cmd = "ip route | grep default | awk '{print $3}'"
            gw_ip = SSHManager().execute_on_remote(node['ip'], cmd)
            logger.debug('Default gw for node {0} is {1}'.format(
                node['name'], gw_ip['stdout_str']))
            assert_not_equal(gw_ip['stdout_str'], self.fuel_web.admin_node_ip)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_idatastore(self):
        """Reconfigure vCenter settings with incorrect regex of Datastore."""
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value']['availability_zones'][0]['nova_computes'][0]\
            ['datastore_regex'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)
        logger.info("Datastore regex settings have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_idc_glance(self):
        """Reconfigure vCenter settings with incorrect Glance Datacenter."""
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value']['glance']['datacenter'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)
        logger.info("Glance datacenter settings have been updated")

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_ids_glance(self):
        """Reconfigure vCenter settings with incorrect Glance Datastore."""
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']
        vcenter_data['value']['glance']['datastore'] = '!@#$%^&*()'

        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)

        logger.info("Glance datastore settings have been updated")

    def _create_server(self, name,
                       flavor_name='m1.micro',
                       net_name='admin_internal_net',
                       availability_zone='nova',
                       image_name='TestVM',
                       timeout=100,
                       delete_existing=True):

        for server in self.os_conn.nova.servers.list():
            if server.name == name:
                if delete_existing:
                    self.os_conn.nova.servers.delete(server)
                    logger.info('Started: delete existing VM '
                                '"{}"'.format(server.name))
                    time.sleep(3)
                else:
                    logger.info('VM "{}" already exists'.format(name))
                    return server

        flavor = [_ for _ in self.os_conn.nova.flavors.list()
                  if _.name == flavor_name][0]

        net = [_ for _ in self.os_conn.nova.networks.list()
               if _.label == net_name][0]

        image = [_ for _ in self.os_conn.nova.images.list()
                 if _.name == image_name][0]

        logger.info(
            'Started: create VM "{name}" with flavor="{flavor}", '
            'net="{net}", az="{az}", image="{image}"'.format(
                name=name, flavor=flavor_name, net=net_name,
                az=availability_zone, image=image_name)
        )

        srv = self.os_conn.nova.servers.create(
            name=name,
            image=image,
            flavor=flavor,
            nics=[{'net-id': net.id}],
            availability_zone=availability_zone
        )

        while timeout > 0:
            status = self.os_conn.get_instance_detail(srv).status
            if status == 'ACTIVE':
                break
            elif status == 'ERROR':
                raise AssertionError('Creation of VM "{}" finished with ERROR '
                                     'status'.format(name))
            time.sleep(5)
            timeout -= 5
        else:
            raise AssertionError('Create server "{}" failed by '
                                 'timeout'.format(name))
        logger.info('VM "{}" created'.format(name))
        return srv

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def create_instances(self):
        """Create instances with nova az and vcenter az."""
        os_ip = self.fuel_web.get_public_vip(self.cluster_id)
        self.os_conn = OpenStackActions(
            os_ip, SERVTEST_USERNAME,
            SERVTEST_PASSWORD,
            SERVTEST_TENANT
        )
        vcenter_az = self.env_settings['vmware_vcenter']['settings']['az']

        vc_inst_count = 1  # amount of VMs to create on vcenter
        nova_inst_count = 1  # amount of VMs to create on nova
        vc_inst_name_prefix = 'vcenter-test'
        nova_inst_name_prefix = 'nova-test'

        # Instances with vcenter availability zone
        for num in xrange(vc_inst_count):
            name = '{prefix}-{num}'.format(prefix=vc_inst_name_prefix,
                                           num=num)
            srv = self._create_server(name=name, availability_zone=vcenter_az,
                                      image_name='TestVM-VMDK', timeout=200)
            self.vms_to_ping.append(srv)

        # Instances with nova availability zone
        for num in xrange(nova_inst_count):
            name = '{prefix}-{num}'.format(prefix=nova_inst_name_prefix,
                                           num=num)
            srv = self._create_server(name=name)
            self.vms_to_ping.append(srv)

    def _get_controller_with_vip(self):
        """Return name of controller with VIPs."""
        for node in self.env.d_env.nodes().slaves:
            ng_node = self.env.fuel_web.get_nailgun_node_by_devops_node(node)
            if ng_node['online']:
                hosts_vip = self.fuel_web.get_pacemaker_resource_location(
                    ng_node['devops_name'], 'vip__management')
                logger.info('Now primary controller is '
                            '{}'.format(hosts_vip[0].name))
                return hosts_vip[0].name

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def hard_reset_primary(self):
        """Hard reboot of primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.fuel_web.cold_restart_nodes([self.primary_ctlr_ng])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_primary(self):
        """Shut down primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.primary_ctlr_ng.destroy()

        timeout = 60 * 10
        interval = 5
        logger.info('Wait offline status for %s' % self.primary_ctlr_ng.name)

        ng_node = self.env.fuel_web.get_nailgun_node_by_devops_node(
            self.primary_ctlr_ng)

        while ng_node['online'] and timeout > 0:
            time.sleep(interval)
            timeout -= interval
            ng_node = self.env.fuel_web.get_nailgun_node_by_devops_node(
                self.primary_ctlr_ng)
        if timeout:
            raise AssertionError('Primary controller is still online')
        logger.info('Primary controller is offline')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def safe_reboot_primary(self):
        """Safe reboot primary controller."""
        self.vip_contr = self._get_controller_with_vip()

        self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
            self.env.d_env.nodes().slaves[0])

        self.fuel_web.warm_restart_nodes([self.primary_ctlr_ng])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_up_vips(self):
        """Ensure that VIPs are moved to another controller."""
        vip_contr = self._get_controller_with_vip()

        if vip_contr and vip_contr != self.vip_contr:
            logger.info('VIPs have been moved to another controller')
        else:
            raise AssertionError('VIPs have not been moved to another '
                                 'controller')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def turn_on_primary(self):
        """Turn on primary controller."""
        self.primary_ctlr_ng.start()
        logger.info('Started: turn on primary controller %s' %
                    self.primary_ctlr_ng.name)

        ng_node = self.env.fuel_web.get_nailgun_node_by_devops_node(
            self.primary_ctlr_ng)

        timeout = 60 * 10
        interval = 5
        logger.info('Wait online status for %s' % self.primary_ctlr_ng.name)
        while not ng_node['online'] and timeout > 0:
            time.sleep(interval)
            timeout -= interval
            ng_node = self.env.fuel_web.get_nailgun_node_by_devops_node(
                self.primary_ctlr_ng)
        if timeout:
            raise AssertionError('Primary controller is still offline')
        logger.info('Primary controller is online')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def reboot_cinder_vmware(self):
        """Reboot CinderVMware node."""
        ng_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=self.cluster_id, roles=['cinder-vmware'])

        dev_node = self.fuel_web.get_devops_node_by_nailgun_fqdn(
            ng_node[0]['fqdn'])

        self.fuel_web.warm_restart_nodes([dev_node])

    def shutdown_node(self, role, index=0):
        """Warm shutdown of node with the role.

        :param role: role of node
        :param index: relative index of node among nodes with the role
        :return: devops node
        """
        ng_node = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id=self.cluster_id, roles=[role])

        dev_node = self.fuel_web.get_devops_node_by_nailgun_fqdn(
            ng_node[index]['fqdn'])

        self.fuel_web.warm_shutdown_nodes([dev_node])
        return dev_node

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_cinder_node(self):
        """Shutdown one of CinderVMDK node."""
        self.dev_cinder = self.shutdown_node('cinder-vmware', 0)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def shutdown_another_cinder_node(self):
        """Shutdown another CinderVMDK node."""
        self.dev_cinder = self.shutdown_node('cinder-vmware', 1)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def power_on_cinder_node(self):
        """Power on CinderVMDK node and wait for it to load."""
        self.fuel_web.warm_start_nodes([self.dev_cinder])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def vcenter_ostf(self):
        """Run vCenter OSTF tests."""
        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            test_sets=['smoke'],
            should_fail=getattr(self, 'ostf_tests_should_failed', 0),
            failed_test_name=getattr(self, 'failed_test_name', None))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def ostf_with_services_fail(self):
        """Run OSTF tests (one should fail)."""
        self.ostf_tests_should_failed = 1
        self.failed_test_name = ['Check that required services are running']

        HealthCheckActions().health_check_sanity_smoke_ha()

        self.ostf_tests_should_failed = 0
        self.failed_test_name = None

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fail_ostf(self):
        """Run OSTF tests (must fail)."""
        try:
            self.env.fuel_web.run_ostf(
                self.cluster_id,
                test_sets=['sanity', 'smoke', 'ha'])
            failed = False
        except AssertionError:
            failed = True
        if failed:
            logger.info('OSTF failed')
        else:
            raise AssertionError('OSTF passed with incorrect parameters')

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def fail_deploy_cluster(self):
        """Deploy environment (must fail)."""
        try:
            self.fuel_web.deploy_cluster_wait(self.cluster_id)
            failed = False
        except AssertionError:
            failed = True
        if failed:
            logger.info('Deploy failed')
        else:
            raise AssertionError('Deploy passed with incorrect parameters')

    def ping_instance_from_instance(self, source_floating_ip,
                                    destination_ip, primary, size=56, count=1):
        """Verify ping between instances."""
        creds = ("cirros", "cubswin:)")

        logger.info('Try to ping from {} to {}'.format(source_floating_ip,
                                                       destination_ip))

        with self.fuel_web.get_ssh_for_node(primary) as ssh:
            command = "ping -s {0} -c {1} {2}".format(size, count,
                                                      destination_ip)
            ping = self.os_conn.execute_through_host(ssh, source_floating_ip,
                                                     command, creds)
            logger.info("Ping result: \n"
                        "{0}\n"
                        "{1}\n"
                        "exit_code={2}".format(ping['stdout'], ping['stderr'],
                                               ping['exit_code']))

            return 0 == ping['exit_code']

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_vm_connect(self):
        """Ensure connectivity between VMs."""
        net = 'admin_internal_net'

        if not self.primary_ctlr_ng:
            self.primary_ctlr_ng = self.fuel_web.get_nailgun_primary_node(
                self.env.d_env.nodes().slaves[0])

        private_ips = {}
        floating_ips = {}

        for srv in self.vms_to_ping:
            t = self.os_conn.assign_floating_ip(srv)
            floating_ips[srv] = t.ip
            logger.info("Floating address {0} associated with instance {1}"
                        .format(floating_ips[srv], srv.name))
            server = self.os_conn.nova.servers.find(name=srv.name)
            private_ips[srv] = self.os_conn.get_nova_instance_ip(
                server, net_name=net)

        for srv1 in self.vms_to_ping:
            for srv2 in self.vms_to_ping:
                self.ping_instance_from_instance(
                    floating_ips[srv1], private_ips[srv2],
                    self.primary_ctlr_ng.name)

                self.ping_instance_from_instance(
                    floating_ips[srv2], private_ips[srv1],
                    self.primary_ctlr_ng.name)
