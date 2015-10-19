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

from fuelweb_test import logger
from fuelweb_test import logwrap


@logwrap
def get_crm_node_attributes(self, crm_node_attr):
    """Get crm node attributes to a python dict:
            return:
                {
                  fqdn: {
                    'arch':
                    'cpu_cores':
                    'cpu_info':
                    'cpu_load':
                    'cpu_speed':
                    'free_swap':
                    'gtidd':
                    'master-p_conntrackd':
                    'master-p_rabbitmq-server':
                    'os':
                    '#health_disk':        # only on master if root_free < 100M
                    'pingd':
                    'rabbit-master':       # only on master
                    'rabbit-start-time':
                    'rabbit_get_alarms_timeouts':
                    'rabbit_list_channels_timeouts':
                    'ram_free':
                    'ram_total':
                    'root_free':
                    'var_lib_glance_free':
                    'var_lib_mysql_free':
                    'var_log_free':
                  },
                  ...
                }
    """

    logger.info('Get crm node attributes from %s ', crm_node_attr)

    if "Node Attributes:" in crm_node_attr:
        crm_node_attr_from = crm_node_attr.split("Node Attributes:")[1]
        crm_node_attr_to = crm_node_attr_from.split("Failed actions:")[0]
        crm_node_attr_string = crm_node_attr_to.strip()
        attributes_raw_list = crm_node_attr_string.split("* Node")[1:]
        attributes_by_nodes_raw = [x.splitlines() for x in attributes_raw_list]
        attributes_by_nodes = [[x.translate(None, "\t+ ")
                                for x in nodes]
                               for nodes in attributes_by_nodes_raw]
        attributes = {}
        for node in attributes_by_nodes:
            node_name = node[0].strip(":")
            attributes[node_name] = {}
            for attribute in node[1:]:
                attribute_name, attribute_value = attribute.rsplit(':', 1)
                attributes[node_name][attribute_name] = attribute_value

    return attributes
