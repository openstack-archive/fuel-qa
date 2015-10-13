#    Copyright 2013 Mirantis, Inc.
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

import re
import time
import yaml
from devops.error import TimeoutError

from devops.helpers.helpers import _tcp_ping
from devops.helpers.helpers import _wait
from devops.helpers.helpers import wait
from devops.models import Environment
from keystoneclient import exceptions
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import revert_info
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.helpers.decorators import update_rpm_packages
from fuelweb_test.helpers.decorators import upload_manifests
from fuelweb_test.helpers.eb_tables import Ebtables
from fuelweb_test.helpers.fuel_actions import AdminActions
from fuelweb_test.helpers.fuel_actions import CobblerActions
from fuelweb_test.helpers.fuel_actions import DockerActions
from fuelweb_test.helpers.fuel_actions import NailgunActions
from fuelweb_test.helpers.fuel_actions import PostgresActions
from fuelweb_test.helpers.fuel_actions import NessusActions
from fuelweb_test.helpers.ntp import GroupNtpSync
from fuelweb_test.helpers.utils import timestat
from fuelweb_test.helpers import multiple_networks_hacks
from fuelweb_test.models.fuel_web_client import FuelWebClient
from fuelweb_test.models.collector_client import CollectorClient
from fuelweb_test import settings
from fuelweb_test import logwrap
from fuelweb_test import logger


class EnvironmentModel(object):
    """EnvironmentModel."""  # TODO documentation

    def __init__(self):
        self._virtual_environment = None
        self.fuel_web = FuelWebClient(self.get_admin_node_ip(), self)

    def __repr__(self):
        klass, obj_id = type(self), hex(id(self))
        if hasattr(self, 'fuel_web'):
            ip = self.fuel_web.admin_node_ip
        else:
            ip = None
        return "[{klass}({obj_id}), ip:{ip}]".format(klass=klass,
                                                     obj_id=obj_id,
                                                     ip=ip)

    @property
    def admin_actions(self):
        return AdminActions(self.d_env.get_admin_remote())

    @property
    def nailgun_actions(self):
        return NailgunActions(self.d_env.get_admin_remote())

    @property
    def postgres_actions(self):
        return PostgresActions(self.d_env.get_admin_remote())

    @property
    def cobbler_actions(self):
        return CobblerActions(self.d_env.get_admin_remote())

    @property
    def docker_actions(self):
        return DockerActions(self.d_env.get_admin_remote())

    @property
    def admin_node_ip(self):
        return self.fuel_web.admin_node_ip

    @property
    def collector(self):
        return CollectorClient(settings.ANALYTICS_IP, 'api/v1/json')

    @logwrap
    def add_syslog_server(self, cluster_id, port=5514):
        self.fuel_web.add_syslog_server(
            cluster_id, self.d_env.router(), port)

    def bootstrap_nodes(self, devops_nodes, timeout=900, skip_timesync=False):
        """Lists registered nailgun nodes
        Start vms and wait until they are registered on nailgun.
        :rtype : List of registered nailgun nodes
        """
        # self.dhcrelay_check()

        for node in devops_nodes:
            logger.info("Bootstrapping node: {}".format(node.name))
            node.start()
            # TODO(aglarendil): LP#1317213 temporary sleep
            # remove after better fix is applied
            time.sleep(2)

        with timestat("wait_for_nodes_to_start_and_register_in_nailgun"):
            wait(lambda: all(self.nailgun_nodes(devops_nodes)), 15, timeout)

        if not skip_timesync:
            self.sync_time([node for node in self.nailgun_nodes(devops_nodes)])

        return self.nailgun_nodes(devops_nodes)

    @logwrap
    def get_admin_node_ip(self):
        return str(
            self.d_env.nodes(
            ).admin.get_ip_address_by_network_name(
                self.d_env.admin_net))

    @logwrap
    def get_ebtables(self, cluster_id, devops_nodes):
        return Ebtables(self.get_target_devs(devops_nodes),
                        self.fuel_web.client.get_cluster_vlans(cluster_id))

    def get_keys(self, node, custom=None, build_images=None,
                 iso_connect_as='cdrom'):
        params = {
            'ks': 'hd:LABEL="Mirantis_Fuel":/ks.cfg' if iso_connect_as == 'usb'
            else 'cdrom:/ks.cfg',
            'repo': 'hd:LABEL="Mirantis_Fuel":/',  # only required for USB boot
            'ip': node.get_ip_address_by_network_name(
                self.d_env.admin_net),
            'mask': self.d_env.get_network(
                name=self.d_env.admin_net).ip.netmask,
            'gw': self.d_env.router(),
            'hostname': ''.join((settings.FUEL_MASTER_HOSTNAME,
                                 settings.DNS_SUFFIX)),
            'nat_interface': self.d_env.nat_interface,
            'dns1': settings.DNS,
            'showmenu': 'yes' if custom else 'no',
            'build_images': '1' if build_images else '0'
        }
        keys = ''
        if(iso_connect_as == 'usb'):
            keys = (
                "<Wait>\n"  # USB boot uses boot_menu=yes for master node
                "<F12>\n"
                "2\n"
                "<Esc><Enter>\n"
                "<Wait>\n"
                "vmlinuz initrd=initrd.img ks=%(ks)s\n"
                " repo=%(repo)s\n"
                " ip=%(ip)s\n"
                " netmask=%(mask)s\n"
                " gw=%(gw)s\n"
                " dns1=%(dns1)s\n"
                " hostname=%(hostname)s\n"
                " dhcp_interface=%(nat_interface)s\n"
                " showmenu=%(showmenu)s\n"
                " build_images=%(build_images)s\n"
                " <Enter>\n"
            ) % params
        else:  # cdrom case is default
            keys = (
                "<Wait>\n"
                "<Wait>\n"
                "<Wait>\n"
                "<Esc>\n"
                "<Wait>\n"
                "vmlinuz initrd=initrd.img ks=%(ks)s\n"
                " ip=%(ip)s\n"
                " netmask=%(mask)s\n"
                " gw=%(gw)s\n"
                " dns1=%(dns1)s\n"
                " hostname=%(hostname)s\n"
                " dhcp_interface=%(nat_interface)s\n"
                " showmenu=%(showmenu)s\n"
                " build_images=%(build_images)s\n"
                " <Enter>\n"
            ) % params
        return keys

    def get_target_devs(self, devops_nodes):
        return [
            interface.target_dev for interface in [
                val for var in map(lambda node: node.interfaces, devops_nodes)
                for val in var]]

    @property
    def d_env(self):
        if self._virtual_environment is None:
            try:
                return Environment.get(name=settings.ENV_NAME)
            except Exception:
                self._virtual_environment = Environment.describe_environment(
                    boot_from=settings.ADMIN_BOOT_DEVICE)
                self._virtual_environment.define()
        return self._virtual_environment

    def resume_environment(self):
        self.d_env.resume()
        admin = self.d_env.nodes().admin

        try:
            admin.await(self.d_env.admin_net, timeout=30, by_port=8000)
        except Exception as e:
            logger.warning("From first time admin isn't reverted: "
                           "{0}".format(e))
            admin.destroy()
            logger.info('Admin node was destroyed. Wait 10 sec.')
            time.sleep(10)

            admin.start()
            logger.info('Admin node started second time.')
            self.d_env.nodes().admin.await(self.d_env.admin_net)
            self.set_admin_ssh_password()
            self.docker_actions.wait_for_ready_containers(timeout=600)

            # set collector address in case of admin node destroy
            if settings.FUEL_STATS_ENABLED:
                self.nailgun_actions.set_collector_address(
                    settings.FUEL_STATS_HOST,
                    settings.FUEL_STATS_PORT,
                    settings.FUEL_STATS_SSL)
                # Restart statsenderd in order to apply new collector address
                self.nailgun_actions.force_fuel_stats_sending()
                self.fuel_web.client.send_fuel_stats(enabled=True)
                logger.info('Enabled sending of statistics to {0}:{1}'.format(
                    settings.FUEL_STATS_HOST, settings.FUEL_STATS_PORT
                ))
        self.set_admin_ssh_password()
        self.docker_actions.wait_for_ready_containers()

    def make_snapshot(self, snapshot_name, description="", is_make=False):
        if settings.MAKE_SNAPSHOT or is_make:
            self.d_env.suspend(verbose=False)
            time.sleep(10)

            self.d_env.snapshot(snapshot_name, force=True)
            revert_info(snapshot_name, self.get_admin_node_ip(), description)

        if settings.FUEL_STATS_CHECK:
            self.resume_environment()

    def nailgun_nodes(self, devops_nodes):
        return map(
            lambda node: self.fuel_web.get_nailgun_node_by_devops_node(node),
            devops_nodes
        )

    def check_slaves_are_ready(self):
        devops_nodes = [node for node in self.d_env.nodes().slaves
                        if node.driver.node_active(node)]
        # Bug: 1455753
        time.sleep(30)

        for node in devops_nodes:
            try:
                wait(lambda:
                     self.fuel_web.get_nailgun_node_by_devops_node(
                         node)['online'], timeout=60 * 6)
            except TimeoutError:
                    raise TimeoutError(
                        "Node {0} does not become online".format(node.name))
        return True

    def revert_snapshot(self, name, skip_timesync=False):
        if not self.d_env.has_snapshot(name):
            return False

        logger.info('We have snapshot with such name: %s' % name)

        logger.info("Reverting the snapshot '{0}' ....".format(name))
        self.d_env.revert(name)

        logger.info("Resuming the snapshot '{0}' ....".format(name))
        self.resume_environment()

        if not skip_timesync:
            nailgun_nodes = [self.fuel_web.get_nailgun_node_by_name(node.name)
                             for node in self.d_env.nodes().slaves
                             if node.driver.node_active(node)]
            self.sync_time(nailgun_nodes)

        try:
            _wait(self.fuel_web.client.get_releases,
                  expected=EnvironmentError, timeout=300)
        except exceptions.Unauthorized:
            self.set_admin_keystone_password()
            self.fuel_web.get_nailgun_version()

        _wait(lambda: self.check_slaves_are_ready(), timeout=60 * 6)
        return True

    def set_admin_ssh_password(self):
        try:
            remote = self.d_env.get_admin_remote(
                login=settings.SSH_CREDENTIALS['login'],
                password=settings.SSH_CREDENTIALS['password'])
            self.execute_remote_cmd(remote, 'date')
            logger.debug('Accessing admin node using SSH: SUCCESS')
        except Exception:
            logger.debug('Accessing admin node using SSH credentials:'
                         ' FAIL, trying to change password from default')
            remote = self.d_env.get_admin_remote(
                login='root', password='r00tme')
            self.execute_remote_cmd(
                remote, 'echo -e "{1}\\n{1}" | passwd {0}'
                .format(settings.SSH_CREDENTIALS['login'],
                        settings.SSH_CREDENTIALS['password']))
            logger.debug("Admin node password has changed.")
        logger.info("Admin node login name: '{0}' , password: '{1}'".
                    format(settings.SSH_CREDENTIALS['login'],
                           settings.SSH_CREDENTIALS['password']))

    def set_admin_keystone_password(self):
        remote = self.d_env.get_admin_remote()
        try:
            self.fuel_web.client.get_releases()
        except exceptions.Unauthorized:
            self.execute_remote_cmd(
                remote, 'fuel user --newpass {0} --change-password'
                .format(settings.KEYSTONE_CREDS['password']))
            logger.info(
                'New Fuel UI (keystone) username: "{0}", password: "{1}"'
                .format(settings.KEYSTONE_CREDS['username'],
                        settings.KEYSTONE_CREDS['password']))

    def setup_environment(self, custom=settings.CUSTOM_ENV,
                          build_images=settings.BUILD_IMAGES,
                          iso_connect_as=settings.ADMIN_BOOT_DEVICE,
                          security=settings.SECURITY_TEST):
        # start admin node
        admin = self.d_env.nodes().admin
        if(iso_connect_as == 'usb'):
            admin.disk_devices.get(device='disk',
                                   bus='usb').volume.upload(settings.ISO_PATH)
        else:  # cdrom is default
            admin.disk_devices.get(
                device='cdrom').volume.upload(settings.ISO_PATH)
        self.d_env.start(self.d_env.nodes().admins)
        logger.info("Waiting for admin node to start up")
        wait(lambda: admin.driver.node_active(admin), 60)
        logger.info("Proceed with installation")
        # update network parameters at boot screen
        admin.send_keys(self.get_keys(admin, custom=custom,
                                      build_images=build_images,
                                      iso_connect_as=iso_connect_as))
        if custom:
            self.setup_customisation()
        if security:
            nessus_node = NessusActions(self.d_env)
            nessus_node.add_nessus_node()
        # wait while installation complete
        admin.await(self.d_env.admin_net, timeout=10 * 60)
        self.set_admin_ssh_password()
        self.admin_actions.modify_configs(self.d_env.router())
        self.wait_bootstrap()

        if settings.UPDATE_FUEL:
            # Update Ubuntu packages
            self.admin_actions.upload_packages(
                local_packages_dir=settings.UPDATE_FUEL_PATH,
                centos_repo_path=None,
                ubuntu_repo_path=settings.LOCAL_MIRROR_UBUNTU)

        self.docker_actions.wait_for_ready_containers()
        time.sleep(10)
        self.set_admin_keystone_password()
        self.sync_time()
        if settings.UPDATE_MASTER:
            if settings.UPDATE_FUEL_MIRROR:
                for i, url in enumerate(settings.UPDATE_FUEL_MIRROR):
                    conf_file = '/etc/yum.repos.d/temporary-{}.repo'.format(i)
                    cmd = ("echo -e"
                           " '[temporary-{0}]\nname="
                           "temporary-{0}\nbaseurl={1}/"
                           "\ngpgcheck=0\npriority="
                           "1' > {2}").format(i, url, conf_file)
                    with self.d_env.get_admin_remote() as remote:
                        remote.execute(cmd)
            self.admin_install_updates()
        if settings.MULTIPLE_NETWORKS:
            self.describe_second_admin_interface()
            multiple_networks_hacks.configure_second_admin_cobbler(self)
        self.nailgun_actions.set_collector_address(
            settings.FUEL_STATS_HOST,
            settings.FUEL_STATS_PORT,
            settings.FUEL_STATS_SSL)
        # Restart statsenderd in order to apply new settings(Collector address)
        self.nailgun_actions.force_fuel_stats_sending()
        if settings.FUEL_STATS_ENABLED:
            self.fuel_web.client.send_fuel_stats(enabled=True)
            logger.info('Enabled sending of statistics to {0}:{1}'.format(
                settings.FUEL_STATS_HOST, settings.FUEL_STATS_PORT
            ))
        if settings.PATCHING_DISABLE_UPDATES:
            remote = self.d_env.get_admin_remote()
            cmd = "find /etc/yum.repos.d/ -type f -regextype posix-egrep" \
                  " -regex '.*/mos[0-9,\.]+\-(updates|security).repo' | " \
                  "xargs -n1 -i sed '$aenabled=0' -i {}"
            self.execute_remote_cmd(remote, cmd)

    @update_rpm_packages
    @upload_manifests
    def wait_for_provisioning(self):
        _wait(lambda: _tcp_ping(
            self.d_env.nodes(
            ).admin.get_ip_address_by_network_name
            (self.d_env.admin_net), 22), timeout=7 * 60)

    def setup_customisation(self):
        self.wait_for_provisioning()
        try:
            remote = self.d_env.get_admin_remote()
            cmd = "pkill -sigusr1 -f '^.*/fuelmenu$'"
            wait(lambda: remote.execute(cmd)['exit_code'] == 0, timeout=60)
        except Exception:
            logger.error("Could not kill process of fuelmenu")
            raise

    @retry(count=3, delay=60)
    def sync_time(self, nailgun_nodes=[]):
        # with @retry, failure on any step of time synchronization causes
        # restart the time synchronization starting from the admin node

        controller_nodes = [
            n for n in nailgun_nodes if "controller" in n['roles']]
        other_nodes = [
            n for n in nailgun_nodes if "controller" not in n['roles']]

        # 1. The first time source for the environment: admin node
        logger.info("Synchronizing time on Fuel admin node")
        with GroupNtpSync(self, sync_admin_node=True) as g_ntp:
            g_ntp.do_sync_time()

        # 2. Controllers should be synchronized before providing time to others
        if controller_nodes:
            logger.info("Synchronizing time on all controllers")
            with GroupNtpSync(self, nailgun_nodes=controller_nodes) as g_ntp:
                g_ntp.do_sync_time()

        # 3. Synchronize time on all the rest nodes
        if other_nodes:
            logger.info("Synchronizing time on other active nodes")
            with GroupNtpSync(self, nailgun_nodes=other_nodes) as g_ntp:
                g_ntp.do_sync_time()

    def verify_network_configuration(self, node_name):
        node = self.fuel_web.get_nailgun_node_by_name(node_name)
        checkers.verify_network_configuration(
            node=node,
            remote=self.d_env.get_ssh_to_remote(node['ip'])
        )

    def wait_bootstrap(self):
        logger.info("Waiting while bootstrapping is in progress")
        log_path = "/var/log/puppet/bootstrap_admin_node.log"
        logger.info("Puppet timeout set in {0}".format(
            float(settings.PUPPET_TIMEOUT)))
        wait(
            lambda: not
            self.d_env.get_admin_remote().execute(
                "grep 'Fuel node deployment' '%s'" % log_path
            )['exit_code'],
            timeout=(float(settings.PUPPET_TIMEOUT))
        )
        result = self.d_env.get_admin_remote().execute(
            "grep 'Fuel node deployment "
            "complete' '%s'" % log_path)['exit_code']
        if result != 0:
            raise Exception('Fuel node deployment failed.')

    def dhcrelay_check(self):
        admin_remote = self.d_env.get_admin_remote()
        out = admin_remote.execute("dhcpcheck discover "
                                   "--ifaces eth0 "
                                   "--repeat 3 "
                                   "--timeout 10")['stdout']

        assert_true(self.get_admin_node_ip() in "".join(out),
                    "dhcpcheck doesn't discover master ip")

    def get_fuel_settings(self, remote=None):
        if not remote:
            remote = self.d_env.get_admin_remote()
        cmd = 'cat {cfg_file}'.format(cfg_file=settings.FUEL_SETTINGS_YAML)
        result = remote.execute(cmd)
        if result['exit_code'] == 0:
            fuel_settings = yaml.load(''.join(result['stdout']))
        else:
            raise Exception('Can\'t output {cfg_file} file: {error}'.
                            format(cfg_file=settings.FUEL_SETTINGS_YAML,
                                   error=result['stderr']))
        return fuel_settings

    def admin_install_pkg(self, pkg_name):
        """Install a package <pkg_name> on the admin node"""
        admin_remote = self.d_env.get_admin_remote()
        remote_status = admin_remote.execute("rpm -q {0}'".format(pkg_name))
        if remote_status['exit_code'] == 0:
            logger.info("Package '{0}' already installed.".format(pkg_name))
        else:
            logger.info("Installing package '{0}' ...".format(pkg_name))
            remote_status = admin_remote.execute("yum -y install {0}"
                                                 .format(pkg_name))
            logger.info("Installation of the package '{0}' has been"
                        " completed with exit code {1}"
                        .format(pkg_name, remote_status['exit_code']))
        return remote_status['exit_code']

    def admin_run_service(self, service_name):
        """Start a service <service_name> on the admin node"""
        admin_remote = self.d_env.get_admin_remote()
        admin_remote.execute("service {0} start".format(service_name))
        remote_status = admin_remote.execute("service {0} status"
                                             .format(service_name))
        if any('running...' in status for status in remote_status['stdout']):
            logger.info("Service '{0}' is running".format(service_name))
        else:
            logger.info("Service '{0}' failed to start"
                        " with exit code {1} :\n{2}"
                        .format(service_name,
                                remote_status['exit_code'],
                                remote_status['stdout']))

    # Execute yum updates
    # If updates installed,
    # then `dockerctl destroy all; bootstrap_admin_node.sh;`
    def admin_install_updates(self):
        logger.info('Searching for updates..')
        admin_remote = self.d_env.get_admin_remote()
        update_command = 'yum clean expire-cache; yum update -y'
        update_result = admin_remote.execute(update_command)
        logger.info('Result of "{1}" command on master node: '
                    '{0}'.format(update_result, update_command))
        assert_equal(int(update_result['exit_code']), 0,
                     'Packages update failed, '
                     'inspect logs for details')

        # Check if any packets were updated and update was successful
        for str_line in update_result['stdout']:
            match_updated_count = re.search("Upgrade(?:\s*)(\d+).*Package",
                                            str_line)
            if match_updated_count:
                updates_count = match_updated_count.group(1)
            match_complete_message = re.search("(Complete!)", str_line)
            match_no_updates = re.search("No Packages marked for Update",
                                         str_line)

        if (not match_updated_count or match_no_updates)\
                and not match_complete_message:
            logger.warning('No updates were found or update was incomplete.')
            return
        logger.info('{0} packet(s) were updated'.format(updates_count))

        cmd = 'dockerctl destroy all; bootstrap_admin_node.sh;'
        result = admin_remote.execute(cmd)
        logger.info('Result of "{1}" command on master node: '
                    '{0}'.format(result, cmd))
        assert_equal(int(result['exit_code']), 0,
                     'bootstrap failed, '
                     'inspect logs for details')

    # Modifies a resolv.conf on the Fuel master node and returns
    # its original content.
    # * adds 'nameservers' at start of resolv.conf if merge=True
    # * replaces resolv.conf with 'nameservers' if merge=False
    def modify_resolv_conf(self, nameservers=[], merge=True):
        remote = self.d_env.get_admin_remote()
        resolv_conf = remote.execute('cat /etc/resolv.conf')
        assert_equal(0, resolv_conf['exit_code'], 'Executing "{0}" on the '
                     'admin node has failed with: {1}'
                     .format('cat /etc/resolv.conf', resolv_conf['stderr']))
        if merge:
            nameservers.extend(resolv_conf['stdout'])

        resolv_keys = ['search', 'domain', 'nameserver']
        resolv_new = "".join('{0}\n'.format(ns) for ns in nameservers
                             if any(x in ns for x in resolv_keys))
        logger.debug('echo "{0}" > /etc/resolv.conf'.format(resolv_new))
        echo_cmd = 'echo "{0}" > /etc/resolv.conf'.format(resolv_new)
        echo_result = remote.execute(echo_cmd)
        assert_equal(0, echo_result['exit_code'], 'Executing "{0}" on the '
                     'admin node has failed with: {1}'
                     .format(echo_cmd, echo_result['stderr']))
        return resolv_conf['stdout']

    @logwrap
    def execute_remote_cmd(self, remote, cmd, exit_code=0):
        result = remote.execute(cmd)
        assert_equal(result['exit_code'], exit_code,
                     'Failed to execute "{0}" on remote host: {1}'.
                     format(cmd, result))
        return result['stdout']

    @logwrap
    def describe_second_admin_interface(self):
        remote = self.d_env.get_admin_remote()
        admin_net2_object = self.d_env.get_network(name=self.d_env.admin_net2)
        second_admin_network = admin_net2_object.ip.network
        second_admin_netmask = admin_net2_object.ip.netmask
        second_admin_if = settings.INTERFACES.get(self.d_env.admin_net2)
        second_admin_ip = str(self.d_env.nodes(
        ).admin.get_ip_address_by_network_name(self.d_env.admin_net2))
        logger.info(('Parameters for second admin interface configuration: '
                     'Network - {0}, Netmask - {1}, Interface - {2}, '
                     'IP Address - {3}').format(second_admin_network,
                                                second_admin_netmask,
                                                second_admin_if,
                                                second_admin_ip))
        add_second_admin_ip = ('DEVICE={0}\\n'
                               'ONBOOT=yes\\n'
                               'NM_CONTROLLED=no\\n'
                               'USERCTL=no\\n'
                               'PEERDNS=no\\n'
                               'BOOTPROTO=static\\n'
                               'IPADDR={1}\\n'
                               'NETMASK={2}\\n').format(second_admin_if,
                                                        second_admin_ip,
                                                        second_admin_netmask)
        cmd = ('echo -e "{0}" > /etc/sysconfig/network-scripts/ifcfg-{1};'
               'ifup {1}; ip -o -4 a s {1} | grep -w {2}').format(
            add_second_admin_ip, second_admin_if, second_admin_ip)
        logger.debug('Trying to assign {0} IP to the {1} on master node...'.
                     format(second_admin_ip, second_admin_if))
        result = remote.execute(cmd)
        assert_equal(result['exit_code'], 0, ('Failed to assign second admin '
                     'IP address on master node: {0}').format(result))
        logger.debug('Done: {0}'.format(result['stdout']))
        multiple_networks_hacks.configure_second_admin_firewall(
            self,
            second_admin_network,
            second_admin_netmask)

    @logwrap
    def get_masternode_uuid(self):
        return self.postgres_actions.run_query(
            db='nailgun',
            query="select master_node_uid from master_node_settings limit 1;")
