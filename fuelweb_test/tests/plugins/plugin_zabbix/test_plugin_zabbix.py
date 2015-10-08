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
import os
import urllib
import urlparse

import bs4
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis import test
import requests

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as conf
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


class ZabbixWeb(object):
    def __init__(self, public_vip, username, password, verify=False):
        self.session = requests.Session()
        self.base_url = "https://{0}/zabbix/".format(public_vip)
        self.username = username
        self.password = password
        self.verify = verify

    def login(self):
        login_params = urllib.urlencode({'request': '',
                                         'name': self.username,
                                         'password': self.password,
                                         'autologin': 1,
                                         'enter': 'Sign in'})
        url = urlparse.urljoin(self.base_url, '?{0}'.format(login_params))
        response = self.session.post(url, verify=self.verify)

        assert_equal(response.status_code, 200,
                     "Login to Zabbix failed: {0}".format(response.content))

    def get_trigger_statuses(self):
        url = urlparse.urljoin(self.base_url, 'tr_status.php')
        response = self.session.get(url, verify=self.verify)

        assert_equal(response.status_code, 200,
                     "Getting Zabbix trigger statuses failed: {0}"
                     .format(response.content))

        return response.content

    def get_screens(self):
        url = urlparse.urljoin(self.base_url, 'screens.php')
        response = self.session.get(url, verify=self.verify)

        assert_equal(response.status_code, 200,
                     "Getting Zabbix screens failed: {0}"
                     .format(response.content))

        return response.content


@test(groups=["plugins", "zabbix_plugins"])
class ZabbixPlugin(TestBasic):
    """ZabbixPlugin."""

    def setup_zabbix_plugin(self,
                            cluster_id,
                            zabbix_username='admin',
                            zabbix_password='zabbix'):
        plugin_name = 'zabbix_monitoring'

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted")
        plugin_options = {'metadata/enabled': True,
                          'username/value': zabbix_username,
                          'password/value': zabbix_password}
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)

    def setup_snmp_plugin(self,
                          cluster_id,
                          snmp_community='public'):
        plugin_name = 'zabbix_snmptrapd'

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted")
        plugin_options = {'metadata/enabled': True,
                          'community/value': snmp_community}
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)

    def setup_snmp_emc_plugin(self, cluster_id):
        plugin_name = 'zabbix_monitoring_emc'

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted")

        plugin_options = {'metadata/enabled': True,
                          'hosts/value': 'emc:10.109.2.2'}
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)

    def setup_snmp_extreme_plugin(self, cluster_id):
        plugin_name = 'zabbix_monitoring_extreme_networks'

        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            "Plugin couldn't be enabled. Check plugin version. Test aborted")

        plugin_options = {'metadata/enabled': True,
                          'hosts/value': 'extreme:10.109.2.2'}
        self.fuel_web.update_plugin_data(
            cluster_id, plugin_name, plugin_options)

    def check_event_message(self, zabbix_web, zabbix_hostgroup, message):
        statuses_html = bs4.BeautifulSoup(zabbix_web.get_trigger_statuses())
        status_lines = statuses_html.find_all('tr', {'class': 'even_row'})

        for status_line in status_lines:
            host_span = status_line.find('span', {'class': 'link_menu'})
            if not host_span or host_span.get_text() != zabbix_hostgroup:
                continue

            host_span = (status_line.find('span', {'class': 'pointer'}).
                         find('span', {'class': 'link_menu'}))
            if host_span and message in host_span.get_text():
                return True
        return False

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_ha"])
    @log_snapshot_after_test
    def deploy_zabbix_ha(self):
        """Deploy cluster in ha mode with zabbix plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute role
            6. Add 1 node with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF
            10. Check zabbix service in pacemaker
            11. Check login to zabbix dashboard

        Duration 70m
        Snapshot deploy_zabbix_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            checkers.upload_tarball(
                remote, conf.ZABBIX_PLUGIN_PATH, "/var")
            checkers.install_plugin_check_code(
                remote,
                plugin=os.path.basename(conf.ZABBIX_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        zabbix_username = 'admin'
        zabbix_password = 'zabbix'
        self.setup_zabbix_plugin(cluster_id, zabbix_username, zabbix_password)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute"],
                "slave-05": ["cinder"]
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        cmd = "crm resource status p_zabbix-server"
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            response = remote.execute(cmd)["stdout"][0]
        assert_true("p_zabbix-server is running" in response,
                    "p_zabbix-server resource wasn't found in pacemaker:\n{0}"
                    .format(response))

        public_vip = self.fuel_web.get_public_vip(cluster_id)

        zabbix_web = ZabbixWeb(public_vip, zabbix_username, zabbix_password)
        zabbix_web.login()

        screens_html = bs4.BeautifulSoup(zabbix_web.get_screens())
        screens_links = screens_html.find_all('a')
        assert_true(any('charts.php?graphid=' in link.get('href')
                        for link in screens_links),
                    "Zabbix screen page does not contain graphs:\n{0}".
                    format(screens_links))

        self.env.make_snapshot("deploy_zabbix_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_snmptrap_ha"])
    @log_snapshot_after_test
    def deploy_zabbix_snmptrap_ha(self):
        """Deploy cluster in ha mode with zabbix snmptrap plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute role
            6. Add 1 node with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF
            10. Check zabbix service in pacemaker
            11. Check login to zabbix dashboard
            12. Check SNMP services on controllers
            13. Check test SNMP trap

        Duration 70m
        Snapshot deploy_zabbix_snmptrap_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            for plugin in [conf.ZABBIX_PLUGIN_PATH,
                           conf.ZABBIX_SNMP_PLUGIN_PATH]:
                checkers.upload_tarball(
                    remote, plugin, "/var")
                checkers.install_plugin_check_code(
                    remote,
                    plugin=os.path.basename(plugin))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        zabbix_username = 'admin'
        zabbix_password = 'zabbix'
        snmp_community = 'public'

        self.setup_zabbix_plugin(cluster_id)
        self.setup_snmp_plugin(cluster_id, snmp_community)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute"],
                "slave-05": ["cinder"]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        cmd = "crm resource status p_zabbix-server"
        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            response = remote.execute(cmd)["stdout"][0]
        assert_true("p_zabbix-server is running" in response,
                    "p_zabbix-server resource wasn't found in pacemaker:\n{0}"
                    .format(response))

        public_vip = self.fuel_web.get_public_vip(cluster_id)

        zabbix_web = ZabbixWeb(public_vip, zabbix_username, zabbix_password)
        zabbix_web.login()

        screens_html = bs4.BeautifulSoup(zabbix_web.get_screens())
        screens_links = screens_html.find_all('a')
        assert_true(any('charts.php?graphid=' in link.get('href')
                        for link in screens_links),
                    "Zabbix screen page does not contain graphs:\n{0}".
                    format(screens_links))

        for node_name in ['slave-01', 'slave-02', 'slave-03']:
            with self.fuel_web.get_ssh_for_node(node_name) as remote:
                cmd = 'pgrep {0}'
                response = \
                    ''.join(remote.execute(cmd.format('snmptrapd'))["stdout"])
                assert_not_equal(response.strip(), "OK",
                                 "Service {0} not started".format('snmptrapd'))
                response = \
                    ''.join(remote.execute(cmd.format('snmptt'))["stdout"])
                assert_not_equal(response.strip(), "OK",
                                 "Service {0} not started".format('snmptt'))

        management_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        snmp_heartbeat_command = \
            ("snmptrap -v 2c -c {0} {1} '' .1.3.6.1.4.1.8072.2.3.0.1"
             .format(snmp_community, management_vip))

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            remote.execute("apt-get install snmp -y")
            remote.execute(snmp_heartbeat_command)

        mgmt_vip_devops_node = self.fuel_web.get_pacemaker_resource_location(
            'slave-01', 'vip__management')[0]
        mgmt_vip_nailgun_node = self.fuel_web.get_nailgun_node_by_devops_node(
            mgmt_vip_devops_node)

        with self.env.d_env.get_ssh_to_remote(
                mgmt_vip_nailgun_node['ip']) as remote:
            cmd = ('grep netSnmpExampleHeartbeatNotification '
                   '/var/log/zabbix/zabbix_server.log | '
                   'grep "Status Events"')

            wait(lambda: remote.execute(cmd)['exit_code'] == 0)

        self.env.make_snapshot("deploy_zabbix_snmptrap_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_snmp_emc_ha"])
    @log_snapshot_after_test
    def deploy_zabbix_snmp_emc_ha(self):
        """Deploy cluster in ha mode with zabbix emc plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugins: zabbix, zabbix snmp and zabbix emc
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute role
            6. Add 1 node with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF
            10. Check EMC trigger with test SNMP message

        Duration 70m
        Snapshot deploy_zabbix_snmp_emc_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            for plugin in [conf.ZABBIX_PLUGIN_PATH,
                           conf.ZABBIX_SNMP_PLUGIN_PATH,
                           conf.ZABBIX_SNMP_EMC_PLUGIN_PATH]:
                checkers.upload_tarball(
                    remote, plugin, "/var")
                checkers.install_plugin_check_code(
                    remote,
                    plugin=os.path.basename(plugin))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        zabbix_username = 'admin'
        zabbix_password = 'zabbix'
        snmp_community = 'public'

        self.setup_zabbix_plugin(cluster_id, zabbix_username, zabbix_password)
        self.setup_snmp_plugin(cluster_id, snmp_community)
        self.setup_snmp_emc_plugin(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute"],
                "slave-05": ["cinder"]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        management_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        snmp_emc_critical_command = \
            ("snmptrap -v 1 -c {snmp_community} {management_vip} "
             "'.1.3.6.1.4.1.1981' {management_vip} 6 6 '10' .1.3.6.1.4.1.1981 "
             "s 'null' .1.3.6.1.4.1.1981 s 'null' .1.3.6.1.4.1.1981 s 'a37'"
             .format(snmp_community=snmp_community,
                     management_vip=management_vip))

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            remote.execute("apt-get install snmp -y")
            remote.execute(snmp_emc_critical_command)

        public_vip = self.fuel_web.get_public_vip(cluster_id)
        zabbix_web = ZabbixWeb(public_vip, zabbix_username, zabbix_password)
        zabbix_web.login()

        wait(lambda: self.check_event_message(
            zabbix_web, 'emc', 'SNMPtrigger Critical'))

        self.env.make_snapshot("deploy_zabbix_snmp_emc_ha")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_snmp_extreme_ha"])
    @log_snapshot_after_test
    def deploy_zabbix_snmp_extreme_ha(self):
        """Deploy cluster in ha mode with zabbix snmptrap plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugins
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 1 node with compute role
            6. Add 1 node with cinder role
            7. Deploy the cluster
            8. Run network verification
            9. Run OSTF
            10. Check Extreme Switch trigger with test SNMP message

        Duration 70m
        Snapshot deploy_zabbix_snmp_extreme_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        with self.env.d_env.get_admin_remote() as remote:
            for plugin in [conf.ZABBIX_PLUGIN_PATH,
                           conf.ZABBIX_SNMP_PLUGIN_PATH,
                           conf.ZABBIX_SNMP_EXTREME_PLUGIN_PATH]:
                checkers.upload_tarball(
                    remote, plugin, "/var")
                checkers.install_plugin_check_code(
                    remote,
                    plugin=os.path.basename(plugin))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
        )

        zabbix_username = 'admin'
        zabbix_password = 'zabbix'
        snmp_community = 'public'

        self.setup_zabbix_plugin(cluster_id, zabbix_username, zabbix_password)
        self.setup_snmp_plugin(cluster_id, snmp_community)
        self.setup_snmp_extreme_plugin(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                "slave-01": ["controller"],
                "slave-02": ["controller"],
                "slave-03": ["controller"],
                "slave-04": ["compute"],
                "slave-05": ["cinder"]
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        management_vip = self.fuel_web.get_mgmt_vip(cluster_id)
        snmp_extreme_critical_command = \
            ("snmptrap -v 1 -c {snmp_community} {management_vip} "
             "'.1.3.6.1.4.1.1916' {management_vip} 6 10 '10' .1.3.6.1.4.1.1916"
             " s 'null' .1.3.6.1.4.1.1916 s 'null' .1.3.6.1.4.1.1916 s '2'"
             .format(snmp_community=snmp_community,
                     management_vip=management_vip))

        with self.fuel_web.get_ssh_for_node("slave-01") as remote:
            remote.execute("apt-get install snmp -y")
            remote.execute(snmp_extreme_critical_command)

        public_vip = self.fuel_web.get_public_vip(cluster_id)
        zabbix_web = ZabbixWeb(public_vip, zabbix_username, zabbix_password)
        zabbix_web.login()

        wait(lambda: self.check_event_message(
            zabbix_web, 'extreme', 'Power Supply Failed'))

        self.env.make_snapshot("deploy_zabbix_snmp_extreme_ha")
