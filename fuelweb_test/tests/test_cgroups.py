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
from __future__ import division

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

    @staticmethod
    def generate_attributes(cgroups):
        """Generate cluster attributes structure from cgroups dicts."""

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

    @staticmethod
    def check_cgconfig_setup(config, process, controller,
                             limit=None, value=None):
        """Check /etc/cgconfig.conf contains properly configured cgroup."""

        actual_limit = config[process][controller]

        if limit is None and value is None:
            asserts.assert_equal(actual_limit, {},
                                 "Actual limit is not empty: {}"
                                 .format(actual_limit))
        else:
            asserts.assert_equal(actual_limit[limit], value,
                                 "Actual value limit is not as expected for "
                                 "process {}, controller {}, limit {}, "
                                 "expected value = {}, actual == {}"
                                 .format(process, controller, limit, value,
                                         actual_limit[limit]))

    @staticmethod
    def generate_lscgroups(cgroups):
        """Generate a list of lscgroups entities from cgroups dicts."""

        cpu_controller = "cpu,cpuacct"
        return ["{}:/{}".format(cpu_controller
                if cgroup["controller"] in cpu_controller
                else cgroup["controller"], cgroup["process"])
                for cgroup in cgroups]

    def apply_cgroups(self, cgroups, node_ids):
        cluster_id = self.fuel_web.get_last_created_cluster()

        self.fuel_web.client.update_cluster_attributes(
            cluster_id, self.generate_attributes(cgroups))
        task = self.fuel_web.client.put_deployment_tasks_for_cluster(
            cluster_id=cluster_id,
            data=["upload_configuration", "configuration_symlink",
                  "hiera", "cgroups"],
            node_id=node_ids)
        self.fuel_web.assert_task_success(task)

    def get_cgroups_config(self, nailgun_node):
        """Get /etc/cgconfig.conf from node, transform it to json and loads

        Before transformation:
            group mysqld {
                   memory {
                           memory.swappiness = 0;
                   }
            }
            group keystone {
                   cpu {
                           cpu.shares = 70;
                   }
            }
            group rabbitmq {
                   blkio {
                           blkio.weight = 500;
                   }
            memory {
                           memory.swappiness = 0;
                   }
            }

        After transformation:
            {
                "mysqld": {
                    "memory": {
                        "memory.swappiness": 0
                    }
                },
                "keystone": {
                    "cpu": {
                        "cpu.shares": 70
                    }
                },
                "rabbitmq": {
                    "blkio": {
                        "blkio.weight": 500
                    },
                    "memory": {
                        "memory.swappiness": 0
                    }
                }
            }
        """

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

    def check_cgroups_on_node(self, nailgun_node, cgroups):
        """Complex validation of cgroups on particular node."""

        cgroups_config = self.get_cgroups_config(nailgun_node)

        for cgroup in cgroups:
            logger.info("Check cgroup config for {} {} on node {}"
                        .format(cgroup["process"], cgroup["controller"],
                                nailgun_node['fqdn']))
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

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=['deploy_ha_cgroup'])
    @log_snapshot_after_test
    def deploy_ha_cgroup(self):
        """Deploy cluster in HA mode with enabled cgroups

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
        self.check_run("deploy_ha_cgroup")
        self.env.revert_snapshot("ready_with_5_slaves")
        data = {
            'tenant': 'cgroup',
            'user': 'cgroup',
            'password': 'cgroup',
            'net_provider': 'neutron',
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan']
        }

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

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

        cgroup_data = [{
            "process": "keystone",
            "controller": "cpu",
            "limit": "cpu.shares",
            "value": 70,
        }]

        self.fuel_web.client.update_cluster_attributes(
            cluster_id, self.generate_attributes(cgroup_data))

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
                nailgun_node["fqdn"]))

            self.ssh_manager.check_call(nailgun_node['ip'], cmd)

            self.check_cgroups_on_node(nailgun_node, cgroup_data)

        self.env.make_snapshot("deploy_ha_cgroup", is_make=True)

    @test(depends_on=[deploy_ha_cgroup],
          groups=['apply_cgroups_after_deploy'])
    @log_snapshot_after_test
    def apply_cgroups_after_deploy(self):
        """Apply, reconfigure and disable cgroups limits to services

        Scenario:
            1. Revert snapshot deploy_ha_cgroup
            2. Configure and validate cgroups for mysqld, rabbitmq
               and keystone
            3. Reconfigure and validate cgroups for mysqld,
               rabbitmq and keystone
            4. Disable cgroups for mysqld, rabbitmq and keystone

        Duration 15m
        """

        self.show_step(1)
        self.env.revert_snapshot("deploy_ha_cgroup")

        cluster_id = self.fuel_web.get_last_created_cluster()
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        ctrl_ids = ",".join([str(nailgun_node['id'])
                             for nailgun_node in n_ctrls])

        self.show_step(2)
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

        self.apply_cgroups(cgroups, ctrl_ids)
        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)

        self.show_step(3)
        cgroups = [
            {"process": "mysqld",
             "controller": "memory",
             "limit": "memory.swappiness",
             "value": 10},
            {"process": "rabbitmq",
             "controller": "blkio",
             "limit": "blkio.weight",
             "value": 400},
            {"process": "rabbitmq",
             "controller": "memory",
             "limit": "memory.swappiness",
             "value": 60},
            {"process": "keystone",
             "controller": "cpu",
             "limit": "cpu.shares",
             "value": 70},
        ]

        self.apply_cgroups(cgroups, ctrl_ids)
        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)

        self.show_step(4)
        cgroups = [
            {"process": "mysqld",
             "controller": "memory"},
            {"process": "rabbitmq",
             "controller": "blkio"},
            {"process": "rabbitmq",
             "controller": "memory"},
            {"process": "keystone",
             "controller": "cpu"},
        ]

        self.apply_cgroups(cgroups, ctrl_ids)
        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)

    @test(depends_on=[deploy_ha_cgroup],
          groups=['apply_relative_cgroups_after_deploy'])
    @log_snapshot_after_test
    def apply_relative_cgroups_after_deploy(self):
        """Apply relative cgroups limits to services

        Scenario:
            1. Revert snapshot deploy_ha_cgroup
            2. Configure and validate cgroups for mysqld, rabbitmq
               and keystone with relative memory count

        Duration 15m
        """
        self.show_step(1)
        self.env.revert_snapshot("deploy_ha_cgroup")

        cluster_id = self.fuel_web.get_last_created_cluster()
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        ctrl_ids = ",".join([str(nailgun_node['id'])
                             for nailgun_node in n_ctrls])

        self.show_step(2)
        cgroups = [
            {"process": "mysqld",
             "controller": "memory",
             "limit": "memory.swappiness",
             "value": 0},
            {"process": "mysqld",
             "controller": "memory",
             "limit": "memory.soft_limit_in_bytes",
             "value": "%5,10,3000"},
            {"process": "rabbitmq",
             "controller": "blkio",
             "limit": "blkio.weight",
             "value": 500},
            {"process": "rabbitmq",
             "controller": "memory",
             "limit": "memory.soft_limit_in_bytes",
             "value": "%99,10,250"},
            {"process": "keystone",
             "controller": "cpu",
             "limit": "cpu.shares",
             "value": 50},
            {"process": "keystone",
             "controller": "memory",
             "limit": "memory.soft_limit_in_bytes",
             "value": "%1,250,2500"},
        ]

        self.apply_cgroups(cgroups, ctrl_ids)

        memory = float("".join(self.ssh_manager.execute(
            n_ctrls[0]["ip"], "facter memorysize_mb")["stdout"]))

        for cgroup in cgroups:
            if cgroup["limit"] == "memory.soft_limit_in_bytes":
                # pylint: disable=no-member
                percent, min_mem, max_mem = cgroup["value"].split(",")
                # pylint: enable=no-member
                percent = int(percent.replace("%", "")) * memory / 100
                min_mem, max_mem = int(min_mem), int(max_mem)

                value = sorted((min_mem, percent, max_mem))[1]
                cgroup["value"] = int(value * 1024 * 1024)

        logger.info("New cgroups to verify: {}".format(cgroups))
        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)

    @test(depends_on=[deploy_ha_cgroup],
          groups=['apply_cgroups_reboot_node'])
    @log_snapshot_after_test
    def apply_cgroups_reboot_node(self):
        """Apply cgroups limits to services, reboot, verify

        Scenario:
            1. Revert snapshot deploy_ha_cgroup
            2. Configure and validate cgroups for mysqld, rabbitmq
               and keystone
            3. Reboot controller
            4. Validate cgroups for mysqld, rabbitmq and keystone

        Duration 15m
        """

        self.show_step(1)
        self.env.revert_snapshot("deploy_ha_cgroup")

        cluster_id = self.fuel_web.get_last_created_cluster()
        n_ctrls = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        ctrl_ids = ",".join([str(nailgun_node['id'])
                             for nailgun_node in n_ctrls])

        self.show_step(2)
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

        self.apply_cgroups(cgroups, ctrl_ids)
        for nailgun_node in n_ctrls:
            self.check_cgroups_on_node(nailgun_node, cgroups)

        self.show_step(3)
        target_controller = self.fuel_web.get_nailgun_primary_node(
            self.fuel_web.get_devops_node_by_nailgun_node(n_ctrls[0]))
        self.fuel_web.cold_restart_nodes([target_controller])

        self.show_step(4)
        self.check_cgroups_on_node(n_ctrls[0], cgroups)
