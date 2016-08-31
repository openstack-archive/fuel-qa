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

from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests import base_test_case

from gates_tests.helpers import exceptions


@test(groups=["prepare_mu_installing"])
class MUInstallBase(base_test_case.TestBasic):

    def _add_repo(self, cluster_id, repo):

        attributes = self.fuel_web.client.get_cluster_attributes(cluster_id)
        repos_attr = attributes['editable']['repo_setup']['repos']
        repos_attr['value'].append(repo)
        self.client.update_cluster_attributes(cluster_id, attributes)

    @test(depends_on_groups=["deploy_multirole_compute_cinder"],
          groups=["prepare_for_install_mu_non_ha_cluster"])
    @log_snapshot_after_test
    def prepare_for_install_mu_non_ha_cluster(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_multirole_compute_cinder
            2. enable updates repo
            3. update fuel-master
            4. install python-cudet package

        Duration: 20m
        Snapshot: build_default_bootstrap
        """
        self.show_step(1)
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'true')

        self.env.revert_snapshot("prepare_for_install_mu_non_ha_cluster")

        cluster_id = self.fuel_web.client.get_cluster_id()

        self.show_step(2)

        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}

        self._add_repo(cluster_id, mos_repo)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.env.admin_actions.wait_for_fuel_ready()

        self.env.make_snapshot(
            "prepare_for_install_mu_non_ha_cluster",
            is_make=True)

    @test(depends_on_groups=["ceph_rados_gw"],
          groups=["prepare_for_install_mu_ha_cluster"])
    @log_snapshot_after_test
    def prepare_for_install_mu_ha_cluster(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot ceph_rados_gw
            2. enable updates repo
            3. update fuel-master
            4. check fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_ha_cluster
        """
        self.show_step(1)
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'true')

        self.env.revert_snapshot("ceph_rados_gw")
        cluster_id = self.fuel_web.client.get_cluster_id()

        self.show_step(2)
        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}

        self._add_repo(cluster_id, mos_repo)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.env.admin_actions.wait_for_fuel_ready()

        self.env.make_snapshot(
            "prepare_for_install_mu_ha_cluster",
            is_make=True)

    @test(depends_on_groups=["ironic_deploy_ceilometer"],
          groups=["prepare_for_install_mu_services_1"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_1(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot ironic_deploy_ceilometer
            2. enable updates repo
            3. update fuel-master
            4. check fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_1
        """
        self.show_step(1)
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'true')

        self.env.revert_snapshot("ironic_deploy_ceilometer")
        cluster_id = self.fuel_web.client.get_cluster_id()

        self.show_step(2)
        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}
        self._add_repo(cluster_id, mos_repo)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.env.admin_actions.wait_for_fuel_ready()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_1",
            is_make=True)

    @test(depends_on_groups=["deploy_sahara_ha_tun"],
          groups=["prepare_for_install_mu_services_2"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_2(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_sahara_ha_tun
            2. enable updates repo
            3. update fuel-master
            4. check fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_2
        """
        self.show_step(1)
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'true')
        self.env.revert_snapshot("deploy_sahara_ha_tun")
        cluster_id = self.fuel_web.client.get_cluster_id()

        self.show_step(2)
        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}

        self._add_repo(cluster_id, repo=mos_repo)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.env.admin_actions.wait_for_fuel_ready()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_2",
            is_make=True)

    @test(depends_on_groups=["deploy_murano_ha_with_tun"],
          groups=["prepare_for_install_mu_services_3"])
    @log_snapshot_after_test
    def prepare_for_install_mu_services_3(self):
        """Update master node and install packages for MU installing

        Scenario:
            1. revert snapshot deploy_sahara_ha_tun
            2. enable updates repo
            3. update fuel-master
            4. check fuel services

        Duration: 20m
        Snapshot: prepare_for_install_mu_services_3
        """
        self.show_step(1)
        if not settings.PATCHING_DISABLE_UPDATES \
                and not settings.REPLACE_DEFAULT_REPOS \
                and not settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE:
            raise exceptions.FuelQAVariableNotSet(
                (settings.PATCHING_DISABLE_UPDATES,
                 settings.REPLACE_DEFAULT_REPOS,
                 settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE),
                'true')
        self.env.revert_snapshot("deploy_murano_ha_with_tun")
        cluster_id = self.fuel_web.client.get_cluster_id()

        self.show_step(2)
        mos_repo = {
            u'name': u'mos-updates',
            u'section': u'main restricted',
            u'uri': u'http://mirror.fuel-infra.org/mos-repos/ubuntu/9.0/',
            u'priority': 1050,
            u'suite':
                u'mos9.0-updates',
            u'type': u'deb'}

        self._add_repo(cluster_id, mos_repo)

        self.show_step(3)
        self.env.admin_install_updates()

        self.show_step(4)
        self.env.admin_actions.wait_for_fuel_ready()

        self.env.make_snapshot(
            "prepare_for_install_mu_services_3",
            is_make=True)
