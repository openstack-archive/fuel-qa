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


from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test.helpers import utils


@test(groups=["iac_git"])
class IacGit(TestBasic):
    """IacGit"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["iac_git_download_settings"])
    @log_snapshot_after_test
    def iac_git_download_settings(self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
           1. Create cluster
           2. Add 3 controller node
           3. Add 2 compute node
           4. Deploy cluster
           5. Verify network
           6. Run OSTF
           7. Install extension
           8. Create git repository with custom yaml file
           9. Add git repository
           10. Re-deploy cluster
           11. Check if settings are applied
           Snapshot: iac_git_download_settings
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'iac_git_download_settings',
            'user': 'iac_git_download_settings',
            'password': 'iac_git_download_settings'
        }
        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        admin_ip = self.env.get_admin_node_ip()
        logger.info('install rpm packages:')
        utils.install_pkg_2(admin_ip, 'git')
        utils.install_pkg_2(admin_ip, 'fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip, command='rpm -qa fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            ip=admin_ip, command='service nailgun restart')
        self.ssh_manager.check_call(
            ip=admin_ip, command='nailgun_syncdb')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 env extension enable 1 -E fuel_external_git')

        self.show_step(8)
        self.ssh_manager.check_call(
            ip=admin_ip, command='mkdir /root/project.git')
        self.ssh_manager.check_call(
            ip=admin_ip, command='git config --global user.name "IAC GIT"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='git config --global user.email iac@mirantis.com')
        source = 'fuelweb_test/tests/'\
                 'test_iac_git_extension'\
                 '/cluster_iac_git_download_settings.yaml'
        target = '/root/project.git/cluster.yaml'
        self.ssh_manager.upload_to_remote(ip=admin_ip,
                                          source=source,
                                          target=target)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='cd /root/project.git && git init && git add . && \
                    git commit -a -m "init repository"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='ssh-keyscan -H localhost >> /root/.ssh/known_hosts')

        self.show_step(9)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo create --env=1 --name=test \
                    --url="root@localhost:/root/project.git" \
                    --ref=master --key="/root/.ssh/id_rsa"')

        logger.info('Check if git repository added:')
        expected = 'project.git'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo list | grep {0}'.format(expected),
            expected=[0],
            error_info='Repository check failure')
        logger.info('Check if configure exist before re-deploy:')
        expected = 'cpu_allocation_ratio=8.0'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "cat /etc/nova/nova.conf \
                    | grep {0}"'.format(expected),
            expected=[0],
            error_info='Configuration check failure')

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(11)
        expected = 'cpu_allocation_ratio=1.0'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "cat /etc/nova/nova.conf \
                    | grep {0}"'.format(expected),
            expected=[0],
            error_info='Configuration check failure')

        self.env.make_snapshot('iac_git_download_settings')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["iac_git_install_remove_package"])
    @log_snapshot_after_test
    def iac_git_install_remove_package(self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
           1. Create cluster
           2. Add 3 controller node
           3. Add 2 compute node
           4. Deploy cluster
           5. Verify network
           6. Run OSTF
           7. Install extension
           8. Create git repository with custom yaml file
           9. Add git repository
           10. Re-deploy cluster
           11. Check if settings are applied
           Snapshot: iac_git_install_remove_package
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'iac_git_install_remove_package',
            'user': 'iac_git_install_remove_package',
            'password': 'iac_git_install_remove_package'
        }
        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        admin_ip = self.env.get_admin_node_ip()
        logger.info('install rpm packages:')
        utils.install_pkg_2(admin_ip, 'git')
        utils.install_pkg_2(admin_ip, 'fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip, command='rpm -qa fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            ip=admin_ip, command='service nailgun restart')
        self.ssh_manager.check_call(
            ip=admin_ip, command='nailgun_syncdb')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 env extension enable 1 -E fuel_external_git')

        self.show_step(8)
        self.ssh_manager.check_call(
            ip=admin_ip, command='mkdir /root/project.git')
        self.ssh_manager.check_call(
            ip=admin_ip, command='git config --global user.name "IAC GIT"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='git config --global user.email iac@mirantis.com')
        source = 'fuelweb_test/tests/'\
                 'test_iac_git_extension/'\
                 'cluster_iac_git_install_remove_package.yaml'
        target = '/root/project.git/cluster.yaml'
        self.ssh_manager.upload_to_remote(ip=admin_ip,
                                          source=source,
                                          target=target)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='cd /root/project.git && git init && git add . && \
                    git commit -a -m "init repository"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='ssh-keyscan -H localhost >> /root/.ssh/known_hosts')

        self.show_step(9)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo create --env=1 --name=test \
                    --url="root@localhost:/root/project.git" \
                    --ref=master --key="/root/.ssh/id_rsa"')

        logger.info('Check if git repository added:')
        expected = 'project.git'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo list | grep {0}'.format(expected),
            expected=[0],
            error_info='Repository check failure')
        logger.info('Check if "mc" package absent before re-deploy:')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "dpkg -s mc"',
            expected=[1],
            error_info='Package check failure')
        logger.info('Check if "virt-what" package installed before re-deploy:')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "dpkg -s virt-what"',
            expected=[0],
            error_info='Package check failure')

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(11)
        logger.info('Check if "mc" package installed after re-deploy:')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "dpkg -s mc"',
            expected=[0],
            error_info='Package check failure')
        logger.info('Check if "virt-what" package removed after re-deploy:')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "dpkg -s virt-what"',
            expected=[1],
            error_info='Package check failure')

        self.env.make_snapshot('iac_git_install_remove_package')

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["iac_git_set_non_openstack_settings"])
    @log_snapshot_after_test
    def iac_git_set_non_openstack_settings(self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
           1. Create cluster
           2. Add 3 controller node
           3. Add 2 compute node
           4. Deploy cluster
           5. Verify network
           6. Run OSTF
           7. Install extension
           8. Create git repository with custom yaml file
           9. Add git repository
           10. Re-deploy cluster
           11. Check if settings are applied
           Snapshot: iac_git_set_non_openstack_settings
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'iac_git_set_non_openstack_settings',
            'user': 'iac_git_set_non_openstack_settings',
            'password': 'iac_git_set_non_openstack_settings'
        }
        self.show_step(1)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(7)
        admin_ip = self.env.get_admin_node_ip()
        logger.info('install rpm packages:')
        utils.install_pkg_2(admin_ip, 'git')
        utils.install_pkg_2(admin_ip, 'fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip, command='rpm -qa fuel-nailgun-extension-iac')
        self.ssh_manager.check_call(
            ip=admin_ip, command='service nailgun restart')
        self.ssh_manager.check_call(
            ip=admin_ip, command='nailgun_syncdb')
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 env extension enable 1 -E fuel_external_git')

        self.show_step(8)
        self.ssh_manager.check_call(
            ip=admin_ip, command='mkdir /root/project.git')
        self.ssh_manager.check_call(
            ip=admin_ip, command='git config --global user.name "IAC GIT"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='git config --global user.email iac@mirantis.com')
        source = 'fuelweb_test/tests/'\
                 'test_iac_git_extension/'\
                 'cluster_iac_git_set_non_openstack_settings.yaml'
        target = '/root/project.git/cluster.yaml'
        self.ssh_manager.upload_to_remote(ip=admin_ip,
                                          source=source,
                                          target=target)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='cd /root/project.git && git init && git add . && \
                    git commit -a -m "init repository"')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='cat /root/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys')
        self.ssh_manager.check_call(
            ip=admin_ip,
            command='ssh-keyscan -H localhost >> /root/.ssh/known_hosts')

        self.show_step(9)
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo create --env=1 --name=test \
                    --url="root@localhost:/root/project.git" \
                    --ref=master --key="/root/.ssh/id_rsa"')

        logger.info('Check if git repository is added:')
        expected = 'project.git'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='fuel2 gitrepo list | grep {0}'.format(expected),
            expected=[0],
            error_info='Repository check failure')

        self.show_step(10)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(11)
        expected = 'myconfig=1'
        self.ssh_manager.check_call(
            verbose=True,
            ip=admin_ip,
            command='ssh node-1 "cat /root/testfile.cfg \
                    | grep {0}"'.format(expected),
            expected=[0],
            error_info='Configuration check failure')

        self.env.make_snapshot('iac_git_set_non_openstack_settings')
