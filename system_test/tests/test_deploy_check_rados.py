#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from proboscis.asserts import assert_true

from system_test import testcase
from system_test import action
from system_test import deferred_decorator

from system_test.tests import ActionTest
from system_test.actions import BaseActions

from system_test.helpers.decorators import make_snapshot_if_step_fail


@testcase(groups=['system_test',
                  'system_test.deploy_and_check_radosgw'])
class DeployCheckRadosGW(ActionTest, BaseActions):
    """Deploy cluster and check RadosGW

    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Check HAProxy backends
        7. Check ceph status
        8. Run OSTF
        9. Check the radosgw daemon is started

    """

    actions_order = [
        'setup_master',
        'config_release',
        'make_slaves',
        'revert_slaves',
        'create_env',
        'add_nodes',
        'network_check',
        'deploy_cluster',
        'network_check',
        'check_haproxy',
        'check_ceph_status',
        'health_check',
        'check_rados_daemon'
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_ceph_status(self):
        """Check Ceph status in cluster"""
        self.fuel_web.check_ceph_status(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_rados_daemon(self):
        """Check the radosgw daemon is started"""
        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert_true(radosgw_started(remote), 'radosgw daemon started')
