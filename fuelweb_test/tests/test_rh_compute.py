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

# TODO: We need to use sshmanager instead of executing bare commands
# bp link: https://blueprints.launchpad.net/fuel/+spec/sshmanager-integration

from __future__ import division
import re

from devops.error import TimeoutError
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test import logger as LOGGER
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class RhBase(TestBasic):
    """RH-based compute tests base"""

    @staticmethod
    def wait_for_slave_provision(node_ip, timeout=10 * 60):
        """Wait for a target node provision.

        :param node_ip: IP address of target node.
        :param timeout: Timeout for wait function.
        """
        wait(lambda: tcp_ping(node_ip, 22),
             timeout=timeout, timeout_msg="Node doesn't appear in network")

    @staticmethod
    def wait_for_slave_network_down(node_ip, timeout=10 * 20):
        """Wait for a target node network down.

        :param node_ip: IP address of target node.
        :param timeout: Timeout for wait function.
        """
        wait(lambda: (not tcp_ping(node_ip, 22)), interval=1,
             timeout=timeout, timeout_msg="Node doesn't gone offline")

    def warm_restart_nodes(self, devops_nodes):
        LOGGER.info('Reboot (warm restart) nodes '
                    '{0}'.format([n.name for n in devops_nodes]))
        self.warm_shutdown_nodes(devops_nodes)
        self.warm_start_nodes(devops_nodes)

    def warm_shutdown_nodes(self, devops_nodes):
        LOGGER.info('Shutting down (warm) nodes '
                    '{0}'.format([n.name for n in devops_nodes]))
        for node in devops_nodes:
            LOGGER.debug('Shutdown node {0}'.format(node.name))
            with self.fuel_web.get_ssh_for_node(node.name) as remote:
                remote.execute('/sbin/shutdown -Ph now & exit')

        for node in devops_nodes:
            ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
            LOGGER.info('Wait a {0} node offline status'.format(node.name))
            try:
                self.wait_for_slave_network_down(ip)
            except TimeoutError:
                asserts.assert_false(
                    tcp_ping(ip, 22),
                    'Node {0} has not become '
                    'offline after warm shutdown'.format(node.name))
            node.destroy()

    def warm_start_nodes(self, devops_nodes):
        LOGGER.info('Starting nodes '
                    '{0}'.format([n.name for n in devops_nodes]))
        for node in devops_nodes:
            node.start()
        for node in devops_nodes:
            ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
            try:
                self.wait_for_slave_provision(ip)
            except TimeoutError:
                asserts.assert_true(
                    tcp_ping(ip, 22),
                    'Node {0} has not become online '
                    'after warm start'.format(node.name))
            LOGGER.debug('Node {0} became online.'.format(node.name))

    @staticmethod
    def connect_rh_image(slave):
        """Upload RH image into a target node.

        :param slave: Target node name.
        """
        path = settings.RH_IMAGE_PATH + settings.RH_IMAGE

        def find_system_drive(node):
            drives = node.disk_devices
            for drive in drives:
                if drive.device == 'disk' and 'system' in drive.volume.name:
                    return drive
            raise Exception('Can not find suitable volume to proceed')

        system_disk = find_system_drive(slave)
        vol_path = system_disk.volume.get_path()

        try:
            system_disk.volume.upload(path)
        except Exception as e:
            LOGGER.error(e)
        LOGGER.debug("Volume path: {0}".format(vol_path))
        LOGGER.debug("Image path: {0}".format(path))

    @staticmethod
    def verify_image_connected(remote):
        """Check that correct image connected to a target node system volume.

        :param remote: Remote node to proceed.
        """
        cmd = "cat /etc/redhat-release"
        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, "Image doesn't connected")

    @staticmethod
    def register_rh_subscription(remote):
        """Register RH subscription.

        :param remote: Remote node to proceed.
        """
        reg_command = (
            "/usr/sbin/subscription-manager register "
            "--username={0} --password={1}".format(
                settings.RH_LICENSE_USERNAME,
                settings.RH_LICENSE_PASSWORD)
        )

        if settings.RH_SERVER_URL:
            reg_command += " --serverurl={0}".format(settings.RH_SERVER_URL)

        if settings.RH_REGISTERED_ORG_NAME:
            reg_command += " --org={0}".format(settings.RH_REGISTERED_ORG_NAME)

        if settings.RH_RELEASE:
            reg_command += " --release={0}".format(settings.RH_RELEASE)

        if settings.RH_ACTIVATION_KEY:
            reg_command += " --activationkey={0}".format(
                settings.RH_ACTIVATION_KEY)

        if settings.RH_POOL_HASH:
            result = remote.execute(reg_command)
            LOGGER.debug(result)
            asserts.assert_equal(result['exit_code'], 0,
                                 'RH registration failed')
            reg_pool_cmd = ("/usr/sbin/subscription-manager "
                            "attach --pool={0}".format(settings.RH_POOL_HASH))
            result = remote.execute(reg_pool_cmd)
            LOGGER.debug(result)
            asserts.assert_equal(result['exit_code'], 0,
                                 'Can not attach node to subscription pool')
        else:
            cmd = reg_command + " --auto-attach"
            result = remote.execute(cmd)
            LOGGER.debug(result)
            asserts.assert_equal(result['exit_code'], 0,
                                 'RH registration with auto-attaching failed')

    @staticmethod
    def enable_rh_repos(remote):
        """Enable Red Hat mirrors on a target node.

        :param remote: Remote node for proceed.
        """
        cmd = ("yum-config-manager --enable rhel-{0}-server-optional-rpms && "
               "yum-config-manager --enable rhel-{0}-server-extras-rpms &&"
               "yum-config-manager --enable rhel-{0}-server-rh-common-rpms"
               .format(settings.RH_MAJOR_RELEASE))

        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Enabling RH repos failed')

    @staticmethod
    def set_hostname(remote, host_number=1):
        """Set hostname with domain for a target node.

        :param host_number: Node index nubmer (1 by default).
        :param remote: Remote node for proceed.
        """
        hostname = "rh-{0}.test.domain.local".format(host_number)
        cmd = ("sysctl kernel.hostname={0} && "
               "echo '{0}' > /etc/hostname".format(hostname))

        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Setting up hostname for node failed')

    @staticmethod
    def puppet_apply(puppets, remote):
        """Apply list of puppets on a target node.

        :param puppets: <list> of puppets.
        :param remote: Remote node for proceed.
        """
        LOGGER.debug("Applying puppets...")
        for puppet in puppets:
            LOGGER.debug('Applying: {0}'.format(puppet))
            result = remote.execute(
                'puppet apply -vd -l /var/log/puppet.log {0}'.format(puppet))
            if result['exit_code'] != 0:
                LOGGER.debug("Failed on task: {0}".format(puppet))
                LOGGER.debug("STDERR:\n {0}".format(result['stderr']))
                LOGGER.debug("STDOUT:\n {0}".format(result['stdout']))
            asserts.assert_equal(
                result['exit_code'], 0, 'Puppet run failed. '
                                        'Task: {0}'.format(puppet))

    def apply_first_part_puppet(self, remote):
        """Apply first part of puppet modular tasks on terget node.

        :param remote: Remote node for proceed.
        """
        first_puppet_run = [
            "/etc/puppet/modules/osnailyfacter/modular/hiera/hiera.pp",
            "/etc/puppet/modules/osnailyfacter/modular/globals/globals.pp",
            "/etc/puppet/modules/osnailyfacter/modular/firewall/firewall.pp",
            "/etc/puppet/modules/osnailyfacter/modular/tools/tools.pp"
        ]

        self.puppet_apply(first_puppet_run, remote)

    @staticmethod
    def apply_networking_puppet(remote):
        """Apply networking puppet on a target node.

        Puppet task will executed in screen to prevent disconnections while
        interfaces configuring.

        :param remote: Remote node for proceed.
        """
        iface_check = "test -f /etc/sysconfig/network-scripts/ifcfg-eth0"
        result = remote.execute(iface_check)
        if result['exit_code'] == 0:
            remove_iface = "rm -f /etc/sysconfig/network-scripts/ifcfg-eth0"
            result = remote.execute(remove_iface)
            LOGGER.debug(result)
        prep = "screen -dmS netconf"
        result = remote.execute(prep)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, 'Can not create screen')
        net_puppet = ('screen -r netconf -p 0 -X stuff '
                      '$"puppet apply -vd -l /var/log/puppet.log '
                      '/etc/puppet/modules/osnailyfacter/modular/'
                      'netconfig/netconfig.pp && touch ~/success ^M"')
        result = remote.execute(net_puppet)

        if result['exit_code'] != 0:
            LOGGER.debug("STDERR:\n {0}".format(result['stderr']))
            LOGGER.debug("STDOUT:\n {0}".format(result['stdout']))
        asserts.assert_equal(
            result['exit_code'], 0, 'Can not create screen with '
                                    'netconfig task')

    @staticmethod
    def check_netconfig_success(remote, timeout=10 * 20):
        """Check that netconfig.pp modular task is succeeded.

        :param remote: Remote node for proceed.
        :param timeout: Timeout for wait function.
        """

        def file_checker(connection):
            cmd = "test -f ~/success"
            result = connection.execute(cmd)
            LOGGER.debug(result)
            if result['exit_code'] != 0:
                return False
            else:
                return True
        wait(lambda: file_checker(remote), timeout=timeout,
             timeout_msg='Netconfig puppet task unsuccessful')

    def apply_last_part_puppet(self, remote):
        """Apply final part of puppet modular tasks on a target node.

        :param remote: Remote node for proceed.
        """
        last_puppet_run = [
            "/etc/puppet/modules/osnailyfacter/modular/roles/compute.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "openstack-network/common-config.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "openstack-network/plugins/ml2.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "openstack-network/agents/l3.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "openstack-network/agents/metadata.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "openstack-network/compute-nova.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "astute/enable_compute.pp"
        ]

        self.puppet_apply(last_puppet_run, remote)

    @staticmethod
    def backup_required_information(remote, ip):
        """Back up required information for compute from target node.

        :param remote: Remote Fuel master node.
        :param ip: Target node ip to back up from.
        """
        LOGGER.debug('Target node ip: {0}'.format(ip))
        cmd = ("cd ~/ && mkdir rh_backup; "
               "scp -r {0}:/root/.ssh rh_backup/. ; "
               "scp {0}:/etc/astute.yaml rh_backup/ ; "
               "scp -r {0}:/var/lib/astute/nova rh_backup/").format(ip)
        result = remote.execute(cmd)
        LOGGER.debug(result['stdout'])
        LOGGER.debug(result['stderr'])
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not back up required information from node')
        LOGGER.debug("Backed up ssh-keys and astute.yaml")

    @staticmethod
    def clean_string(string):
        """Clean string of redundant characters.

        :param string: String.
        :return:
        """
        k = str(string)
        pattern = "^\s+|\[|\]|\n|,|'|\r|\s+$"
        res = re.sub(pattern, '', k)
        res = res.strip('/\\n')
        # NOTE(freerunner): Using sub twice to collect key without extra
        # whitespaces.
        res = re.sub(pattern, '', res)
        res = res.strip('/\\n')
        return res

    def restore_information(self, ip, remote_admin, remote_slave):
        """Restore information on a target node.

        :param ip: Remote node ip.
        :param remote_admin: Remote admin node for proceed.
        :param remote_slave: Remote slave node for proceed.
        """
        cmd = "cat ~/rh_backup/.ssh/authorized_keys"
        result = remote_admin.execute(cmd)
        key = result['stdout']
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not get backed up ssh key.')

        key = self.clean_string(key)

        cmd = "mkdir ~/.ssh; echo '{0}' >> ~/.ssh/authorized_keys".format(key)
        result = remote_slave.execute(cmd)
        LOGGER.debug(result['stdout'])
        LOGGER.debug(result['stderr'])
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not recover ssh key for node')

        cmd = "cd ~/rh_backup && scp astute.yaml {0}@{1}:/etc/.".format(
            settings.RH_IMAGE_USER, ip)
        LOGGER.debug("Restoring astute.yaml for node with ip {0}".format(ip))
        result = remote_admin.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not restore astute.yaml')

        cmd = "mkdir -p /var/lib/astute"
        LOGGER.debug("Prepare node for restoring nova ssh-keys")
        result = remote_slave.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, 'Preparation failed')

        cmd = (
            "cd ~/rh_backup && scp -r nova {0}@{1}:/var/lib/astute/.".format(
                settings.RH_IMAGE_USER, ip)
        )
        LOGGER.debug("Restoring nova ssh-keys")
        result = remote_admin.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not restore ssh-keys for nova')

    @staticmethod
    def install_yum_components(remote):
        """Install required yum components on a target node.

        :param remote: Remote node for proceed.
        """
        cmd = "yum install yum-utils yum-priorities -y"
        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, 'Can not install required'
                                                     'yum components.')

    @staticmethod
    def set_repo_for_perestroika(remote):
        """Set Perestroika repos.

        :param remote: Remote node for proceed.
        """
        repo = settings.PERESTROIKA_REPO
        cmd = ("curl {0}".format(repo))

        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Perestroika repos unavailable from node.')

        cmd = ("echo '[mos]\n"
               "name=mos\n"
               "type=rpm-md\n"
               "baseurl={0}\n"
               "gpgcheck=0\n"
               "enabled=1\n"
               "priority=5' >"
               "/etc/yum.repos.d/mos.repo && "
               "yum clean all".format(repo))
        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Can not create config file for repo')

    @staticmethod
    def check_hiera_installation(remote):
        """Check hiera installation on node.

        :param remote: Remote node for proceed.
        """
        cmd = "yum list installed | grep hiera"
        LOGGER.debug('Checking hiera installation...')
        result = remote.execute(cmd)
        if result['exit_code'] == 0:
            cmd = "yum remove hiera -y"
            LOGGER.debug('Found existing installation of hiera. Removing...')
            result = remote.execute(cmd)
            asserts.assert_equal(result['exit_code'], 0, 'Can not remove '
                                                         'hiera')
            cmd = "ls /etc/hiera"
            LOGGER.debug('Checking hiera files for removal...')
            result = remote.execute(cmd)
            if result['exit_code'] == 0:
                LOGGER.debug('Found redundant hiera files. Removing...')
                cmd = "rm -rf /etc/hiera"
                result = remote.execute(cmd)
                asserts.assert_equal(result['exit_code'], 0,
                                     'Can not remove hiera files')

    @staticmethod
    def check_rsync_installation(remote):
        """Check rsync installation on node.

        :param remote: Remote node for proceed.
        """
        cmd = "yum list installed | grep rsync"
        LOGGER.debug("Checking rsync installation...")
        result = remote.execute(cmd)
        if result['exit_code'] != 0:
            LOGGER.debug("Rsync is not found. Installing rsync...")
            cmd = "yum clean all && yum install rsync -y"
            result = remote.execute(cmd)
            LOGGER.debug(result)
            asserts.assert_equal(result['exit_code'], 0, 'Can not install '
                                                         'rsync on node.')

    @staticmethod
    def remove_old_compute_services(remote, hostname):
        """Remove old redundant services which was removed from services base.

        :param remote: Remote node for proceed.
        :param hostname: Old compute hostname.
        """
        cmd = ("source ~/openrc && for i in $(nova service-list | "
               "awk '/%s/{print $2}'); do nova service-delete $i; "
               "done" % hostname)
        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, 'Can not remove '
                                                     'old nova computes')

        cmd = ("source ~/openrc && for i in $(neutron agent-list | "
               "awk '/%s/{print $2}'); do neutron agent-delete $i; "
               "done" % hostname)
        result = remote.execute(cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0, 'Can not remove '
                                                     'old neutron agents')

    @staticmethod
    def install_ruby_puppet(remote):
        """Install ruby and puppet on a target node.

        :param remote: Remote node for proceed.
        """
        puppet_install_cmd = "yum install puppet ruby -y"
        result = remote.execute(puppet_install_cmd)
        LOGGER.debug(result)
        asserts.assert_equal(result['exit_code'], 0,
                             'Ruby and puppet installation failed')

    @staticmethod
    def rsync_puppet_modules(remote, ip):
        """Rsync puppet modules from remote node to node with specified ip.

        :param remote: Remote node for proceed.
        :param ip: IP address of a target node where to sync.
        """
        cmd = ("rsync -avz /etc/puppet/modules/* "
               "{0}@{1}:/etc/puppet/modules/".format(settings.RH_IMAGE_USER,
                                                     ip))
        result = remote.execute(cmd)
        LOGGER.debug(cmd)
        asserts.assert_equal(result['exit_code'], 0,
                             'Rsync puppet modules failed')

    def save_node_hostname(self, remote):
        """Save hostname of a node.

        :param remote: Remote node for proceed.
        :return: Node hostname.
        """
        cmd = "hostname"
        result = remote.execute(cmd)
        asserts.assert_equal(result['exit_code'], 0, 'Can not get hostname '
                                                     'for remote')
        nodename = self.clean_string(result['stdout'])
        return nodename


@test(groups=["rh", "rh.ha_one_controller", "rh.basic"])
class RhHaOneController(RhBase):
    """RH-based compute HA One Controller basic test"""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_rh_compute_ha_one_controller_tun"])
    @log_snapshot_after_test
    def deploy_rh_compute_ha_one_controller_tun(self):
        """Deploy RH-based compute in HA One Controller mode
        with Neutron VXLAN

        Scenario:
            1. Check required image.
            2. Revert snapshot 'ready_with_3_slaves'.
            3. Create a Fuel cluster.
            4. Update cluster nodes with required roles.
            5. Deploy the Fuel cluster.
            6. Run OSTF.
            7. Backup astute.yaml and ssh keys from compute.
            8. Boot compute with RH image.
            9. Prepare node for Puppet run.
            10. Execute modular tasks for compute.
            11. Run OSTF.

        Duration: 150m
        Snapshot: deploy_rh_compute_ha_one_controller_tun

        """
        self.show_step(1, initialize=True)
        LOGGER.debug('Check MD5 sum of RH 7 image')
        check_image = checkers.check_image(
            settings.RH_IMAGE,
            settings.RH_IMAGE_MD5,
            settings.RH_IMAGE_PATH)
        asserts.assert_true(check_image,
                            'Provided image is incorrect. '
                            'Please, check image path and md5 sum of it.')

        self.show_step(2)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(3)
        LOGGER.debug('Create Fuel cluster RH-based compute tests')
        data = {
            'volumes_lvm': True,
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'RhHAOneController',
            'user': 'RhHAOneController',
            'password': 'RhHAOneController'
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data
        )

        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            cluster_vip, data['user'], data['password'], data['tenant'])

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.show_step(7)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        LOGGER.debug('Got node: {0}'.format(compute))
        target_node = self.fuel_web.get_devops_node_by_nailgun_node(
            compute)
        LOGGER.debug('DevOps Node: {0}'.format(target_node))
        target_node_ip = compute['ip']
        LOGGER.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_ip, target_node.name))

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            old_hostname = self.save_node_hostname(remote)

        with self.env.d_env.get_admin_remote() as remote:
            self.backup_required_information(remote, target_node_ip)

        self.show_step(8)

        target_node.destroy()
        asserts.assert_false(target_node.driver.node_active(node=target_node),
                             'Target node still active')
        self.connect_rh_image(target_node)
        target_node.start()
        asserts.assert_true(target_node.driver.node_active(node=target_node),
                            'Target node did not start')
        self.wait_for_slave_provision(target_node_ip)
        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            self.verify_image_connected(remote)

        self.show_step(9)

        with self.env.d_env.get_admin_remote() as remote_admin:
            with self.env.d_env.get_ssh_to_remote(target_node_ip) as \
                    remote_slave:
                self.restore_information(target_node_ip,
                                         remote_admin, remote_slave)

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            self.set_hostname(remote)
            if not settings.CENTOS_DUMMY_DEPLOY:
                self.register_rh_subscription(remote)
            self.install_yum_components(remote)
            if not settings.CENTOS_DUMMY_DEPLOY:
                self.enable_rh_repos(remote)
            self.set_repo_for_perestroika(remote)
            self.check_hiera_installation(remote)
            self.install_ruby_puppet(remote)
            self.check_rsync_installation(remote)

        with self.env.d_env.get_admin_remote() as remote:
            self.rsync_puppet_modules(remote, target_node_ip)

        self.show_step(10)
        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            self.apply_first_part_puppet(remote)

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            self.apply_networking_puppet(remote)

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            self.check_netconfig_success(remote)
            self.apply_last_part_puppet(remote)

        with self.env.d_env.get_ssh_to_remote(controller['ip']) as remote:
            self.remove_old_compute_services(remote, old_hostname)

        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_one_controller_with_rh_compute",
                               is_make=True)
