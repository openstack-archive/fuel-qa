#    Copyright 2015-2016 Mirantis, Inc.
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

from __future__ import division

import os
import time
import itertools

from devops.helpers.helpers import wait

from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
# pylint: disable=redefined-builtin
from six.moves import xrange
# pylint: enable=redefined-builtin

import fuelweb_test
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.cloud_image import generate_cloud_image_settings
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test import settings

from system_test import logger
from system_test import action
from system_test import nested_action
from system_test import deferred_decorator

from system_test.actions.ostf_actions import HealthCheckActions
from system_test.actions.plugins_actions import PluginsActions
from system_test.actions.vcenter_actions import VMwareActions

from system_test.core.discover import load_yaml
from system_test.helpers.decorators import make_snapshot_if_step_fail


# pylint: disable=no-member
class PrepareActions(object):
    """Base class with prepare actions

    _start_case - runned before test case start
    _finish_case - runned after test case finish
    setup_master - setup master node in environment
    config_release - preconfig releases if it needs
    make_slaves - boot slaves and snapshot environment with bootstrapped slaves
    revert_slaves - revert environment with bootstrapped slaves

    """
    def __init__(self):
        self.full_config = None
        self.env_config = None
        self.env_settings = None
        self.config_name = None
        self._devops_config = None
        self._start_time = 0

    def _load_config(self):
        config = load_yaml(self.config_file)
        self.full_config = config
        self.env_config = config[
            'template']['cluster_template']
        self.env_settings = config[
            'template']['cluster_template']['settings']
        self.config_name = config['template']['name']

        if 'devops_settings' in config['template']:
            self._devops_config = config

    def _start_case(self):
        """Start test case"""
        self._load_config()
        class_doc = getattr(self, "__doc__", self.__class__.__name__)
        name = class_doc.splitlines()[0]
        class_scenario = class_doc.splitlines()[1:]
        start_case = "[ START {} ]".format(name)
        header = "<<< {:=^142} >>>".format(start_case)
        indent = ' ' * 4
        scenario = '\n'.join(class_scenario)
        logger.info("\n{header}\n\n"
                    "{indent}Configuration: {config}\n"
                    "\n{scenario}".format(
                        header=header,
                        indent=indent,
                        config=self.config_name,
                        scenario=scenario))
        self._start_time = time.time()

    def _finish_case(self):
        """Finish test case"""
        case_time = time.time() - self._start_time
        minutes = case_time // 60
        # pylint: disable=round-builtin
        seconds = int(round(case_time)) % 60
        # pylint: enable=round-builtin
        name = getattr(self, "__doc__",
                       self.__class__.__name__).splitlines()[0]
        finish_case = "[ FINISH {} CASE TOOK {} min {} sec ]".format(
            name,
            minutes,
            seconds)
        footer = "<<< {:=^142} >>>".format(finish_case)
        logger.info("\n{footer}\n".format(footer=footer))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def setup_master(self):
        """Setup master node"""
        self.check_run("empty")
        with TimeStat("setup_environment", is_uniq=True):
            self.env.setup_environment()
            self.fuel_post_install_actions()

        self.env.make_snapshot("empty", is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def setup_centos_master(self):
        """Create environment, bootstrap centos_master
        and install fuel services

        Snapshot "empty_centos"

            1. bootstrap_centos_master
            2. Download fuel_release from remote repository
            3. install fuel_setup package
            4. Install Fuel services by executing bootstrap_admin_node.sh
            5. check Fuel services


        """
        self.check_run("empty_centos")
        self.show_step(1, initialize=True)
        cloud_image_settings_path = os.path.join(
            os.path.dirname(fuelweb_test.__file__),
            'cloud_image_settings/cloud_settings.iso')

        admin_net_object = self.env.d_env.get_network(
            name=self.env.d_env.admin_net)
        admin_network = admin_net_object.ip.network
        admin_netmask = admin_net_object.ip.netmask
        admin_ip = str(self.env.d_env.nodes(
        ).admin.get_ip_address_by_network_name(self.env.d_env.admin_net))
        interface_name = settings.iface_alias("eth0")
        gateway = self.env.d_env.router()
        dns = settings.DNS
        dns_ext = ''.join(settings.EXTERNAL_DNS)
        hostname = ''.join((settings.FUEL_MASTER_HOSTNAME,
                            settings.DNS_SUFFIX))
        user = settings.SSH_CREDENTIALS['login']
        password = settings.SSH_CREDENTIALS['password']
        generate_cloud_image_settings(cloud_image_settings_path, admin_network,
                                      interface_name, admin_ip, admin_netmask,
                                      gateway, dns, dns_ext,
                                      hostname, user, password)

        with TimeStat("bootstrap_centos_node", is_uniq=True):
            admin = self.env.d_env.nodes().admin
            logger.info(cloud_image_settings_path)
            admin.disk_devices.get(
                device='cdrom').volume.upload(cloud_image_settings_path)
            self.env.d_env.start([admin])
            logger.info("Waiting for Centos node to start up")
            wait(lambda: admin.driver.node_active(admin), 60,
                 timeout_msg='Centos node failed to start')
            logger.info("Waiting for Centos node ssh ready")
            self.env.wait_for_provisioning()

        self.centos_setup_fuel(hostname)

        self.env.make_snapshot("empty", is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_release(self):
        """Configuration releases"""
        self.check_run("ready")
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()

        if (settings.REPLACE_DEFAULT_REPOS and
                settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE):
            self.fuel_web.replace_default_repos()

        self.env.make_snapshot("ready", is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def make_slaves(self):
        """Bootstrap slave and make snapshot

        Use slaves parameter from case section

        """
        slaves = int(self.full_config['template']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)
        logger.info("Bootstrap {} nodes".format(slaves))
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:slaves],
                                 skip_timesync=True)
        self.env.make_snapshot(snapshot_name, is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def revert_slaves(self):
        """Revert bootstrapped nodes

        Skip if snapshot with cluster exists

        """
        self.check_run(self.env_config['name'])
        slaves = int(self.full_config['template']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.env.revert_snapshot(snapshot_name)

    @nested_action
    def prepare_admin_node_with_slaves():
        """Combine preparation steps in alias"""
        return [
            'setup_master',
            'config_release',
            'make_slaves',
            'revert_slaves',
        ]


class BaseActions(PrepareActions, HealthCheckActions, PluginsActions,
                  VMwareActions):
    """Basic actions for acceptance cases

    For choosing action order use actions_order variable, set list of actions
        order

    Actions:
        create_env - create and configure environment
        add_nodes - add nodes to environment
        deploy_cluster - deploy en environment
        network_check - run network check
        reset_cluster - reset an environment
        delete_cluster - delete en environment
        stop_deploy - stop deploying of environment

    """

    est_duration = None
    base_group = None
    actions_order = None
    cluster_id = None
    scale_step = 0
    power_step = 0

    def _add_node(self, nodes_list):
        """Add nodes to Environment"""
        logger.info("Add nodes to env {}".format(self.cluster_id))
        names = "slave-{:02}"
        slaves = int(self.full_config['template']['slaves'])
        num = iter(xrange(1, slaves + 1))
        nodes = {}
        for new in nodes_list:
            for _ in xrange(new['count']):
                name = names.format(next(num))
                while name in self.assigned_slaves:
                    name = names.format(next(num))

                self.assigned_slaves.add(name)
                nodes[name] = new['roles']
                logger.info("Set roles {} to node {}".format(new['roles'],
                                                             name))
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    def _del_node(self, nodes_list):
        """Delete nodes from Environment"""
        logger.info("Delete nodes from env {}".format(self.cluster_id))
        nodes = {}

        for node in nodes_list:
            cluster_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                self.cluster_id, node['roles'])
            for i in xrange(node['count']):
                dnode = self.fuel_web.get_devops_node_by_nailgun_node(
                    cluster_nodes[i])
                self.assigned_slaves.remove(dnode.name)

                nodes[dnode.name] = node['roles']
                logger.info("Delete node {} with role {}".format(
                    dnode.name, node['roles']))

        self.fuel_web.update_nodes(self.cluster_id, nodes, False, True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def create_env(self):
        """Create Fuel Environment

        For configure Environment use environment-config section in config file

        Skip action if we have snapshot with Environment name

        """
        self.check_run(self.env_config['name'])

        logger.info("Create env {}".format(
            self.env_config['name']))
        cluster_settings = {
            "murano": self.env_settings['components'].get('murano', False),
            "sahara": self.env_settings['components'].get('sahara', False),
            "ceilometer": self.env_settings['components'].get('ceilometer',
                                                              False),
            "ironic": self.env_settings['components'].get('ironic', False),
            "user": self.env_config.get("user", "admin"),
            "password": self.env_config.get("password", "admin"),
            "tenant": self.env_config.get("tenant", "admin"),
            "volumes_lvm": self.env_settings['storages'].get("volume-lvm",
                                                             False),
            "volumes_ceph": self.env_settings['storages'].get("volume-ceph",
                                                              False),
            "images_ceph": self.env_settings['storages'].get("image-ceph",
                                                             False),
            "ephemeral_ceph": self.env_settings['storages'].get(
                "ephemeral-ceph", False),
            "objects_ceph": self.env_settings['storages'].get("rados-ceph",
                                                              False),
            "osd_pool_size": str(self.env_settings['storages'].get(
                "replica-ceph", 2)),
            "net_provider": self.env_config['network'].get('provider',
                                                           'neutron'),
            "net_segment_type": self.env_config['network'].get('segment-type',
                                                               'vlan'),
            "assign_to_all_nodes": self.env_config['network'].get(
                'pubip-to-all',
                False),
            "neutron_l3_ha": self.env_config['network'].get(
                'neutron-l3-ha', False),
            "neutron_dvr": self.env_config['network'].get(
                'neutron-dvr', False),
            "neutron_l2_pop": self.env_config['network'].get(
                'neutron-l2-pop', False)
        }

        self.cluster_id = self.fuel_web.create_cluster(
            name=self.env_config['name'],
            mode=settings.DEPLOYMENT_MODE,
            release_name=settings.OPENSTACK_RELEASE_UBUNTU
            if self.env_config['release'] == 'ubuntu'
            else settings.OPENSTACK_RELEASE,
            settings=cluster_settings)

        logger.info("Cluster created with ID:{}".format(self.cluster_id))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def add_nodes(self):
        """Add nodes to environment

        Used sub-section nodes in environment-config section

        Skip action if cluster doesn't exist

        """
        if self.cluster_id is None:
            raise SkipTest()

        self._add_node(self.env_config['nodes'])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def deploy_cluster(self):
        """Deploy environment

        Skip action if cluster doesn't exist

        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def stop_on_deploy(self):
        """Stop environment deploying and wait while slave bacame online"""
        if self.cluster_id is None:
            raise SkipTest()

        cluster_id = self.cluster_id
        logger.info('Deploy will be stopeed on {}%'.format(
            settings.PROGRESS_TO_STOP))
        self.fuel_web.deploy_cluster_wait_progress(
            cluster_id, progress=settings.PROGRESS_TO_STOP)
        self.fuel_web.stop_deployment_wait(cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.get_nodes(name__in=list(self.assigned_slaves)),
            timeout=10 * 60)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def network_check(self):
        """Run network checker

        Skip action if cluster doesn't exist

        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.verify_network(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def save_load_environment(self):
        """Load existent environment from snapshot or save it"""
        env_name = self.env_config['name']
        if self.cluster_id is None:
            logger.info("Revert Environment from "
                        "snapshot({})".format(env_name))
            assert_true(self.env.d_env.has_snapshot(env_name))
            self.env.revert_snapshot(env_name)
            self.cluster_id = self.fuel_web.client.get_cluster_id(env_name)
            logger.info("Cluster with ID:{} reverted".format(self.cluster_id))
        else:
            logger.info("Make snapshot of Environment '{}' ID:{}".format(
                env_name, self.cluster_id))
            self.env.make_snapshot(env_name, is_make=True)
            self.env.resume_environment()
            self.env.sync_time()

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_haproxy(self):
        """HAProxy backend checking"""
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def scale_node(self):
        """Scale node in cluster

        For add nodes with role use scale_nodes in yaml with action add in
        step::

          scale_nodes:
          - - roles:
              - controller
              count: 2
              action: add

        For remove nodes with role use scale_nodes in yaml with action delete
        in step::

          scale_nodes:
          - - roles:
              - controller
              count: 2
              action: delete

        Step may contain add and remove action together::

          scale_nodes:
          - - roles:
              - compute
              count: 2
              action: add
          - - roles:
              - ceph-osd
              count: 1
              action: delete

        """
        step_config = self.env_config['scale_nodes'][self.scale_step]
        for node in step_config:
            if node['action'] == 'add':
                self._add_node([node])
            elif node['action'] == 'delete':
                self._del_node([node])
                if 'compute-vmware' in node['roles']:
                    self.del_vmware_nova_compute()
            elif node['action'] == 'reconfigure':
                if node.get('vmware_vcenter'):
                    nova_computes = node['vmware_vcenter']['nova-compute']
                    self.add_vmware_nova_compute(nova_computes)
                if node.get('vmware_dvs'):
                    dvs_settings = node['vmware_dvs']
                    self.update_dvs_plugin_settings(dvs_settings)
            else:
                logger.error("Unknown scale action: {}".format(node['action']))
        self.scale_step += 1

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def manage_nodes_power(self):
        """Manage power of node

        To power off node with role use manage_nodes_power in yaml with action
        power_off in step::

          manage_nodes_power:
          - - roles:
              - controller
              node_number: 0
              action: power_off

        To power on node with role use manage_nodes_power in yaml with action
        power_on in step::

          manage_nodes_power:
          - - roles:
              - controller
              node_number: 0
              action: power_on

        To restart node with role use manage_nodes_power in yaml with action
        warm_restart or cold_restart in step::

          manage_nodes_power:
          - - roles:
              - controller
              node_number: 0
              action: warm_restart

        Example of cold restarting two different nodes with the same role::

          manage_nodes_power:
          - - roles:
              - controller
              node_number: 0
              action: cold_restart
          - - roles:
              - controller
              node_number: 1
              action: cold_restart

        """
        power_actions = {
            'power_off_warm': self.fuel_web.warm_shutdown_nodes,
            'power_on_warm': self.fuel_web.warm_start_nodes,
            'reboot_warm': self.fuel_web.warm_restart_nodes,
            'reboot_cold': self.fuel_web.cold_restart_nodes
        }

        step_config = self.env_config['manage_nodes_power'][self.power_step]
        for node in step_config:
            power_action = power_actions.get(node['action'], None)
            node_number = node['node_number']
            if power_action:
                ng_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                    cluster_id=self.cluster_id, roles=[node['roles'][0]])

                dev_node = self.fuel_web.get_devops_node_by_nailgun_fqdn(
                    ng_nodes[node_number]['fqdn'])

                power_action([dev_node])
            else:
                logger.error("Unknown power switch action: "
                             "{}".format(node['action']))
        self.power_step += 1

    def add_vmware_nova_compute(self, nova_computes):
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']['value']['availability_zones'][
            0]["nova_computes"]

        comp_vmware_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ['compute-vmware'], role_status='pending_roles')

        comp_vmware_nodes = [n for n in comp_vmware_nodes if
                             n['pending_addition']]

        for instance in nova_computes:
            cluster_name = instance['cluster']
            srv_name = instance['srv_name']
            datastore = instance['datastore']
            if instance['target_node'] == 'compute-vmware':
                node = comp_vmware_nodes.pop()
                target_node = node['hostname']
            else:
                target_node = instance['target_node']

            vcenter_data[:] = [n for n in vcenter_data if
                               cluster_name != n['vsphere_cluster']]

            vcenter_data.append(
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

        logger.debug("Try to update cluster with next "
                     "vmware_attributes {0}".format(vmware_attr))
        self.fuel_web.client.update_cluster_vmware_attributes(
            self.cluster_id, vmware_attr)

    def del_vmware_nova_compute(self):
        vmware_attr = \
            self.fuel_web.client.get_cluster_vmware_attributes(self.cluster_id)
        vcenter_data = vmware_attr['editable']['value']['availability_zones'][
            0]["nova_computes"]

        comp_vmware_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ['compute-vmware'])
        comp_vmware_nodes = [node for node in comp_vmware_nodes if
                             node['pending_deletion'] is True]

        for node, nova_comp in itertools.product(comp_vmware_nodes,
                                                 vcenter_data):
            if node['hostname'] == nova_comp['target_node']['current']['id']:
                vcenter_data.remove(nova_comp)
        self.fuel_web.client.update_cluster_vmware_attributes(self.cluster_id,
                                                              vmware_attr)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def reset_cluster(self):
        """Reset environment"""
        cluster_id = self.cluster_id
        self.fuel_web.stop_reset_env_wait(cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def delete_cluster(self):
        """Delete environment"""
        cluster_id = self.cluster_id
        self.fuel_web.delete_env_wait(cluster_id)
