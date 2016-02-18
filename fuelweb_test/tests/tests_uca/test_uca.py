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
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings as CONF
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["uca_neutron_ha"])
class UCATest(TestBasic):
    """UCATest."""  # TODO(mattymo) documentation

    @classmethod
    def check_service(cls, remote, service):
        ps_output = ''.join(
            remote.execute('ps ax | grep {0} | '
                           'grep -v grep'.format(service))['stdout'])
        return service in ps_output

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["uca_neutron_ha"])
    @log_snapshot_after_test
    def uca_neutron_ha(self):
        """Deploy cluster in ha mode with UCA repo

        Scenario:
            1. Create cluster
            2. Enable UCA configuration
            3. Add 3 nodes with controller role
            4. Add 2 nodes with compute+cinder role
            5. Deploy the cluster
            6. Run network verification
            7. Check plugin installation
            8. Run OSTF

        Duration 60m
        Snapshot uca_neutron_ha
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE,
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)

        # check attributes have uca options

        for option in ["repo_type", "uca_repo_url", "uca_openstack_release",
                       "pin_haproxy", "pin_rabbitmq", "pin_ceph"]:
            asserts.assert_true(option in attr["editable"]["repo_setup"],
                                "{0} is not in cluster attributes: {1}".
                                format(option,
                                       str(attr["editable"]["repo_setup"])))

        # enable UCA repository

        uca_options = attr["editable"]["repo_setup"]
        uca_options["repo_type"]["value"] = CONF.UCA_REPO_TYPE
        uca_options["uca_repo_url"]["value"] = CONF.UCA_REPO_URL
        uca_options["uca_openstack_release"]["value"] = CONF.UCA_RELEASE
        uca_options["pin_haproxy"]["value"] = CONF.UCA_PIN_HAPROXY
        uca_options["pin_rabbitmq"]["value"] = CONF.UCA_PIN_RABBITMQ
        uca_options["pin_ceph"]["value"] = CONF.UCA_PIN_RABBITMQ

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['compute', 'cinder'],
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("uca_neutron_ha")
