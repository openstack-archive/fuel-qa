import time
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.helpers import os_actions
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["ubuntu_bootstrap"])
class UbuntuBootstrap(TestBasic):
    """UbuntuBootstrap."""  # TODO documentation
    @test(depends_on=[SetupEnvironment.prepare_release],
          groups=["ubuntu_bootstrap"])
    @log_snapshot_after_test
    def change_bootstrap_to_ubuntu(self):
        """Provision new cluster with Ubuntu bootstrap instead Centos

        Scenario:
            1. Revert snapshot "ready"
            2. Run script on master node to change bootstrap to Ubuntu
            3. Bootstrap slaves
            4. Create cluster with default values
            6. Create snapshot of environment

        Duration 30m

        """
        self.env.revert_snapshot("ready")
        self.fuel_web.client.get_root()

        # Run script on master node to change bootstrap to Ubuntu
        with self.env.d_env.get_admin_remote() as remote:
            cmd = 'fuel-bootstrap-image-set ubuntu'
            remote.execute(cmd)
        time.sleep(60)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )
        logger.info('cluster is %s' % str(cluster_id))
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))
        self.fuel_web.assert_cluster_ready(os_conn, smiles_count=4,
                                           networks_count=2, timeout=300)
        self.fuel_web.run_single_ostf_test(
            cluster_id=cluster_id, test_sets=['sanity'],
            test_name=('fuel_health.tests.sanity.test_sanity_identity'
                       '.SanityIdentityTest.test_list_users'))

        self.env.make_snapshot("ubuntu_bootstrap")
