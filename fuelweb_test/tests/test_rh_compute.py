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
from fuelweb_test import logger
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
        logger.info('Reboot (warm restart) nodes '
                    '{0}'.format([n.name for n in devops_nodes]))
        self.warm_shutdown_nodes(devops_nodes)
        self.warm_start_nodes(devops_nodes)

    def warm_shutdown_nodes(self, devops_nodes):
        logger.info('Shutting down (warm) nodes '
                    '{0}'.format([n.name for n in devops_nodes]))
        for node in devops_nodes:
            ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
            logger.debug('Shutdown node {0}'.format(node.name))
            self.ssh_manager.execute(ip, '/sbin/shutdown -Ph now & exit')

        for node in devops_nodes:
            ip = self.fuel_web.get_node_ip_by_devops_name(node.name)
            logger.info('Wait a {0} node offline status'.format(node.name))
            try:
                self.wait_for_slave_network_down(ip)
            except TimeoutError:
                asserts.assert_false(
                    tcp_ping(ip, 22),
                    'Node {0} has not become '
                    'offline after warm shutdown'.format(node.name))
            node.destroy()

    def warm_start_nodes(self, devops_nodes):
        logger.info('Starting nodes '
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
            logger.debug('Node {0} became online.'.format(node.name))

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
            logger.error(e)
        logger.debug("Volume path: {0}".format(vol_path))
        logger.debug("Image path: {0}".format(path))

    def verify_image_connected(self, ip):
        """Check that correct image connected to a target node system volume.

        :param ip: Remote node ip to proceed.
        """
        cmd = "cat /etc/redhat-release"
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg="Image doesn't connected")

    def register_rh_subscription(self, ip):
        """Register RH subscription.

        :param ip: Remote node ip to proceed.
        """
        reg_command = (
            "/usr/sbin/subscription-manager register "
            "--username={0} --password={1}".format(
                settings.RH_LICENSE_USERNAME,
                settings.RH_LICENSE_PASSWORD)
        )

        if settings.RH_SERVER_URL:
            reg_command += " --serverurl={0}".format(
                settings.RH_SERVER_URL)

        if settings.RH_REGISTERED_ORG_NAME:
            reg_command += " --org={0}".format(
                settings.RH_REGISTERED_ORG_NAME)

        if settings.RH_RELEASE:
            reg_command += " --release={0}".format(
                settings.RH_RELEASE)

        if settings.RH_ACTIVATION_KEY:
            reg_command += " --activationkey={0}".format(
                settings.RH_ACTIVATION_KEY)

        if settings.RH_POOL_HASH:
            self.ssh_manager.execute_on_remote(
                ip, reg_command, err_msg='RH registration failed')
            reg_pool_cmd = ("/usr/sbin/subscription-manager "
                            "attach --pool={0}".format(settings.RH_POOL_HASH))
            self.ssh_manager.execute_on_remote(
                ip, reg_pool_cmd,
                err_msg='Can not attach node to subscription pool')
        else:
            cmd = reg_command + " --auto-attach"
            self.ssh_manager.execute_on_remote(
                ip, cmd, err_msg='RH registration with auto-attaching failed')

    def enable_rh_repos(self, ip):
        """Enable Red Hat mirrors on a target node.

        :param ip: Remote node ip for proceed.
        """
        cmd = ("yum-config-manager --enable rhel-{0}-server-optional-rpms && "
               "yum-config-manager --enable rhel-{0}-server-extras-rpms &&"
               "yum-config-manager --enable rhel-{0}-server-rh-common-rpms"
               .format(settings.RH_MAJOR_RELEASE))

        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Enabling RH repos failed')

    def set_hostname(self, ip, host_number=1):
        """Set hostname with domain for a target node.

        :param host_number: Node index nubmer (1 by default).
        :param ip: Remote node ip for proceed.
        """
        hostname = "rh-{0}.test.domain.local".format(host_number)
        cmd = ("sysctl kernel.hostname={0} && "
               "echo '{0}' > /etc/hostname".format(hostname))

        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Setting up hostname for node failed')
        return hostname

    def puppet_apply(self, puppets, ip):
        """Apply list of puppets on a target node.

        :param puppets: <list> of puppets.
        :param ip: Remote node ip for proceed.
        """
        logger.debug("Applying puppets...")
        for puppet in puppets:
            logger.debug('Applying: {0}'.format(puppet))
            self.ssh_manager.execute_on_remote(
                ip,
                'puppet apply -vd -l /var/log/puppet.log {0}'.format(puppet),
                err_msg='Puppet run failed. Task: {0}'.format(puppet))

    def apply_first_part_puppet(self, ip):
        """Apply first part of puppet modular tasks on target node.

        :param ip: Remote node ip for proceed.
        """
        first_puppet_run = [
            "/etc/puppet/modules/osnailyfacter/modular/hiera/hiera.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "hiera/override_configuration.pp",
            "/etc/puppet/modules/osnailyfacter/modular/"
            "netconfig/reserved_ports.pp",
            "/etc/puppet/modules/osnailyfacter/modular/fuel_pkgs/fuel_pkgs.pp",
            "/etc/puppet/modules/osnailyfacter/modular/globals/globals.pp",
            "/etc/puppet/modules/osnailyfacter/modular/tools/tools.pp"
        ]

        self.puppet_apply(first_puppet_run, ip)

    def apply_networking_puppet(self, ip):
        """Apply networking puppet on a target node.

        Puppet task will executed in screen to prevent disconnections while
        interfaces configuring.

        :param ip: Remote node ip for proceed.
        """
        iface_check = "test -f /etc/sysconfig/network-scripts/ifcfg-eth0"
        result = self.ssh_manager.execute(ip, iface_check)
        if result['exit_code'] == 0:
            remove_iface = "rm -f /etc/sysconfig/network-scripts/ifcfg-eth0"
            self.ssh_manager.execute_on_remote(ip, remove_iface)
        prep = "screen -dmS netconf"
        self.ssh_manager.execute_on_remote(ip, prep,
                                           err_msg='Can not create screen')

        net_puppet = ('screen -r netconf -p 0 -X stuff '
                      '$"puppet apply -vd -l /var/log/puppet.log '
                      '/etc/puppet/modules/osnailyfacter/modular/'
                      'netconfig/netconfig.pp && touch ~/success ^M"')
        self.ssh_manager.execute_on_remote(
            ip, net_puppet,
            err_msg='Can not create screen with netconfig task')

    def check_netconfig_success(self, ip, timeout=10 * 20):
        """Check that netconfig.pp modular task is succeeded.

        :param ip: Remote node ip for proceed.
        :param timeout: Timeout for wait function.
        """

        def file_checker(target_ip):
            cmd = "test -f ~/success"
            result = self.ssh_manager.execute(target_ip, cmd)
            logger.debug(result)
            if result['exit_code'] != 0:
                return False
            else:
                return True
        wait(lambda: file_checker(ip), timeout=timeout,
             timeout_msg='Netconfig puppet task unsuccessful')

    def apply_last_part_puppet(self, ip, ceph=False):
        """Apply final part of puppet modular tasks on a target node.

        :param ip: Remote node ip for proceed.
        """
        last_puppet_run = [
            "/etc/puppet/modules/osnailyfacter/modular/firewall/firewall.pp",
            "/etc/puppet/modules/osnailyfacter/modular/hosts/hosts.pp",
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
            "roles/enable_compute.pp",
            "/etc/puppet/modules/osnailyfacter/modular/dns/dns-client.pp",
            "/etc/puppet/modules/osnailyfacter/modular/netconfig/"
            "configure_default_route.pp"
        ]

        if ceph:
            last_puppet_run.append("/etc/puppet/modules/osnailyfacter/"
                                   "modular/ceph/ceph_compute.pp")
        last_puppet_run.append("/etc/puppet/modules/osnailyfacter/modular/"
                               "ntp/ntp-client.pp")

        self.puppet_apply(last_puppet_run, ip)

    def backup_required_information(self, ip, target_ip, node=1, ceph=False):
        """Back up required information for compute from target node.

        :param ip: Remote Fuel master node ip.
        :param target_ip: Target node ip to back up from.
        :param node: Node number
        :param ceph: Enabled or disabled Ceph storage.
        """

        logger.debug('Target node ip: {0}'.format(target_ip))
        cmd = ("cd ~/ && mkdir rh_backup-{1}; "
               "scp -r {0}:/root/.ssh rh_backup-{1}/. ; "
               "scp {0}:/etc/astute.yaml rh_backup-{1}/ ; "
               "scp -r {0}:/var/lib/astute/nova rh_backup-{1}/"
               .format(target_ip, node))
        if ceph:
            cmd += (" ; scp -r {0}:/var/lib/astute/ceph rh_backup-{1}/"
                    .format(target_ip, node))
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not back up required information from node')
        logger.debug("Backed up ssh-keys and astute.yaml")

    @staticmethod
    def clean_string(string, twice=True):
        """Clean string of redundant characters.

        :param string: String.
        :param twice: Boolean. Use function twice or not.
        :return:
        """
        k = str(string)
        pattern = "^\s+|\[|\]|\n|,|'|\r|\s+$"
        res = re.sub(pattern, '', k)
        if twice:
            res = res.strip('/\\n')
            # NOTE(freerunner): Using sub twice to collect key without extra
            # whitespaces.
            res = re.sub(pattern, '', res)
            res = res.strip('/\\n')
        return res

    def restore_information(self, ip, remote_admin_ip, ceph=False, node=1):

        """Restore information on a target node.

        :param ip: Remote node ip.
        :param remote_admin_ip: Remote admin node for proceed.
        """

        cmd = "cat ~/rh_backup-{0}/.ssh/authorized_keys".format(node)
        result = self.ssh_manager.execute_on_remote(
            remote_admin_ip, cmd,
            err_msg='Can not get backed up ssh key.')
        key = result['stdout']

        key = self.clean_string(key)

        cmd = "mkdir ~/.ssh; echo '{0}' >> ~/.ssh/authorized_keys".format(key)
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not recover ssh key for node')

        cmd = "cd ~/rh_backup-{2} && scp astute.yaml {0}@{1}:/etc/.".format(
            settings.RH_IMAGE_USER, ip, node)
        logger.debug("Restoring astute.yaml for node with ip {0}".format(ip))
        self.ssh_manager.execute_on_remote(
            remote_admin_ip, cmd, err_msg='Can not restore astute.yaml')

        cmd = "mkdir -p /var/lib/astute"
        logger.debug("Prepare node for restoring nova ssh-keys")
        self.ssh_manager.execute_on_remote(ip, cmd,
                                           err_msg='Preparation failed')

        cmd = (
            "cd ~/rh_backup-{2} && scp -r nova {0}@{1}:/var/lib/astute/.".
            format(settings.RH_IMAGE_USER, ip, node)
        )
        logger.debug("Restoring nova ssh-keys")
        self.ssh_manager.execute_on_remote(
            remote_admin_ip, cmd, err_msg='Can not restore ssh-keys for nova')

        if ceph:
            cmd = (
                "cd ~/rh_backup-{2} && scp -r ceph {0}@{1}:/var/lib/astute/."
                .format(settings.RH_IMAGE_USER, ip, node)
            )
            logger.debug("Restoring ceph ssh-keys")
            self.ssh_manager.execute_on_remote(
                remote_admin_ip, cmd,
                err_msg='Can not restore ssh-keys for ceph')

    def install_yum_components(self, ip):
        """Install required yum components on a target node.

        :param ip: Remote node ip for proceed.
        """
        cmd = "yum install yum-utils yum-priorities -y"
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not install required yum components.')

    def set_repo_for_perestroika(self, ip):
        """Set Perestroika repos.

        :param ip: Remote node ip for proceed.
        """
        repo = settings.PERESTROIKA_REPO
        cmd = ("curl {0}".format(repo))

        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Perestroika repos unavailable from node.')

        cmd = ("echo '[mos]\n"
               "name=mos\n"
               "type=rpm-md\n"
               "baseurl={0}\n"
               "gpgcheck=0\n"
               "enabled=1\n"
               "priority=5' >"
               "/etc/yum.repos.d/mos.repo && "
               "yum clean all".format(repo))
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not create config file for repo')

    def check_hiera_installation(self, ip):
        """Check hiera installation on node.

        :param ip: Remote node ip for proceed.
        """
        cmd = "yum list installed | grep hiera"
        logger.debug('Checking hiera installation...')
        result = self.ssh_manager.execute(ip, cmd)
        if result['exit_code'] == 0:
            cmd = "yum remove hiera -y"
            logger.debug('Found existing installation of hiera. Removing...')
            result = self.ssh_manager.execute(ip, cmd)
            asserts.assert_equal(result['exit_code'], 0, 'Can not remove '
                                                         'hiera')
            cmd = "ls /etc/hiera"
            logger.debug('Checking hiera files for removal...')
            result = self.ssh_manager.execute(ip, cmd)
            if result['exit_code'] == 0:
                logger.debug('Found redundant hiera files. Removing...')
                cmd = "rm -rf /etc/hiera"
                self.ssh_manager.execute_on_remote(
                    ip, cmd, err_msg='Can not remove hiera files')

    def check_rsync_installation(self, ip):
        """Check rsync installation on node.

        :param ip: Remote node ip for proceed.
        """
        cmd = "yum list installed | grep rsync"
        logger.debug("Checking rsync installation...")
        result = self.ssh_manager.execute(ip, cmd)
        if result['exit_code'] != 0:
            logger.debug("Rsync is not found. Installing rsync...")
            cmd = "yum clean all && yum install rsync -y"
            self.ssh_manager.execute_on_remote(
                ip, cmd, err_msg='Can not install rsync on node.')

    def remove_old_compute_services(self, ip, hostname):
        """Remove old redundant services which was removed from services base.

        :param ip: Remote node ip for proceed.
        :param hostname: Old compute hostname.
        """
        cmd = ("source ~/openrc && for i in $(nova service-list | "
               "awk '/{:s}/{{print $2}}'); do nova service-delete $i; "
               "done".format(hostname))
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not remove old nova computes')

        cmd = ("source ~/openrc && for i in $(neutron agent-list | "
               "awk '/{:s}/{{print $2}}'); do neutron agent-delete $i; "
               "done".format(hostname))
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not remove old neutron agents')

    def install_ruby_puppet(self, ip):
        """Install ruby and puppet on a target node.

        :param ip: Remote node ip for proceed.
        """
        puppet_install_cmd = "yum install puppet ruby -y"
        self.ssh_manager.execute_on_remote(
            ip, puppet_install_cmd,
            err_msg='Ruby and puppet installation failed')

    def rsync_puppet_modules(self, master_node_ip, ip):
        """Rsync puppet modules from remote node to node with specified ip.

        :param master_node_ip: Remote node ip for proceed.
        :param ip: IP address of a target node where to sync.
        """
        cmd = ("rsync -avz /etc/puppet/modules/* "
               "{0}@{1}:/etc/puppet/modules/".format(settings.RH_IMAGE_USER,
                                                     ip))
        self.ssh_manager.execute_on_remote(
            master_node_ip, cmd, err_msg='Rsync puppet modules failed')

    def save_node_hostname(self, ip):
        """Save hostname of a node.

        :param ip: Remote node ip for proceed.
        :return: Node hostname.
        """
        cmd = "hostname"
        result = self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not get hostname for remote')
        nodename = self.clean_string(result['stdout'][0], twice=False)
        return nodename

    def backup_hosts_file(self, ip, target_ip):
        """Backing up hosts file

        :param ip: Remote node ip to backup to.
        :param target_ip: Node ip to backup from.
        """
        cmd = "cd ~/ && scp {0}:/etc/hosts .".format(target_ip)
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not save hosts file from remote')

    def prepare_hosts_file(self, ip, old_host, new_host):
        cmd = "cd ~/ && sed -i 's/{0}/{1}/g' hosts".format(old_host, new_host)
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not prepare hosts file.')

    def restore_hosts_file(self, ip, target_ip):
        """Restore host file

        :param ip: Node ip to restore from.
        :param target_ip: Node ip to restore to.
        """
        cmd = "cd ~/ && scp hosts {0}:/etc/".format(target_ip)
        self.ssh_manager.execute_on_remote(
            ip, cmd, err_msg='Can not restore hosts file.')


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
        logger.debug('Check MD5 sum of RH 7 image')
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
        logger.debug('Create Fuel cluster RH-based compute tests')
        data = {
            'volumes_lvm': True,
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'admin',
            'user': 'admin',
            'password': 'admin'
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
                               test_sets=['smoke', 'sanity'])

        self.show_step(7)
        compute = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        controller = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]
        logger.debug('Got node: {0}'.format(compute))
        target_node = self.fuel_web.get_devops_node_by_nailgun_node(
            compute)
        logger.debug('DevOps Node: {0}'.format(target_node))
        target_node_ip = compute['ip']
        controller_ip = controller['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_ip, target_node.name))

        old_hostname = self.save_node_hostname(target_node_ip)

        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_ip)

        self.show_step(8)

        target_node.destroy()
        asserts.assert_false(target_node.driver.node_active(node=target_node),
                             'Target node still active')
        self.connect_rh_image(target_node)
        target_node.start()
        asserts.assert_true(target_node.driver.node_active(node=target_node),
                            'Target node did not start')
        self.wait_for_slave_provision(target_node_ip)
        self.verify_image_connected(target_node_ip)

        self.show_step(9)

        self.restore_information(target_node_ip, self.ssh_manager.admin_ip)

        self.set_hostname(target_node_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rh_subscription(target_node_ip)
        self.install_yum_components(target_node_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.enable_rh_repos(target_node_ip)
        self.set_repo_for_perestroika(target_node_ip)
        self.check_hiera_installation(target_node_ip)
        self.install_ruby_puppet(target_node_ip)
        self.check_rsync_installation(target_node_ip)

        self.rsync_puppet_modules(self.ssh_manager.admin_ip, target_node_ip)

        self.show_step(10)
        self.apply_first_part_puppet(target_node_ip)
        self.apply_networking_puppet(target_node_ip)
        self.check_netconfig_success(target_node_ip)
        self.apply_last_part_puppet(target_node_ip)

        self.remove_old_compute_services(controller_ip, old_hostname)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=5)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_one_controller_with_rh_compute",
                               is_make=True)


@test(groups=['rh.migration'])
class RhHAOneControllerMigration(RhBase):
    """RH-based compute HA migration test"""
    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["check_vm_migration_rh_ha_one_controller_tun"])
    @log_snapshot_after_test
    def check_vm_migration_rh_ha_one_controller_tun(self):
        """Deploy environment with RH and Ubuntu computes in HA mode with
           neutron VXLAN

        Scenario:
            1. Check required image.
            2. Revert snapshot 'ready_with_5_slaves'.
            3. Create a Fuel cluster.
            4. Update cluster nodes with required roles.
            5. Deploy the Fuel cluster.
            6. Run OSTF.
            7. Backup astute.yaml and ssh keys from one of computes.
            8. Boot compute with RH image.
            9. Prepare node for Puppet run.
            10. Execute modular tasks for compute.
            11. Run OSTF.


        Duration: 150m
        Snapshot: check_vm_migration_rh_ha_one_controller_tun

        """
        self.show_step(1, initialize=True)
        logger.debug('Check MD5 sum of RH 7 image')
        check_image = checkers.check_image(
            settings.RH_IMAGE,
            settings.RH_IMAGE_MD5,
            settings.RH_IMAGE_PATH)
        asserts.assert_true(check_image,
                            'Provided image is incorrect. '
                            'Please, check image path and md5 sum of it.')

        self.show_step(2)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(3)
        logger.debug('Create Fuel cluster RH-based compute tests')
        data = {
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'RhHAMigration',
            'user': 'RhHAMigration',
            'password': 'RhHAMigration',
            'volumes_ceph': True,
            'ephemeral_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'osd_pool_size': "1"
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
                'slave-03': ['compute'],
                'slave-04': ['ceph-osd'],
            }
        )

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            cluster_vip, data['user'], data['password'], data['tenant'])

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.show_step(7)
        compute_one = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[0]
        controller_ip = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])[0]['ip']
        logger.debug('Got node: {0}'.format(compute_one))
        target_node_one = self.fuel_web.get_devops_node_by_nailgun_node(
            compute_one)
        logger.debug('DevOps Node: {0}'.format(target_node_one))
        target_node_one_ip = compute_one['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_one_ip, target_node_one.name))

        compute_two = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'])[1]
        logger.debug('Got node: {0}'.format(compute_two))
        target_node_two = self.fuel_web.get_devops_node_by_nailgun_node(
            compute_two)
        logger.debug('DevOps Node: {0}'.format(target_node_two))
        target_node_two_ip = compute_two['ip']
        logger.debug('Acquired ip: {0} for node: {1}'.format(
            target_node_two_ip, target_node_two.name))

        old_hostname_one = self.save_node_hostname(target_node_one_ip)
        old_hostname_two = self.save_node_hostname(target_node_two_ip)

        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_one_ip, ceph=True)
        self.backup_required_information(self.ssh_manager.admin_ip,
                                         target_node_two_ip, ceph=True,
                                         node=2)
        self.backup_hosts_file(self.ssh_manager.admin_ip, controller_ip)

        self.show_step(8)

        target_node_one.destroy()
        target_node_two.destroy()
        asserts.assert_false(
            target_node_one.driver.node_active(node=target_node_one),
            'Target node still active')
        asserts.assert_false(
            target_node_two.driver.node_active(node=target_node_two),
            'Target node still active')
        self.connect_rh_image(target_node_one)
        self.connect_rh_image(target_node_two)
        target_node_one.start()
        asserts.assert_true(
            target_node_one.driver.node_active(node=target_node_one),
            'Target node did not start')
        self.wait_for_slave_provision(target_node_one_ip)
        target_node_two.start()
        asserts.assert_true(
            target_node_two.driver.node_active(node=target_node_two),
            'Target node did not start')
        self.wait_for_slave_provision(target_node_two_ip)
        self.verify_image_connected(target_node_one_ip)
        self.verify_image_connected(target_node_two_ip)

        self.show_step(9)

        self.restore_information(target_node_one_ip,
                                 self.ssh_manager.admin_ip, ceph=True)
        self.restore_information(target_node_two_ip,
                                 self.ssh_manager.admin_ip, ceph=True, node=2)

        new_host_one = self.set_hostname(target_node_one_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rh_subscription(target_node_one_ip)
        self.install_yum_components(target_node_one_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.enable_rh_repos(target_node_one_ip)
        self.set_repo_for_perestroika(target_node_one_ip)
        self.check_hiera_installation(target_node_one_ip)
        self.install_ruby_puppet(target_node_one_ip)
        self.check_rsync_installation(target_node_one_ip)

        new_host_two = self.set_hostname(target_node_two_ip, host_number=2)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rh_subscription(target_node_two_ip)
        self.install_yum_components(target_node_two_ip)
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.enable_rh_repos(target_node_two_ip)
        self.set_repo_for_perestroika(target_node_two_ip)
        self.check_hiera_installation(target_node_two_ip)
        self.install_ruby_puppet(target_node_two_ip)
        self.check_rsync_installation(target_node_two_ip)

        self.rsync_puppet_modules(self.ssh_manager.admin_ip,
                                  target_node_one_ip)
        self.rsync_puppet_modules(self.ssh_manager.admin_ip,
                                  target_node_two_ip)
        self.prepare_hosts_file(self.ssh_manager.admin_ip, old_hostname_one,
                                new_host_one)
        self.prepare_hosts_file(self.ssh_manager.admin_ip, old_hostname_two,
                                new_host_two)
        self.restore_hosts_file(self.ssh_manager.admin_ip, target_node_one_ip)
        self.restore_hosts_file(self.ssh_manager.admin_ip, target_node_two_ip)

        self.show_step(10)
        self.apply_first_part_puppet(target_node_one_ip)
        self.apply_first_part_puppet(target_node_two_ip)
        self.apply_networking_puppet(target_node_one_ip)
        self.apply_networking_puppet(target_node_two_ip)
        self.check_netconfig_success(target_node_one_ip)
        self.apply_last_part_puppet(target_node_one_ip, ceph=True)
        self.check_netconfig_success(target_node_two_ip)
        self.apply_last_part_puppet(target_node_two_ip, ceph=True)

        self.remove_old_compute_services(controller_ip, old_hostname_one)
        self.remove_old_compute_services(controller_ip, old_hostname_two)

        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=6)

        self.show_step(11)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_one_controller_with_rh_computes")
