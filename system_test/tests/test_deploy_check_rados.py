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
        7. Check the radosqw daemon is started
    """

    base_group = ['actions_tests',
                  'actions_tests.deploy_and_check_radosgw',
                  'actions_tests.bvt_2']
    actions_order = [
        '_action_setup_master',
        '_action_config_release',
        '_action_make_slaves',
        '_action_revert_slaves',
        '_action_create_env',
        '_action_add_nodes',
        '_action_network_check',
        '_action_deploy_cluster',
        '_action_network_check',
        '_action_check_haproxy',
        '_action_check_ceph_status',
        '_action_health_check',
        '_action_check_rados_daemon'
    ]

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_check_ceph_status(self):
        """Check Ceph status in cluster"""
        self.fuel_web.check_ceph_status(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    def _action_check_rados_daemon(self):
        """Check the radosqw daemon is started"""
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            radosgw_started = lambda: len(remote.check_call(
                'ps aux | grep "/usr/bin/radosgw -n '
                'client.radosgw.gateway"')['stdout']) == 3
            assert_true(radosgw_started(), 'radosgw daemon started')


@factory
def cases():
    return case_factory(DeployCheckRadosGW)
