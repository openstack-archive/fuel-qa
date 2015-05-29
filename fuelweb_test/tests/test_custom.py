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

import re
import os

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test
from proboscis import SkipTest

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.settings import DEPLOYMENT_MODE_HA
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger


@test(groups=["test_custom"])
class TestCustom(TestBasic):
    #Environment
    #OPENSTACK_RELEASE = os.environ.get("OPENSTACK_RELEASE", "centos")
    HYPERVISOR_TYPE = os.environ.get("HYPERVISOR_TYPE", "qemu")
    NET_PROVIDER = os.environ.get("NETWORK_PROVIDER", "neutron")
    NET_SEGMENT_TYPE = os.environ.get("NET_SEGMENT_TYPE","vlan")
    STORAGE_PROVIDER = os.environ.get("STORAGE_PROVIDER", "cinder")

    #ADDITIONAL_SERVICES =  os.environ.get("ADDITIONAL_SERVICES","")
    NUMBER_CONTROLLERS = os.environ.get("NUMBER_CONTROLLERS","1")
    NUMBER_COMPUTES = os.environ.get("NUMBER_COMPUTES", "1")
    NUMBER_STORAGE = os.environ.get("NUMBER_STORAGE", "1")
    NUMBER_CONTROLLERS = int(NUMBER_CONTROLLERS)
    NUMBER_COMPUTES = int(NUMBER_COMPUTES)
    NUMBER_STORAGE = int(NUMBER_STORAGE)
    
    LAUNCH_OSTF = os.environ.get("LAUNCH_OSTF","false") == 'true'
    TOTAL_SLAVES = NUMBER_CONTROLLERS + NUMBER_COMPUTES + NUMBER_STORAGE
    
    roles = {}
    data = {}

    #Configure cluster data
    data['libvirt_type'] = HYPERVISOR_TYPE
    data['net_provider'] = NET_PROVIDER

    if NET_PROVIDER == 'neutron':
        data['net_segment_type'] = NET_SEGMENT_TYPE
    else:
        NET_SEGMENT_TYPE = ''

    if STORAGE_PROVIDER == 'ceph':
        data['volumes_ceph'] = True
        data['images_ceph'] = True
        data['volumes_lvm'] = False
	data['ephemeral_ceph'] = True
	data['objects_ceph'] = True
    elif STORAGE_PROVIDER == 'cinder':
        data['volumes_ceph'] = False
        data['images_ceph'] = False
        data['volumes_lvm'] = True

    for i in xrange(1,NUMBER_CONTROLLERS+1):
        slave = 'slave-0%s' % i
        roles[slave] = ['controller']
    for i in xrange(1+NUMBER_CONTROLLERS,NUMBER_CONTROLLERS+NUMBER_COMPUTES+1):
        slave = 'slave-0%s' % i
        roles[slave] = ['compute']
    for i in xrange(1+NUMBER_CONTROLLERS+NUMBER_COMPUTES,NUMBER_CONTROLLERS+NUMBER_COMPUTES+NUMBER_STORAGE+1):
        slave = 'slave-0%s' % i
        if STORAGE_PROVIDER == 'ceph':
            roles[slave] = ['ceph-osd']
        elif STORAGE_PROVIDER == 'cinder':
            roles[slave] = ['cinder']

    @test(depends_on=[SetupEnvironment.prepare_release],
        groups=["deploy_custom"])
    @log_snapshot_after_test
    def deploy_custom(self):
        """Deploy cluster in HA mode with VLAN Manager:

           Scenario:
               1. Create cluster
               2. Add nodes with controller roles
               3. Add nodes with compute roles
               4. Add nodes with storage roles
           Snapshot deploy_custom
        """
        #% (OPENSTACK_RELEASE, HYPERVISOR_TYPE, NET_PROVIDER, NET_SEGMENT_TYPE, STORAGE_PROVIDER, NUMBER_CONTROLLERS, NUMBER_COMPUTES, NUMBER_STORAGE)

#        self.env.revert_snapshot("ready_with_%s_slaves" % self.BOOTSTRAP_SLAVES)
        self.env.revert_snapshot("ready")
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:self.TOTAL_SLAVES])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE_HA,
            settings=self.data
        )
        self.fuel_web.update_nodes(
                cluster_id,
                self.roles
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.check_ceph_status(cluster_id)

        # Run ostf
        if self.LAUNCH_OSTF:
	    self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_custom_%s" % self.TOTAL_SLAVES)
