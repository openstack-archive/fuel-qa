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
from __future__ import unicode_literals
from os import getenv

from proboscis.asserts import assert_true, assert_equal, assert_is_not_none
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

from system_test import get_groups
from run_system_test import basedir, tests_directory, discover_import_tests


@test(groups=["ha_neutron_tun", "ceph"])
class Upgrade9X(TestBasic):
    """Upgrade9X."""  # TODO(aderyugin): documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["upgrade_9x", "ceph", "neutron", "deployment"])
    @log_snapshot_after_test
    def upgrade_9x(self):
        """Run given scenario and then upgrade to 9.x

        For each scenario in a given group

        Scenario:
            1. Run given scenario
            2. Upgrade master node
            3. Set repositories
            4. Upgrade environment
            5. Run OSTF tests

        Duration 150m
        Snapshot upgrade_9x_<test_name>

        """

        test_group_name = getenv("UPGRADE_TEST_GROUP", "bvt_2")
        discover_import_tests(basedir, tests_directory)

        test_group = get_groups().get(test_group_name, None)

        assert_is_not_none(test_group)

        for test_case in test_group:
            self.show_step(1)

            test_method = test_case.method

            for dependency in test_case.info.depends_on:
                dependency()

            logger.info("Running {}.{}".format(
                test_method.im_class.__name__,
                test_method.__name__
            ))

            test_method(test_method.im_class())

            cluster_id = self.fuel_web.client.get_cluster_id(
                test_method.im_class.__name__
            )

            self.show_step(2)

            master_repo_url = "http://mirror.seed-cz1.fuel-infra.org/" \
                              "mos-repos/centos/mos9.0-centos7/snapshots/" \
                              "proposed-2016-08-08-112322"

            upgrade_cmds = [
                "yum-config-manager --add-repo %s/x86_64/" % master_repo_url,

                "rpm --import %s/RPM-GPG-KEY-mos9.0" % master_repo_url,

                "sed -i 's/priority=15/#priority=15/g' "
                "/etc/yum.repos.d/9.0_auxiliary.repo",

                "wget -O - https://review.openstack.org/cat/346119%2C2%2Cutils"
                "/updates/update-master-node.sh%5E0 | zcat | bash 2>&1 | "
                "tee /var/log/upgrade.log",

                "for manifest in $(find /etc/puppet/modules/ -name tasks.yaml "
                "| xargs grep puppet_manifest | awk '{ print $3 }'); "
                "do echo \"Package<| |> { ensure => 'latest' }\" >> $manifest;"
                " done",

                "fuel rel --sync-deployment-tasks --dir /etc/puppet"
            ]

            for command in upgrade_cmds:
                assert_true(self.ssh_manager.execute_on_remote(
                    ip=self.ssh_manager.admin_ip,
                    cmd=command
                )['exit_code'] == 0, 'master node upgrade: "%s"' % command)

            self.show_step(3)

            mirror_url = "http://mirror.seed-cz1.fuel-infra.org/mos-repos/" \
                         "ubuntu/snapshots/9.0-2016-08-08-094723/"

            mirrors = ['mos9.0', 'mos9.0-holdback', 'mos9.0-hotfix',
                       'mos9.0-proposed', 'mos9.0-security', 'mos9.0-updates']

            attrs = self.fuel_web.client.get_cluster_attributes(cluster_id)

            for mirror in mirrors:
                attrs['editable']['repo_setup']['repos']['value'].append({
                    'name': mirror,
                    'priority': 1050,
                    'section': 'main restricted',
                    'suite': mirror,
                    'type': 'deb',
                    'uri': mirror_url,
                })

            self.fuel_web.client.update_cluster_attributes(cluster_id, attrs)

            self.show_step(4)

            self.fuel_web.redeploy_cluster_changes_wait_progress(
                cluster_id, None
            )

            self.fuel_web.verify_network(cluster_id)

            controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                cluster_id, ['controller'])

            for node in controllers:
                logger.info("Check all HAProxy backends on {}".format(
                    node['meta']['system']['fqdn']))
                haproxy_status = checkers.check_haproxy_backend(node['ip'])
                assert_equal(haproxy_status['exit_code'], 1,
                             "HAProxy backends are DOWN. {0}".format(
                                 haproxy_status))

            self.show_step(5)

            self.fuel_web.run_ostf(cluster_id=cluster_id,
                                   test_sets=['ha', 'smoke', 'sanity'])

            self.env.make_snapshot("upgrade_9x_%s" % test_method.__name__)
