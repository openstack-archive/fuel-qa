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

from proboscis.asserts import assert_true, assert_equal
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ha_neutron_tun", "ceph"])
class RedeployNoop(TestBasic):
    """RedeployNoop."""  # TODO(aderyugin): documentation

    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["redeploy_noop", "ceph", "neutron", "deployment"])
    @log_snapshot_after_test
    def redeploy_noop(self):
        """Deploy 9.0 ceph HA with RadosGW for objects and then redeploy in noop mode

        Scenario:
            1. Create 9.0 cluster with Neutron
            2. Add 3 nodes with controller role
            3. Add 3 nodes with compute and ceph-osd role
            4. Deploy the cluster
            5. Check ceph status
            6. Run OSTF tests
            7. Check the radosgw daemon is started
            8. Re-run deployment in noop mode

        Duration 150m
        Snapshot upgrade_9x

        """
        def radosgw_started(remote):
            return remote.check_call('pkill -0 radosgw')['exit_code'] == 0

        self.env.revert_snapshot("ready")
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:6])

        logger.info('<<< 1. Create 9.0 cluster with Neutron >>>')

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'volumes_lvm': False,
                'volumes_ceph': True,
                'images_ceph': True,
                'objects_ceph': True,
                'tenant': 'rados',
                'user': 'rados',
                'password': 'rados'
            }
        )

        logger.info('<<< 2. Add 3 nodes with controller role >>>')
        logger.info('<<< 3. Add 3 nodes with compute and ceph-osd role >>>')

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['compute', 'ceph-osd'],
                'slave-06': ['compute', 'ceph-osd']
            }
        )

        self.fuel_web.verify_network(cluster_id)

        logger.info('<<< 4. Deploy the cluster >>>')

        # Deploy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # HAProxy backend checking
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])

        for node in controller_nodes:
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(node['ip'])
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))

        logger.info('<<< 5. Check ceph status >>>')

        self.fuel_web.check_ceph_status(cluster_id)

        logger.info('<<< 6. Run OSTF tests >>>')

        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])

        logger.info('<<< 7. Check the radosgw daemon is started >>>')

        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            assert_true(radosgw_started(remote), 'radosgw daemon started')

        logger.info('<<< 8. Re-run deployment in noop mode >>>')

        remote_cmds = [
            "for taskfile in $(find /etc/puppet/modules/ -name tasks.yaml); "
            "do sed -i \"s/puppet_manifest: \(.*\)$/puppet_manifest: \1 --noop"
            " --logdest \/var\/log\/puppet_noop.json/g\" $taskfile; "
            "done",

            "fuel rel --sync-deployment-tasks --dir /etc/puppet"
        ]

        with self.fuel_web.get_ssh_for_node('admin') as remote:
            for command in remote_cmds:
                assert_true(remote.check_call(command) == 0,
                            'master node: "%s"' % command)

        self.fuel_web.redeploy_cluster_changes_wait_progress(cluster_id)

        self.env.make_snapshot("upgrade_9x")
