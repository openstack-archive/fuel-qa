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
from fuelweb_test.helpers.utils import run_on_remote


def ovs_get_data(remote, table, columns=None):
    """Get data from a specified OpenVSwitch table

       :param SSHClient remote: fuel-devops.helpers.helpers object
       :param str table: ovs table name (see `ovsdb-client list-tables`)
       :param list columns:
           list of strings to get specified columns. if None - all columns
           will be requested.
       :return dict: data from JSON object
    """
    if columns:
        col = '--columns=' + ','.join(columns)
    else:
        col = ''
    cmd = ('ovs-vsctl --oneline --format=json {columns} list {table}'
           .format(columns=col, table=table))
    res = run_on_remote(remote, cmd, jsonify=True)
    logger.debug("OVS output of the command '{0}': {1}".format(cmd, res))
    return res


def ovs_decode_columns(ovs_data):
    """Decode columns from OVS data format to a python dict
       :param str ovs_data: data from JSON object
       :return list: list of decoded dicts
    """
    data = ovs_data['data']
    headings = ovs_data['headings']
    res = []
    for fields in data:
        res_fields = {}
        for i, field in enumerate(fields):
            if isinstance(field, list):
                if field[0] == 'map':
                    d = {}
                    for f in field[1]:
                        d[f[0]] = f[1]
                    res_fields[headings[i]] = d
                elif field[0] == 'uuid':
                    res_fields[headings[i]] = {'uuid': field[1]}
                else:
                    res_fields[headings[i]] = field
            else:
                res_fields[headings[i]] = field
        res.append(res_fields)
    return res


def ovs_get_tag_by_port(remote, port):
    """Get the tag used for OVS interface by Neutron port ID

        :param SSHClient remote: fuel-devops.helpers.helpers object
        :param str port: Neutron port ID
        :return str: tag number
    """
    interfaces_raw = ovs_get_data(remote,
                                  table='Interface',
                                  columns=['external_ids', 'name'])
    interfaces = ovs_decode_columns(interfaces_raw)

    ports_ifaces = {x['external_ids']['iface-id']: x['name']
                    for x in interfaces if 'iface-id' in x['external_ids']}
    logger.debug("OVS interfaces: {0}".format(ports_ifaces))
    if port not in ports_ifaces:
        raise ValueError("Neutron port {0} not found in OVS interfaces."
                         .format(port))

    iface_id = ports_ifaces[port]

    ovs_port_raw = ovs_get_data(remote,
                                table='Port {0}'.format(iface_id),
                                columns=['tag'])
    ovs_port = ovs_decode_columns(ovs_port_raw)
    logger.debug("OVS tag for port {0}: {1}".format(iface_id, ovs_port))
    ovs_tag = ovs_port[0]['tag']

    return str(ovs_tag)
