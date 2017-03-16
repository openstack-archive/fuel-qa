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

import os
import time

from devops.helpers.helpers import wait
from devops.helpers.templates import get_devops_config

from proboscis import TestProgram
from proboscis import SkipTest
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.fuel_release_hacks import install_mos_repos
from fuelweb_test.helpers.utils import erase_data_from_hdd
from fuelweb_test.helpers.utils import get_test_method_name
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.models.environment import EnvironmentModel
from fuelweb_test.settings import CUSTOM_FUEL_SETTING_YAML
from fuelweb_test.settings import EXTERNAL_HAPROXY_TEMPLATE
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import MULTIPLE_NETWORKS_TEMPLATE
from fuelweb_test.settings import ENABLE_DMZ
from fuelweb_test.settings import ENABLE_DMZ_TEMPLATE
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS
from fuelweb_test.settings import REPLACE_DEFAULT_REPOS_ONLY_ONCE
from fuelweb_test.settings import SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH
from fuelweb_test.settings import USE_HAPROXY_TEMPLATE


class TestBasic(object):
    """Basic test case class for all system tests.

    Initializes EnvironmentModel and FuelWebModel.

    """
    def __init__(self):
        self._devops_config = None
        self.__env = None
        self.__current_log_step = 0
        self.__test_program = None
        self.__fuel_constants = {
            'rabbit_pcs_name': 'p_rabbitmq-server'
        }

    @property
    def fuel_constants(self):
        return self.__fuel_constants

    @property
    def ssh_manager(self):
        return SSHManager()

    @property
    def current_log_step(self):
        return self.__current_log_step

    @current_log_step.setter
    def current_log_step(self, new_val):
        self.__current_log_step = new_val

    @property
    def next_step(self):
        return self.current_log_step + 1

    @property
    def test_program(self):
        if self.__test_program is None:
            self.__test_program = TestProgram()
        return self.__test_program

    @property
    def env(self):
        if self.__env is None:
            # hack before we find proper solution for loading devops templates
            external_config = os.environ.get("DEVOPS_SETTINGS_TEMPLATE", None)
            if external_config:
                config = get_devops_config(external_config)
            else:
                config = self._devops_config
            self.__env = EnvironmentModel(config)
        return self.__env

    @property
    def fuel_web(self):
        return self.env.fuel_web

    def check_run(self, snapshot_name):
        """Checks if run of current test is required.

        :param snapshot_name: Name of the snapshot the function should make
        :type snapshot_name: str
        :raises: SkipTest

        """
        if snapshot_name:
            if self.env.d_env.has_snapshot(snapshot_name):
                raise SkipTest('Snapshot {} already exist'.format(
                    snapshot_name))

    def show_step(self, step, details='', initialize=False):
        """Show a description of the step taken from docstring
           :param int/str step: step number to show
           :param str details: additional info for a step
        """
        test_func_name = get_test_method_name()

        if initialize or step == 1:
            self.current_log_step = step
        else:
            self.current_log_step += 1
            if self.current_log_step != step:
                error_message = 'The step {} should be {} at {}'
                error_message = error_message.format(
                    step,
                    self.current_log_step,
                    test_func_name
                )
                logger.error(error_message)

        test_func = getattr(self.__class__, test_func_name)
        docstring = test_func.__doc__
        docstring = '\n'.join([s.strip() for s in docstring.split('\n')])
        steps = {s.split('. ')[0]: s for s in
                 docstring.split('\n') if s and s[0].isdigit()}
        if details:
            details_msg = ': {0} '.format(details)
        else:
            details_msg = ''
        if str(step) in steps:
            logger.info("\n" + " " * 55 + "<<< {0} {1}>>>"
                        .format(steps[str(step)], details_msg))
        else:
            logger.info("\n" + " " * 55 + "<<< {0}. (no step description "
                        "in scenario) {1}>>>".format(str(step), details_msg))

    def is_make_snapshot(self):
        """Check if the test 'test_name' is a dependency for other planned
        tests (snapshot is required). If yes return True, if no - False.

        :rtype: bool
        """
        test_name = get_test_method_name()
        tests = self.test_program.plan.tests
        test_cases = [t for t in tests if t.entry.method.__name__ == test_name]
        if len(test_cases) != 1:
            logger.warning("Method 'is_make_snapshot' is called from function "
                           "which is not a test case: {0}".format(test_name))
            return False
        test_groups = set(test_cases[0].entry.info.groups)
        dependent_tests = set()
        dependent_groups = set()
        for t in tests:
            for func in t.entry.info.depends_on:
                dependent_tests.add(func.__name__)
            for group in t.entry.info.depends_on_groups:
                dependent_groups.add(group)
        if test_name in dependent_tests or \
                test_groups & dependent_groups:
            return True
        return False

    def fuel_post_install_actions(self,
                                  force_ssl=settings.FORCE_HTTPS_MASTER_NODE
                                  ):
        if settings.UPDATE_FUEL:
            # Update Ubuntu packages
            self.env.admin_actions.upload_packages(
                local_packages_dir=settings.UPDATE_FUEL_PATH,
                centos_repo_path=None,
                ubuntu_repo_path=settings.LOCAL_MIRROR_UBUNTU)
        time.sleep(10)
        self.env.set_admin_keystone_password()
        self.env.sync_time(['admin'])
        if settings.UPDATE_MASTER:
            if settings.UPDATE_FUEL_MIRROR:
                for i, url in enumerate(settings.UPDATE_FUEL_MIRROR):
                    conf_file = '/etc/yum.repos.d/temporary-{}.repo'.format(i)
                    cmd = ("echo -e"
                           " '[temporary-{0}]\nname="
                           "temporary-{0}\nbaseurl={1}/"
                           "\ngpgcheck=0\npriority="
                           "1' > {2}").format(i, url, conf_file)

                    self.ssh_manager.execute(
                        ip=self.ssh_manager.admin_ip,
                        cmd=cmd
                    )
            self.env.admin_install_updates()
        if settings.MULTIPLE_NETWORKS:
            self.env.describe_other_admin_interfaces(
                self.env.d_env.nodes().admin)
        if settings.FUEL_STATS_HOST:
            self.env.nailgun_actions.set_collector_address(
                settings.FUEL_STATS_HOST,
                settings.FUEL_STATS_PORT,
                settings.FUEL_STATS_SSL)
            # Restart statsenderd to apply settings(Collector address)
            self.env.nailgun_actions.force_fuel_stats_sending()
        if settings.FUEL_STATS_ENABLED and settings.FUEL_STATS_HOST:
            self.fuel_web.client.send_fuel_stats(enabled=True)
            logger.info('Enabled sending of statistics to {0}:{1}'.format(
                settings.FUEL_STATS_HOST, settings.FUEL_STATS_PORT
            ))
        if settings.PATCHING_DISABLE_UPDATES:
            cmd = "find /etc/yum.repos.d/ -type f -regextype posix-egrep" \
                  " -regex '.*/mos+\-(updates|security).repo' | " \
                  "xargs -n1 -i sed -i 's/enabled=1/enabled=0/' -i {}"
            self.ssh_manager.execute_on_remote(
                ip=self.ssh_manager.admin_ip,
                cmd=cmd
            )
        if force_ssl:
            self.env.enable_force_https(self.ssh_manager.admin_ip)
        # enable nailgun debug log for more informative app.log file
        self.env.nailgun_actions.update_nailgun_settings({"DEVELOPMENT": True})

    def reinstall_master_node(self):
        """Erase boot sector and run setup_environment"""
        admin = self.env.d_env.get_node(name="admin")
        with self.env.d_env.get_admin_remote() as remote:
            erase_data_from_hdd(remote, mount_point='/boot')
        admin.destroy()
        admin.close_tray()
        if settings.ADMIN_BOOT_DEVICE == 'usb':
            volume = admin.disk_devices.get(device='disk', bus='usb').volume
        else:  # cdrom is default
            volume = admin.disk_devices.get(device='cdrom').volume
        volume.upload(settings.ISO_PATH)
        self.env.setup_environment()
        self.fuel_post_install_actions()

    def centos_setup_fuel(self, hostname):
        with TimeStat("bootstrap_centos_node", is_uniq=True):
            admin = list(self.env.d_env.get_nodes(role__contains='master'))[0]
            self.env.d_env.start([admin])
            logger.info("Waiting for Centos node to start up")
            wait(lambda: admin.driver.node_active(admin), 60,
                 timeout_msg='Centos node failed to start')
            logger.info("Waiting for Centos node ssh ready")
            self.env.wait_for_provisioning()

        ssh = SSHManager()
        logger.debug("Update host information")
        cmd = "echo HOSTNAME={} >> /etc/sysconfig/network".format(hostname)
        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

        cmd = "echo {0} {1} {2} >> /etc/hosts".format(
            ssh.admin_ip,
            hostname,
            settings.FUEL_MASTER_HOSTNAME)

        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

        cmd = "hostname {}".format(hostname)
        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

        cmd = "yum install -y screen"
        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

        install_mos_repos()

        logger.info("Install Fuel services")

        cmd = "screen -dm bash -c 'showmenu=no wait_for_external_config=yes " \
              "bootstrap_admin_node.sh'"
        ssh.execute_on_remote(ssh.admin_ip, cmd=cmd)

        self.env.wait_for_external_config()
        self.env.admin_actions.modify_configs(self.env.d_env.get_default_gw())
        if CUSTOM_FUEL_SETTING_YAML:
            self.env.admin_actions.update_fuel_setting_yaml(
                CUSTOM_FUEL_SETTING_YAML)
        self.env.kill_wait_for_external_config()

        self.env.wait_bootstrap()

        logger.debug("Check Fuel services")
        self.env.admin_actions.wait_for_fuel_ready()

        logger.debug("post-installation configuration of Fuel services")
        self.fuel_post_install_actions()


@test
class SetupEnvironment(TestBasic):
    @test(groups=["setup"])
    @log_snapshot_after_test
    def setup_master(self):
        """Create environment and set up master node

        Snapshot: empty

        """
        # TODO: remove this code when fuel-devops will be ready to
        # describe all required network parameters (gateway, CIDR, IP range)
        # inside 'address_pool', so we can use 'network_pools' section
        # for L3 configuration in tests for multi racks
        if MULTIPLE_NETWORKS:
            from system_test.core.discover import load_yaml
            self._devops_config = load_yaml(MULTIPLE_NETWORKS_TEMPLATE)
        if USE_HAPROXY_TEMPLATE and SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH:
            from system_test.core.discover import load_yaml
            self._devops_config = load_yaml(EXTERNAL_HAPROXY_TEMPLATE)
        if ENABLE_DMZ:
            from system_test.core.discover import load_yaml
            self._devops_config = load_yaml(ENABLE_DMZ_TEMPLATE)

        self.check_run("empty")

        with TimeStat("setup_environment", is_uniq=True):

            if list(self.env.d_env.get_nodes(role='fuel_master')):
                self.env.setup_environment()
                self.fuel_post_install_actions()

            elif list(self.env.d_env.get_nodes(role='centos_master')):
                # need to use centos_master.yaml devops template
                hostname = ''.join((settings.FUEL_MASTER_HOSTNAME,
                                    settings.DNS_SUFFIX))
                self.centos_setup_fuel(hostname)

            else:
                raise SkipTest(
                    "No Fuel master nodes found!")

        self.env.make_snapshot("empty", is_make=True)
        self.current_log_step = 0

    @test(groups=["setup_master_custom_manifests"])
    @log_snapshot_after_test
    def setup_with_custom_manifests(self):
        """Setup master node with custom manifests
        Scenario:
            1. Start installation of master
            2. Enable option 'wait_for_external_config'
            3. Upload custom manifests
            4. Kill 'wait_for_external_config' countdown
        Snapshot: empty_custom_manifests

        Duration 20m
        """
        self.check_run("empty_custom_manifests")
        self.show_step(1, initialize=True)
        self.show_step(2)
        self.env.setup_environment(custom=True, build_images=True)
        self.show_step(3)
        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
            self.fuel_post_install_actions()
        self.env.make_snapshot("empty_custom_manifests", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[setup_master], groups=["prepare_release"])
    @log_snapshot_after_test
    def prepare_release(self):
        """Prepare master node

        Scenario:
            1. Revert snapshot "empty"
            2. Download the release if needed. Uploads custom manifest.

        Snapshot: ready

        """
        self.check_run("ready")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()
        self.show_step(2)
        if REPLACE_DEFAULT_REPOS and REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            self.fuel_web.replace_default_repos()
        self.env.make_snapshot("ready", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_1"])
    @log_snapshot_after_test
    def prepare_slaves_1(self):
        """Bootstrap 1 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 1 slave nodes

        Snapshot: ready_with_1_slaves

        """
        self.check_run("ready_with_1_slaves")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:1],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_1_slaves", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_3"])
    @log_snapshot_after_test
    def prepare_slaves_3(self):
        """Bootstrap 3 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 3 slave nodes

        Snapshot: ready_with_3_slaves

        """
        self.check_run("ready_with_3_slaves")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:3],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_3_slaves", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_5"])
    @log_snapshot_after_test
    def prepare_slaves_5(self):
        """Bootstrap 5 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 5 slave nodes

        Snapshot: ready_with_5_slaves

        """
        self.check_run("ready_with_5_slaves")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready", skip_timesync=True)
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:5],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_5_slaves", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_9"])
    @log_snapshot_after_test
    def prepare_slaves_9(self):
        """Bootstrap 9 slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start 9 slave nodes

        Snapshot: ready_with_9_slaves

        """
        self.check_run("ready_with_9_slaves")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready", skip_timesync=True)
        # Bootstrap 9 slaves in two stages to get lower load on the host
        self.show_step(2)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:5],
                                 skip_timesync=True)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[5:9],
                                 skip_timesync=True)
        self.env.make_snapshot("ready_with_9_slaves", is_make=True)
        self.current_log_step = 0

    @test(depends_on=[prepare_release],
          groups=["prepare_slaves_all"])
    @log_snapshot_after_test
    def prepare_slaves_all(self):
        """Bootstrap all slave nodes

        Scenario:
            1. Revert snapshot "ready"
            2. Start all available slave nodes

        Snapshot: ready_with_all_slaves

        """
        self.check_run("ready_with_all_slaves")
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready", skip_timesync=True)

        # Bootstrap by 5 slaves at the same time
        self.show_step(2)
        slaves = self.env.d_env.nodes().slaves[:]

        while slaves:
            slaves_to_bootstrap = slaves[:5]
            self.env.bootstrap_nodes(slaves_to_bootstrap, skip_timesync=True)
            del slaves[:5]

        self.env.make_snapshot("ready_with_all_slaves", is_make=True)
        self.current_log_step = 0
