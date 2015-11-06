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

from proboscis import factory
from proboscis.asserts import assert_true

from system_test.tests import actions_base
from system_test.helpers.utils import case_factory
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import action


class DeployCheckRadosGW(actions_base.ActionsBase):
    """Deploy cluster and check RadosGW


    Scenario:
        1. Create Environment
        2. Add nodes to Environment
        3. Run network checker
        4. Deploy Environment
        5. Run network checker
        6. Check HAProxy backends
        5. Check ceph status
        6. Run OSTF
        7. Check the radosgw daemon is started
    """

    base_group = ['system_test',
                  'system_test.deploy_and_check_radosgw',
                  'system_test.bvt_2']
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
            return len(remote.check_call(
                'ps aux | grep "/usr/bin/radosgw -n '
                'client.radosgw.gateway"')['stdout']) == 3
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert_true(radosgw_started(remote), 'radosgw daemon started')


@factory
def cases():
    return case_factory(DeployCheckRadosGW)
