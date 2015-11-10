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
from fuelweb_test.helpers.utils import run_on_remote_get_results

from xml.etree import ElementTree


def get_pacemaker_nodes_attributes(cibadmin_status_xml):
    """Parse 'cibadmin --query --scope status'.
    :param cibadmin_status_xml: stdout from 'cibadmin --query --scope status'
    :return: nested dictionary with node-fqdn and attribute name as keys
    """

    """ Get cibadmin_status to a python dict:
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
    root = ElementTree.fromstring(cibadmin_status_xml)
    nodes = {}
    for node_state in root.iter('node_state'):
        node_name = node_state.get('uname')
        nodes[node_name] = {}
        for instance_attribute in node_state.iter('nvpair'):
            nodes[node_name][instance_attribute.get(
                'name')] = instance_attribute.get('value')
    return nodes


def get_pcs_nodes(pcs_status_xml):
    """Parse 'pcs status xml'. <Nodes> section
    :param pcs_status_xml: stdout from 'pcs status xml'
    :return: nested dictionary with node-fqdn and attribute name as keys
    """
    """ Get crm node attributes to a python dict:
        return:
            {
              fqdn: {
                'node name':
                'id':
                'online':
                'standby':
                'standby_on_fail':
                'maintenance':
                'pending':
                'unclean':
                'shutdown':
                'expected_up':
                'is_dc':
                'resources_running':
                'type':
              },
              ...
            }
    """

    root = ElementTree.fromstring(pcs_status_xml)
    nodes = {}
    for nodes_group in root.iter('nodes'):
        for node in nodes_group:
            nodes[node.get('name')] = node.attrib
    return nodes


def get_pcs_status_xml(self, devops_node_name):
    """Parse 'pcs status xml'. <Nodes> section
    :param devops_node_name: name of controller
    :return: nested dictionary with node-fqdn and attribute name as keys
    """
    with self.fuel_web.get_ssh_for_node(devops_node_name) as remote:
            pcs_status_xml = run_on_remote_get_results(
                remote, 'pcs status xml')['stdout_str']
            return pcs_status_xml
