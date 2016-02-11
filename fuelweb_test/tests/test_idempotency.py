#    Copyright 2013 Mirantis, Inc.
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

import time
import traceback

from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.astute_log_parser import AstutePuppetTaskParser
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment

#from fuelweb_test.tests.test_neutron_tun_base import NeutronTunHaBase


from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["deploy_idempotency"])
#class TestIdempotency(NeutronTunHaBase):
class TestIdempotency(TestBasic):
    """TestIdempotency."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["deploy_idempotency"])
    @log_snapshot_after_test
    def deploy_neutron_tun_ha(self):
        """Deploy cluster in HA mode with Neutron VXLAN

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_tun_ha
        """
        cmds = [
            'echo "puppet_succeed_retries: 1" >> /etc/astute/astuted.conf',
            'systemctl restart astute'
        ]
        for cmd in cmds:
            self.ssh_manager.execute_on_remote(
                ip=self.ssh_manager.admin_ip,
                cmd=cmd
            )
        time.sleep(30)
        """ TODO: switch back to neutrontunhabase when i figure out if the
        rest of this stuff works
        super(self.__class__, self).deploy_neutron_tun_ha_base(
            snapshot_name="deploy_neutron_tun_ha")
        """
        self.env.revert_snapshot("ready")
        self.fuel_web.client.get_root()
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        logger.info('cluster is %s' % str(cluster_id))
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=4)
        self.fuel_web.run_single_ostf_test(
            cluster_id=cluster_id, test_sets=['sanity'],
            test_name=('fuel_health.tests.sanity.test_sanity_identity'
                       '.SanityIdentityTest.test_list_users'))
        try:
            admin_report = self.env.d_env.get_admin_remote()
            if not admin_report.download('/var/log/astute/astute.log',
                                         settings.LOGS_DIR):
                logger.error(("Unable to download astute.log"))
        except Exception:
            logger.error(traceback.format_exc())

        parser = AstutePuppetTaskParser()
        parser.parse_log("{path}/astute.log".format(path=settings.LOGS_DIR))
        parser.print_tasks()
