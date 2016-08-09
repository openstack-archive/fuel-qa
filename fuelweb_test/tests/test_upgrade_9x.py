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
from fuelweb_test.tests.base_test_case import TestBasic

from system_test import get_groups
from run_system_test import basedir, tests_directory, discover_import_tests


@test(groups=["ha_neutron_tun", "ceph"])
class Upgrade9X(TestBasic):
    """Upgrade9X."""  # TODO(aderyugin): documentation

    @test(groups=["upgrade_9x", "ceph", "neutron", "deployment"])
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

        def _show_step_for_sub_test(test_method):
            def wrapper(step, details='', initialize=False):
                docstring = test_method.__doc__
                docstring = '\n'.join(
                    [s.strip() for s in docstring.split('\n')]
                )

                steps = {s.split('. ')[0]: s for s in
                         docstring.split('\n') if s and s[0].isdigit()}
                if details:
                    details_msg = ': {0} '.format(details)
                else:
                    details_msg = ''

                if str(step) in steps:
                    logger.info("\n" + " " * 55 + "<<< {0} {1} {2}>>>".format(
                        test_method.__name__, steps[str(step)], details_msg
                    ))
                else:
                    logger.info("\n" + " " * 55 + "<<< {0} {1}. {2}>>>".format(
                        test_method.__name__, str(step), details_msg
                    ))
            return wrapper

        def _resolve_dependencies(test_group_name):
            test_group = get_groups().get(test_group_name, None)

            dep_list = []
            if test_group is not None:
                for test_case in test_group:
                    case_dep_list = []
                    for dependency in test_case.info.depends_on:
                        sub_dep_list = _resolve_dependencies(
                            dependency.func_name)
                        case_dep_list += sub_dep_list if len(
                            sub_dep_list) > 0 else [dependency]
                    case_dep_list += [test_case.method]

                    if len(test_group) > 1:
                        dep_list += [case_dep_list]
                    else:
                        dep_list += case_dep_list

            return dep_list

        def _run_test_case(test_case):
            self.show_step(1)

            test_case_method = test_case[-1]

            logger.info("Running {}.{}".format(
                test_case_method.im_class.__name__,
                test_case_method.__name__
            ))

            for test_method in test_case:
                test_instance = test_method.im_class() if hasattr(
                    test_method, 'im_class'
                ) else None

                if test_instance:
                    test_instance.show_step = _show_step_for_sub_test(
                        test_method
                    )

                test_method(test_instance if test_instance else self)

            cluster_id = self.fuel_web.client.get_cluster_id(
                test_case_method.im_class.__name__
            )

            self.show_step(2)

            master_repo_url = "http://mirror.seed-cz1.fuel-infra.org/" \
                              "mos-repos/centos/mos9.0-centos7/snapshots/" \
                              "proposed-2016-08-16-104320"
            upgrade_cmds = [
                "yum-config-manager --add-repo %s/x86_64/" % master_repo_url,

                "rpm --import %s/RPM-GPG-KEY-mos9.0" % master_repo_url,

                "sed -i 's/priority=15/#priority=15/g' "
                "/etc/yum.repos.d/9.0_auxiliary.repo",

                "wget -O - https://review.openstack.org/cat/346119%2C2%2Cutils"
                "/updates/update-master-node.sh%5E0 | zcat | bash 2>&1 | "
                "tee /var/log/upgrade.log",

                "yum install -y fuel-library",

                "fuel rel --sync-deployment-tasks --dir /etc/puppet"
            ]

            for command in upgrade_cmds:
                assert_true(self.ssh_manager.execute_on_remote(
                    ip=self.ssh_manager.admin_ip,
                    cmd=command
                )['exit_code'] == 0, 'master node upgrade: "%s"' % command)

            self.show_step(3)

            mirror_url = "http://mirror.seed-cz1.fuel-infra.org/mos-repos/" \
                         "ubuntu/snapshots/9.0-2016-08-16-104320/"

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

            self.env.make_snapshot("upgrade_9x_%s" % test_case_method.__name__)

        test_group_name = getenv("UPGRADE_TEST_GROUP", "bvt_2")
        discover_import_tests(basedir, tests_directory)

        test_group = _resolve_dependencies(test_group_name)

        if isinstance(test_group[0], list):
            for test_case in test_group:
                _run_test_case(test_case)
        else:
            _run_test_case(test_group)
