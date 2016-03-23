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
import re
import json

from proboscis import test
from proboscis import asserts

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers import utils


@test(groups=["cgroup_ha"])
class TestCgroupHa(TestBasic):
    """Tests for verification deployment with enabled cgroup."""

    def generate_attributes(self, cgroups):
        attributes = {}

        for cgroup in cgroups:

            if "limit" not in cgroup:
                limit = {}
            else:
                limit = {cgroup["limit"]: cgroup["value"]}

            attributes = utils.dict_merge(attributes, {
                cgroup["process"]: {
                    "label": cgroup["process"],
                    "type": "text",
                    "value": {
                        cgroup["controller"]: limit
                    }
                }
            })

        for cgroup in attributes.values():
            cgroup["value"] = json.dumps(cgroup["value"])

        return {"editable": {"cgroups": attributes}}

    def generate_lscgroups(self, cgroups):
        return ["{}:/{}".format(cgroup["controller"], cgroup["process"])
                for cgroup in cgroups]

    def check_cgroups_on_node(self, nailgun_node, cgroups):
        cgroups_config = self.get_cgroups_config(nailgun_node)

        for cgroup in cgroups:
            self.check_cgconfig_setup(config=cgroups_config, **cgroup)

        for lscgroup in self.generate_lscgroups(cgroups):
            check_group_cmd = 'sudo lscgroup | fgrep  -q {}'
            logger.info('Check {} group existence on controller node {}'
                        .format(lscgroup, nailgun_node['fqdn']))
            self.ssh_manager.check_call(nailgun_node['ip'],
                                        check_group_cmd.format(lscgroup))

        for cgroup in cgroups:
            check_rule_cmd = ("fgrep {} /etc/cgrules.conf | fgrep -q {}"
                              .format(cgroup["process"], cgroup["controller"]))

            logger.info("Check cgrule {} {} on controller node {}"
                        .format(cgroup["process"], cgroup["controller"],
                                nailgun_node['fqdn']))

            self.ssh_manager.check_call(nailgun_node['ip'], check_rule_cmd)

    def get_cgroups_config(self, nailgun_node):
        cmd = "cat /etc/cgconfig.conf"
        result = self.ssh_manager.execute(nailgun_node['ip'], cmd)["stdout"]
        cgroups_config = "".join([line for line in result
                                  if not line.startswith("#")])

        cgroups_to_json = [
            ('group ', ''),                        # Remove group tag
            (' {', ': {'),                         # Replace { -> : {
            ('}', '},'),                           # Replace } -> },
            (';', ','),                            # Replace ; -> ,
            (' = ', ': '),                         # Replace = -> :
            ('[a-z_]+\.{0,1}[a-z_]*', '"\g<0>"'),  # Wrap all words with " "
                                                   # Words could contain period
            ('[\s\S]*', '{\g<0> }'),               # Wrap whole string with {}
            (',[ \t\r\n]+}', '}')                  # Clear trailing commas
        ]

        for pattern, replace in cgroups_to_json:
            cgroups_config = re.sub(pattern, replace, cgroups_config)

        return json.loads(cgroups_config)

    def check_cgconfig_setup(self, config, process, controller,
                             limit=None, value=None):
        actual_limit = config[process][controller]

        if limit is None and value is None:
            asserts.assert_equal(actual_limit, {},
                                 "Actual limit is not empty: {}"
                                 .format(actual_limit))
        else:
            asserts.assert_equal(actual_limit[limit], value,
                                 "Actual value limit is not as expected: {}"
                                 .format(actual_limit[limit]))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_ha_cgroup'])
    # @log_snapshot_after_test
    def deploy_ha_cgroup(self):
        """Deploy cluster in HA mode with enabled cgroup

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 1 node with compute role
            4. Add 1 node with cinder role
            5. Deploy the cluster
            6. Check ceph status
            7. Run OSTF

        Duration 90m
        Snapshot deploy_ha_cgroup
        """
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'tenant': 'cgroup',
            'user': 'cgroup',
            'password': 'cgroup',
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }

        cgroup_data = {
            'keystone': {
                'type': 'text',
                'value': "{\"cpu\":{\"cpu.shares\":70}}",
                'label': 'keystone'
            }, }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data, cgroup_data=cgroup_data)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['cinder']
            }
        )
        # Cluster deploy
        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        # Check that task cgroup was executed
        cmd = 'fgrep  "MODULAR: cgroups/cgroups.pp" -q /var/log/puppet.log'
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        for nailgun_node in n_ctrls:
            logger.info('Check cgroups task on controller node {0}'.format(
                nailgun_node))

            self.ssh_manager.check_call(nailgun_node['ip'], cmd)

            check_group_cmd = 'sudo lscgroup | fgrep  -q cpu:/keystone'
            logger.info('Check cpu:/keystone group existence  '
                        'on controller node {0}'.format(nailgun_node['fqdn']))
            self.ssh_manager.check_call(nailgun_node['ip'], check_group_cmd)

            cgroups_config = self.get_cgroups_config(nailgun_node)
            self.check_cgconfig_setup(
                config=cgroups_config, process="keystone",
                controller="cpu", limit="cpu.shares", value=70)

        self.env.make_snapshot("deploy_ha_cgroup")

    @test(depends_on=[deploy_ha_cgroup],
          groups=['apply_cgroups_after_deploy'])
    # @log_snapshot_after_test
    def apply_cgroups_after_deploy(self):
        """

        :return:
        """

        # self.check_run("deploy_ha_cgroup")
        # self.env.revert_snapshot("deploy_ha_cgroup")

        cluster_id = self.fuel_web.get_last_created_cluster()

        cgroups = [
            {"process": "mysqld",
             "controller": "memory",
             "limit": "memory.swappiness",
             "value": 0},
            {"process": "rabbitmq",
             "controller": "blkio",
             "limit": "blkio.weight",
             "value": 500},
            {"process": "rabbitmq",
             "controller": "memory",
             "limit": "memory.swappiness",
             "value": 0},
            {"process": "keystone",
             "controller": "cpu",
             "limit": "cpu.shares",
             "value": 50},
        ]

        attributes = self.generate_attributes(cgroups)
        self.fuel_web.client.update_cluster_attributes(cluster_id, attributes)

        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        ctrl_ids = ",".join([str(nailgun_node['id'])
                             for nailgun_node in n_ctrls])

        def apply_cgroups():
            task = self.fuel_web.client.put_deployment_tasks_for_cluster(
                cluster_id=cluster_id,
                data=["cgroups"],
                node_id=ctrl_ids)
            self.fuel_web.assert_task_success(task)

        apply_cgroups()

        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)
