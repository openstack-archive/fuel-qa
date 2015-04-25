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
import re

import bs4
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test
import requests

from fuelweb_test import logger
from fuelweb_test import settings as conf
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class ZabbixPlugin(TestBasic):

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_zabbix_ha"])
    @log_snapshot_on_error
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
            9. check plugin health
            10. Run OSTF

        Duration 70m
        Snapshot deploy_zabbix_ha

        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(), conf.ZABBIX_PLUGIN_PATH, "/var")

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(conf.ZABBIX_PLUGIN_PATH))

        settings = None

        if conf.NEUTRON_ENABLE:
            settings = {
                "net_provider": "neutron",
                "net_segment_type": conf.NEUTRON_SEGMENT_TYPE
            }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=conf.DEPLOYMENT_MODE,
            settings=settings
        )

        plugin_name = 'zabbix_monitoring'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        logger.debug('we have zabbix_monitoring element')
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

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

        logger.debug("Start checking service on node slave-01")
        cmd = "crm resource status p_zabbix-server"
        remote = self.fuel_web.get_ssh_for_node("slave-01")
        response = remote.execute(cmd)["stdout"][0]
        assert_true("p_zabbix-server is running" in response,
                    "Response: {0}".format(response))

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        logger.debug("Start checking login to zabbix dashboard")
        zabbix_ip = self.fuel_web.get_public_vip(cluster_id)
        zabbix_url = "http://{0}/zabbix/".format(zabbix_ip)
        req = "request=&name=admin&password=zabbix&autologin=1&enter=Sign+in"
        session = requests.Session()
        res = session.post("{0}?{1}".format(zabbix_url, req))
        assert_equal(res.status_code, 200, "HTTP {0}".format(res.status_code))

        logger.debug("Zabbix dashboard {0}".format(zabbix_url))
        res = session.get("{0}/screens.php".format(zabbix_url))
        assert_equal(res.status_code, 200, "HTTP {0}".format(res.status_code))
        soup = bs4.BeautifulSoup(res.content)
        output = soup.find_all('a')

        screen_graphids = []
        for s in output:
            m = re.match(r".*graphid=(?P<id>\d+).*", "{0}".format(s))
            if m:
                screen_graphids.append(m.group("id"))
        assert_true(screen_graphids, "No Graphs at the screen")

        self.env.make_snapshot("deploy_zabbix_ha")
