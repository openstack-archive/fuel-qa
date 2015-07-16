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
import os

# from proboscis.asserts import assert_equal
# from proboscis.asserts import assert_true
from proboscis import test

# from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
# from fuelweb_test.settings import GLUSTER_CLUSTER_ENDPOINT
# from fuelweb_test.settings import GLUSTER_PLUGIN_PATH
from fuelweb_test.settings import NEUTRON_ENABLE
from fuelweb_test.settings import CALAMARI_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["fuel_plugins"])
class CalamariPlugin(TestBasic):
    """Tests for Calamari Plugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_ha_simple_calamari_plugin'])
    def deploy_ha_one_calamari_plugin(self):
        """Deploy cluster with one controller and Calamari plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 1 node with controller role
            5. Add 3 nodes with compute and ceph-osd roles
            6. Add 1 node with base-os and call it 'Calamari'
            7. Deploy the cluster
            8. Run network verification
            9. Check plugin health
            10. Run OSTF

        Duration 35m
        Snapshot deploy_ha_one_calamari_plugin
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CALAMARI_PLUGIN_PATH, '/var')

        # install plugin
        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CALAMARI_PLUGIN_PATH))        

        settings = {}
        if NEUTRON_ENABLE:
            settings = {
                "net_provider": 'neutron',
                "net_segment_type": "vlan"
            }
        settings.update(
            {
                'volumes_ceph': True,
                'images_ceph': True,
                'volumes_lvm': False,
                'tenant': 'cephHAoneCalamari',
                'user': 'cephHAoneCalamari',
                'password': 'cephHAoneCalamari'
            }
        )
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings=settings
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute', 'ceph-osd'],
                'slave-03': ['compute', 'ceph-osd'],
                'slave-04': ['compute', 'ceph-osd'],
                'slave-05': ['base-os']
            },
            custom_names={
                'slave-05': 'Calamari'
            }
        )

        # Config plugin
        plugin_name = 'fuel_plugin_calamari'
        options = {'metadata/enabled': True,
                   'fuel-plugin-calamari_username/value': 'cephHAoneCalamari',
                   'fuel-plugin-calamari_password': 'cephHAoneCalamari'}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        # Depoy cluster
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        # TODO:
        # Add additional checks after specifying acceptance criteria
