#    Copyright 2016 Mirantis, Inc.
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

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.replace_repos import parse_ubuntu_repo
from fuelweb_test.helpers import utils
from fuelweb_test.settings import EXTRA_DEB_REPOS
from fuelweb_test.settings import EXTRA_DEB_REPOS_PRIORITY
from fuelweb_test.settings import NEUTRON
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import NODEGROUPS
from fuelweb_test.settings import MIRROR_UBUNTU
from fuelweb_test.settings import MULTIPLE_NETWORKS
from fuelweb_test.settings import SEPARATE_SERVICE_BALANCER_PLUGIN_PATH
from fuelweb_test.settings import SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.test_net_templates_base import TestNetworkTemplatesBase
from gates_tests.helpers import exceptions


@test(groups=["thread_separate_haproxy"])
class TestSeparateHaproxy(TestNetworkTemplatesBase):
    """Test for verification of deployment with detached haproxy role."""

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["separate_haproxy"])
    @log_snapshot_after_test
    def separate_haproxy(self):
        """Deploy HA environment with separate Haproxy.

        Scenario:
            1. Revert snapshot with ready master node
            2. Copy and install external-lb and detach-haproxy plugins
            3. Bootstrap 3 slaves from default nodegroup
            4. Create cluster with Neutron VXLAN and custom nodegroups
            5. Run 'fuel-mirror' to replace cluster repositories
               with local mirrors
            6. Bootstrap 2 slaves nodes from second nodegroup
               and one node from third node group
            7. Enable plugins for cluster
            8. Add 2 controllers from default nodegroup and 1 controller
               from second node group
            9. Add 1 compute+cinder from default node group
               and 1 compute+cinder from second node group
            10. Add haproxy node from third node group
            11. Verify networks
            12. Deploy cluster

        Duration 120m
        Snapshot separate_haproxy
        """

        if not MULTIPLE_NETWORKS:
            raise exceptions.FuelQAVariableNotSet(
                'MULTIPLE_NETWORKS', 'true')

        self.show_step(1)
        self.env.revert_snapshot('ready')

        self.show_step(2)
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH,
            tar_target="/var")

        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=SEPARATE_SERVICE_BALANCER_PLUGIN_PATH,
            tar_target="/var")

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH))

        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(
                SEPARATE_SERVICE_BALANCER_PLUGIN_PATH))

        self.show_step(3)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[0:3])
        self.show_step(4)
        admin_ip = self.ssh_manager.admin_ip
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings={
                'net_provider': NEUTRON,
                'net_segment_type': NEUTRON_SEGMENT['tun'],
                'tenant': 'separatehaproxy',
                'user': 'separatehaproxy',
                'password': 'separatehaproxy',
                'ntp_list': [admin_ip],
            }
        )
        self.show_step(5)
        if MIRROR_UBUNTU != '':
            ubuntu_url = MIRROR_UBUNTU.split()[1]
            replace_cmd = \
                "sed -i 's,http://archive.ubuntu.com/ubuntu,{0},g'" \
                " /usr/share/fuel-mirror/ubuntu.yaml".format(
                    ubuntu_url)
            self.ssh_manager.execute_on_remote(ip=admin_ip,
                                               cmd=replace_cmd)
        if EXTRA_DEB_REPOS != '':
            # replace mos-base-url to snapshot url
            extra_deb_repo = EXTRA_DEB_REPOS.split('|')[0]
            mos_url = parse_ubuntu_repo(extra_deb_repo, None,
                                        EXTRA_DEB_REPOS_PRIORITY)['uri']
            replace_cmd = "sed -i 's,http://mirror.fuel-infra.org/mos-repos/" \
                          "ubuntu/$mos_version,{0},g'"\
                          " /usr/share/fuel-mirror/ubuntu.yaml".format(mos_url)
            self.ssh_manager.execute_on_remote(ip=admin_ip,
                                               cmd=replace_cmd)

        # add proposed repository
        with utils.YamlEditor("/usr/share/fuel-mirror/ubuntu.yaml",
                              ip=admin_ip) as editor:
            proposed_desc = {
                str("name"): "mos-proposed",
                "uri": editor.content['mos_baseurl'],
                "suite": "mos$mos_version-proposed",
                "section": "main restricted",
                "type": "deb",
                "priority": 1050
            }
            editor.content["groups"]["mos"].append(proposed_desc)
            editor.content["repos"].append(proposed_desc)


        create_mirror_cmd = 'fuel-mirror create -P ubuntu -G mos ubuntu'
        self.ssh_manager.execute_on_remote(ip=admin_ip, cmd=create_mirror_cmd)
        apply_mirror_cmd = 'fuel-mirror apply -P ubuntu -G mos ubuntu ' \
                           '--env {0} --replace'.format(cluster_id)
        self.ssh_manager.execute_on_remote(ip=admin_ip, cmd=apply_mirror_cmd)

        self.show_step(6)
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[3:5])
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[6:7])

        self.show_step(7)
        plugin_name = 'detach_haproxy'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        plugin_name = 'external_loadbalancer'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        nodegroup1 = NODEGROUPS[0]['name']
        nodegroup2 = NODEGROUPS[1]['name']
        nodegroup3 = NODEGROUPS[2]['name']

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': [['controller'], nodegroup1],
                'slave-02': [['controller'], nodegroup1],
                'slave-04': [['compute', 'cinder'], nodegroup2],
                'slave-05': [['controller'], nodegroup2],
                'slave-03': [['compute', 'cinder'], nodegroup1],
                'slave-07': [['standalone-haproxy'], nodegroup3]
            }
        )

        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(12)
        self.fuel_web.deploy_cluster_wait(cluster_id, timeout=180 * 60,
                                          check_services=False)

        self.env.make_snapshot('separate_haproxy')
