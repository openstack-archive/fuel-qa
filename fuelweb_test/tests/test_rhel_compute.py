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
from devops.helpers.helpers import _wait
from devops.helpers.helpers import _tcp_ping
from proboscis import asserts
from proboscis import test
from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test import settings
from fuelweb_test import logger as LOGGER
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["rhel", "rhel_ha", "rhel.basic"])
class RhelHA(TestBasic):
    """RHEL-based compute tests"""

    def wait_for_slave_provision(self, slave_name, timeout=10 * 60):
        _wait(lambda: _tcp_ping(
            self.env.d_env.get_node(
                name=slave_name).get_ip_address_by_network_name
            (self.env.d_env.admin_net), 22), timeout=timeout)

    def connect_rhel_image(self, slave):
        """Upload RHEL image into target node

        :param slave: Target node name
        """
        path = settings.RHEL_IMAGE_PATH + settings.RHEL_IMAGE
        if settings.COMPUTE_BOOT_STRATEGY == 'usb':
            slave.disk_devices.get(
                device='disk', bus='usb').volume.upload(path)
        elif settings.COMPUTE_BOOT_STRATEGY == 'cdrom':
            slave.disk_devices.get(
                device='cdrom').volume.upload(path)
        else:
            slave.disk_devices.get(
                name='system').volume.upload(path)

    def register_rhel_subscription(self, ip):
        reg_command = ("/usr/sbin/subscription-manager register "
                       "--username={0} --password={1} --serverurl={2} "
                       "--org={3} --release={4}".format(
                        settings.RHEL_LICENSE_USERNAME,
                        settings.RHEL_LICENSE_PASSWORD,
                        settings.RHEL_SERVER_URL,
                        settings.RHEL_REGISTERED_ORG_NAME,
                        settings.RHEL_RELEASE))

        if settings.RHEL_ACTIVATION_KEY:
            reg_command = reg_command + "--activationkey={0}".format(
                settings.RHEL_ACTIVATION_KEY)

        with self.env.d_env.get_ssh_to_remote(ip) as remote:
            result = remote.execute(reg_command)
        LOGGER.debug(result)

    def enable_rhel_repos(self, ip):
        cmd = ("yum-config-manager --enable rhel-7-server-optional-rpms && "
               "yum-config-manager --enable rhel-7-server-extras-rpms &&"
               "yum-config-manager --enable rhel-7-server-rh-common-rpms")

        with self.env.d_env.get_ssh_to_remote(ip) as remote:
            result = remote.execute(cmd)
        LOGGER.debug(result)

    def set_hostname(self, ip):
        cmd = "sysctl kernel.hostname=rhel.domain.local"

        with self.env.d_env.get_ssh_to_remote(ip) as remote:
            result = remote.execute(cmd)
        LOGGER.debug(result)

    def apply_compute_puppet(self, ip):
        puppet_path = [
            "/etc/puppet/modules/osnailyfacter/modular/hiera/hiera.pp",
            "/etc/puppet/modules/osnailyfacter/modular/globals/globals.pp",
            "/etc/puppet/modules/osnailyfacter/modular/firewall/firewall.pp",
            "/etc/puppet/modules/osnailyfacter/modular/tools/tools.pp",
            "/etc/puppet/modules/osnailyfacter/modular/netconfig/netconfig.pp",
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
            "openstack-network/compute-nova.pp"]

        with self.env.d_env.get_ssh_to_remote(ip) as remote:
            for puppet in puppet_path:
                result = remote.execute("puppet apply -vd {0}".format(puppet))
                LOGGER.debug(result)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_rhel_compute_ha_tun"])
    @log_snapshot_after_test
    def deploy_rhel_based_compute(self):
        """Deploy RHEL-based compute in HA mode with Neutron VXLAN

        Scenario:
            1. Create a Fuel cluster.
            2. Add 3 node with "controller" role.
            3. Add 2 node with "compute" role.
            4. Deploy the Fuel cluster.
            5. Run OSTF.
            6. Backup astute.yaml and ssh keys from one of the compute.
            7. Boot compute with RHEL image.
            8. Prepare node for Puppet run.
            9. Execute modular tasks for compute.
            10. Run OSTF.

        Duration: 150m
        Snapshot: deploy_rhel_compute_ha_tun

        """
        LOGGER.debug('Check MD5 sum of RHEL 7 image')
        check_image = checkers.check_image(
            settings.RHEL_IMAGE,
            settings.RHEL_IMAGE_MD5,
            settings.RHEL_IMAGE_PATH)
        asserts.assert_true(check_image)

        self.env.revert_snapshot("ready_with_5_slaves")

        LOGGER.debug('Create Fuel cluster RHEL-based compute tests')
        data = {
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['tun'],
            'tenant': 'RhelHA',
            'user': 'RhelHA',
            'password': 'RhelHA'
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        cluster_vip = self.fuel_web.get_public_vip(cluster_id)
        os_conn = os_actions.OpenStackActions(
            cluster_vip, data['user'], data['password'], data['tenant'])
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=13)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        target_node_name = "slave-04"
        cmd = ("cd ~/ && mkdir rhel_backup && "
               "scp -r {0}:/root/.ssh rhel_backup/. && "
               "scp {0}:/etc/astute.yaml rhel_backup/ && "
               "scp -r {0}:/var/lib/astute/nova .").format(target_node_name)
        with self.env.d_env.get_ssh_to_remote(self.env.admin_node_ip()) as \
                remote:
            result = remote.execute(cmd)
        LOGGER.debug(result)
        LOGGER.debug("Backed up ssh-keys and astute.yaml")

        target_node = self.env.d_env.get_node(name=target_node_name)
        target_node.destroy()
        self.connect_rhel_image(target_node)
        target_node.start()
        self.wait_for_slave_provision(target_node_name)

        target_node_ip = target_node.get_ip_address_by_network_name('admin')

        cmd = ("cd ~/rhel_backup && "
               "scp -r .ssh {0}:{1}@{2}:/root/. && "
               "scp astute.yaml {0}:{1}@{2}:/etc/. && "
               "scp -r nova /var/lib/astute/").format(
            settings.RHEL_IMAGE_USER,
            settings.RHEL_IMAGE_PASSWORD,
            target_node_ip
        )

        self.set_hostname(target_node_ip)

        with self.env.d_env.get_ssh_to_remote(self.env.admin_node_ip()) as \
                remote:
            result = remote.execute(cmd)
        LOGGER.debug(result)

        cmd = ("curl https://perestroika-repo-tst.infra.mirantis.net/"
               "mos-repos/centos/mos8.0-centos7-fuel/os/x86_64/")

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            result = remote.execute(cmd)
            if result['exit_code'] != 0:
                LOGGER.warning(result)
                msg = "Perestroika repos unavailable from node. Exiting."
                LOGGER.error(msg)
                raise Exception("msg")
            else:
                cmd = ("echo 'http://perestroika-repo-tst.infra.mirantis.net/"
                       "mos-repos/centos/mos8.0-centos7-fuel/os/x86_64/' >>"
                       "/etc/yum.repos.d/mos8.0.repo && "
                       "yum install yum-utils -y")
                result = remote.execute(cmd)
                LOGGER.debug(result)

        # Remove this parameter after infrastructure and tests will be ready.
        if not settings.CENTOS_DUMMY_DEPLOY:
            self.register_rhel_subscription(target_node_ip)
            self.enable_rhel_repos(target_node_ip)

        puppet_install_cmd = ("sudo yum install puppet ruby -y")
        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            result = remote.execute(puppet_install_cmd)
            LOGGER.debug(result)

        with self.env.d_env.get_ssh_to_remote(target_node_ip) as remote:
            cmd = ("rm -f /etc/selinux/config; "
                   "echo 'SELINUX=disabled\n"
                   "SELINUXTYPE=targeted\n"
                   "SETLOCALDEFS=0' > /etc/selinux/config")
            result = remote.execute(cmd)
            LOGGER.debug(result)

        cmd = ("rsync -avz /etc/puppet/modules/* "
               "{0}@{1}:/etc/puppet/modules/".format(settings.RHEL_IMAGE_USER,
                                                     target_node_ip))
        with self.env.d_env.get_ssh_to_remote(
                self.env.get_admin_node_ip()) as remote:
            remote.execute(cmd)
            LOGGER.debug(cmd)

        self.apply_compute_puppet(target_node_ip)
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=13)

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        self.env.make_snapshot("ready_ha_with_rhel_compute", is_make=True)
