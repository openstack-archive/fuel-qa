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

from warnings import warn

from keystoneauth1.identity import V2Password
from keystoneauth1.session import Session as KeystoneSession

from fuelweb_test import logwrap
from fuelweb_test import logger
from fuelweb_test.settings import FORCE_HTTPS_MASTER_NODE
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import OPENSTACK_RELEASE


class NailgunClient(object):
    """NailgunClient"""  # TODO documentation

    def __init__(self, admin_node_ip=None, session=None, **kwargs):
        if session:
            logger.info(
                'Initialization of NailgunClient using shared session \n'
                '(auth_url={})'.format(session.auth.auth_url))
            self.session = session
        else:
            warn(
                'Initialization of NailgunClient by IP is deprecated, '
                'please use keystonesession1.session.Session',
                DeprecationWarning)

            if FORCE_HTTPS_MASTER_NODE:
                url = "https://{0}:8443".format(admin_node_ip)
            else:
                url = "http://{0}:8000".format(admin_node_ip)
            logger.info('Initiate Nailgun client with url %s', url)
            keystone_url = "http://{0}:5000/v2.0".format(admin_node_ip)

            creds = dict(KEYSTONE_CREDS, **kwargs)

            auth = V2Password(
                auth_url=keystone_url,
                username=creds['username'],
                password=creds['password'],
                tenant_name=creds['tenant_name'])
            # TODO: in v3 project_name

            self.session = KeystoneSession(auth=auth, verify=False)

        super(NailgunClient, self).__init__()

    def __repr__(self):
        klass, obj_id = type(self), hex(id(self))
        url = getattr(self, 'url', None)
        return "[{klass}({obj_id}), url:{url}]".format(klass=klass,
                                                       obj_id=obj_id,
                                                       url=url)

    def _get(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.get(url=url, **kwargs)

    def _delete(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.delete(url=url, **kwargs)

    def _post(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.post(url=url, **kwargs)

    def _put(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.put(url=url, **kwargs)

    def list_nodes(self):
        return self._get(url="/nodes/").json()

    def list_cluster_nodes(self, cluster_id):
        return self._get(url="/nodes/?cluster_id={}".format(cluster_id)).json()

    @logwrap
    def get_networks(self, cluster_id):
        net_provider = self.get_cluster(cluster_id)['net_provider']
        return self._get(
            url="/clusters/{}/network_configuration/{}".format(
                cluster_id, net_provider
            )).json()

    @logwrap
    def verify_networks(self, cluster_id):
        net_provider = self.get_cluster(cluster_id)['net_provider']
        return self._put(
            "/clusters/{}/network_configuration/{}/verify/".format(
                cluster_id, net_provider
            ),
            json=self.get_networks(cluster_id)
        ).json()

    def get_cluster_attributes(self, cluster_id):
        return self._get(
            url="/clusters/{}/attributes/".format(cluster_id)).json()

    def get_cluster_vmware_attributes(self, cluster_id):
        return self._get(
            url="/clusters/{}/vmware_attributes/".format(cluster_id),
        ).json()

    @logwrap
    def update_cluster_attributes(self, cluster_id, attrs):
        return self._put(
            "/clusters/{}/attributes/".format(cluster_id),
            json=attrs
        ).json()

    @logwrap
    def update_cluster_vmware_attributes(self, cluster_id, attrs):
        return self._put(
            "/clusters/{}/vmware_attributes/".format(cluster_id),
            json=attrs
        ).json()

    @logwrap
    def get_cluster(self, cluster_id):
        return self._get(url="/clusters/{}".format(cluster_id)).json()

    @logwrap
    def update_cluster(self, cluster_id, data):
        return self._put(
            "/clusters/{}/".format(cluster_id),
            json=data
        ).json()

    @logwrap
    def delete_cluster(self, cluster_id):
        return self._delete(url="/clusters/{}/".format(cluster_id)).json()

    @logwrap
    def update_node(self, node_id, data):
        return self._put(
            "/nodes/{}/".format(node_id), json=data
        ).json()

    @logwrap
    def update_nodes(self, data):
        return self._put(url="/nodes", json=data).json()

    @logwrap
    def delete_node(self, node_id):
        return self._delete(url="/nodes/{}/".format(node_id)).json()

    @logwrap
    def deploy_cluster_changes(self, cluster_id):
        return self._put(url="/clusters/{}/changes/".format(cluster_id)).json()

    @logwrap
    def get_task(self, task_id):
        return self._get(url="/tasks/{}".format(task_id)).json()

    @logwrap
    def get_tasks(self):
        return self._get(url="/tasks").json()

    @logwrap
    def get_releases(self):
        return self._get(url="/releases/").json()

    @logwrap
    def get_release(self, release_id):
        return self._get(url="/releases/{}".format(release_id)).json()

    @logwrap
    def put_release(self, release_id, data):
        return self._put(
            url="/releases/{}".format(release_id), json=data).json()

    @logwrap
    def get_releases_details(self, release_id):
        warn('get_releases_details is deprecated in favor of get_release')
        return self._get(url="/releases/{}".format(release_id)).json()

    @logwrap
    def get_node_disks(self, node_id):
        return self._get(url="/nodes/{}/disks".format(node_id)).json()

    @logwrap
    def put_node_disks(self, node_id, data):
        return self._put(
            url="/nodes/{}/disks".format(node_id), json=data).json()

    @logwrap
    def get_release_id(self, release_name=OPENSTACK_RELEASE):
        for release in self.get_releases():
            if release["name"].lower().find(release_name.lower()) != -1:
                return release["id"]

    @logwrap
    def get_release_default_net_settings(self, release_id):
        return self._get(url="/releases/{}/networks".format(release_id)).json()

    @logwrap
    def put_release_default_net_settings(self, release_id, data):
        return self._put(
            "/releases/{}/networks".format(release_id),
            json=data).json()

    @logwrap
    def get_node_interfaces(self, node_id):
        return self._get(url="/nodes/{}/interfaces".format(node_id)).json()

    @logwrap
    def put_node_interfaces(self, data):
        return self._put(url="/nodes/interfaces", json=data).json()

    @logwrap
    def list_clusters(self):
        return self._get(url="/clusters/").json()

    @logwrap
    def clone_environment(self, environment_id, data):
        return self._post(
            "/clusters/{}/upgrade/clone".format(environment_id),
            json=data
        ).json()

    @logwrap
    def reassign_node(self, cluster_id, data):
        return self._post(
            "/clusters/{}/upgrade/assign".format(cluster_id),
            json=data
        ).json()

    @logwrap
    def create_cluster(self, data):
        logger.info('Before post to nailgun')
        return self._post(url="/clusters", json=data).json()

    # ## OSTF ###
    @logwrap
    def get_ostf_test_sets(self, cluster_id):
        return self._get(
            url="/testsets/{}".format(cluster_id),
            endpoint_filter={'service_type': 'ostf'}
        ).json()

    @logwrap
    def get_ostf_tests(self, cluster_id):
        return self._get(
            url="/tests/{}".format(cluster_id),
            endpoint_filter={'service_type': 'ostf'}
        ).json()

    @logwrap
    def get_ostf_test_run(self, cluster_id):
        return self._get(
            url="/testruns/last/{}".format(cluster_id),
            endpoint_filter={'service_type': 'ostf'}
        ).json()

    @logwrap
    def ostf_run_tests(self, cluster_id, test_sets_list):
        logger.info('Run OSTF tests at cluster #%s: %s',
                    cluster_id, test_sets_list)
        data = []
        for test_set in test_sets_list:
            data.append(
                {
                    'metadata': {'cluster_id': str(cluster_id), 'config': {}},
                    'testset': test_set
                }
            )
        # get tests otherwise 500 error will be thrown
        self.get_ostf_tests(cluster_id)
        return self._post(
            "/testruns",
            json=data,
            endpoint_filter={'service_type': 'ostf'})

    @logwrap
    def ostf_run_singe_test(self, cluster_id, test_sets_list, test_name):
        # get tests otherwise 500 error will be thrown
        self.get_ostf_tests(cluster_id)
        logger.info('Get tests finish with success')
        data = []
        for test_set in test_sets_list:
            data.append(
                {
                    'metadata': {'cluster_id': str(cluster_id), 'config': {}},
                    'tests': [test_name],
                    'testset': test_set
                }
            )
        return self._post(
            "/testruns",
            json=data,
            endpoint_filter={'service_type': 'ostf'}).json()
    # ## /OSTF ###

    @logwrap
    def update_network(self, cluster_id, networking_parameters=None,
                       networks=None):
        nc = self.get_networks(cluster_id)
        if networking_parameters is not None:
            for k in networking_parameters:
                nc["networking_parameters"][k] = networking_parameters[k]
        if networks is not None:
            nc["networks"] = networks

        net_provider = self.get_cluster(cluster_id)['net_provider']
        return self._put(
            "/clusters/{}/network_configuration/{}".format(
                cluster_id, net_provider
            ),
            json=nc,

        ).json()

    @logwrap
    def get_cluster_id(self, name):
        for cluster in self.list_clusters():
            if cluster["name"] == name:
                logger.info('Cluster name is {:s}'.format(name))
                logger.info('Cluster id is {:d}'.format(cluster["id"]))
                return cluster["id"]

    @logwrap
    def add_syslog_server(self, cluster_id, host, port):
        # Here we updating cluster editable attributes
        # In particular we set extra syslog server
        attributes = self.get_cluster_attributes(cluster_id)
        attributes["editable"]["syslog"]["syslog_server"]["value"] = host
        attributes["editable"]["syslog"]["syslog_port"]["value"] = port
        self.update_cluster_attributes(cluster_id, attributes)

    @logwrap
    def get_cluster_vlans(self, cluster_id):
        cluster_vlans = []
        nc = self.get_networks(cluster_id)['networking_parameters']
        vlans = nc["vlan_range"]
        cluster_vlans.extend(vlans)

        return cluster_vlans

    @logwrap
    def get_notifications(self):
        return self._get(url="/notifications").json()

    @logwrap
    def generate_logs(self):
        return self._put(url="/logs/package").json()

    @logwrap
    def provision_nodes(self, cluster_id, node_ids=None):
        return self.do_cluster_action(cluster_id, node_ids=node_ids)

    @logwrap
    def deploy_nodes(self, cluster_id, node_ids=None):
        return self.do_cluster_action(
            cluster_id, node_ids=node_ids, action="deploy")

    @logwrap
    def stop_deployment(self, cluster_id):
        return self.do_stop_reset_actions(cluster_id)

    @logwrap
    def reset_environment(self, cluster_id):
        return self.do_stop_reset_actions(cluster_id, action="reset")

    @logwrap
    def do_cluster_action(self, cluster_id, node_ids=None, action="provision"):
        if not node_ids:
            nailgun_nodes = self.list_cluster_nodes(cluster_id)
            # pylint: disable=map-builtin-not-iterating
            node_ids = map(lambda _node: str(_node['id']), nailgun_nodes)
            # pylint: enable=map-builtin-not-iterating
        return self._put(
            "/clusters/{0}/{1}?nodes={2}".format(
                cluster_id,
                action,
                ','.join(node_ids))
        ).json()

    @logwrap
    def do_stop_reset_actions(self, cluster_id, action="stop_deployment"):
        return self._put(
            "/clusters/{0}/{1}/".format(str(cluster_id), action)).json()

    @logwrap
    def get_api_version(self):
        return self._get(url="/version").json()

    @logwrap
    def run_update(self, cluster_id):
        return self._put(
            "/clusters/{0}/update/".format(str(cluster_id))).json()

    @logwrap
    def create_nodegroup(self, cluster_id, group_name):
        data = {"cluster_id": cluster_id, "name": group_name}
        return self._post(url="/nodegroups/", json=data).json()

    @logwrap
    def get_nodegroups(self):
        return self._get(url="/nodegroups/").json()

    @logwrap
    def assign_nodegroup(self, group_id, nodes):
        data = [{"group_id": group_id, "id": n["id"]} for n in nodes]
        return self._put(url="/nodes/", json=data).json()

    @logwrap
    def delete_nodegroup(self, group_id):
        return self._delete(url="/nodegroups/{0}/".format(group_id))

    @logwrap
    def update_settings(self, data=None):
        return self._put(url="/settings", json=data).json()

    @logwrap
    def send_fuel_stats(self, enabled=False):
        settings = self.update_settings()
        params = ('send_anonymous_statistic', 'user_choice_saved')
        for p in params:
            settings['settings']['statistics'][p]['value'] = enabled
        self.update_settings(data=settings)

    @logwrap
    def get_cluster_deployment_tasks(self, cluster_id):
        """ Get list of all deployment tasks for cluster."""
        return self._get(
            url='/clusters/{}/deployment_tasks'.format(cluster_id),
        ).json()

    @logwrap
    def get_release_deployment_tasks(self, release_id):
        """ Get list of all deployment tasks for release."""
        return self._get(
            url='/releases/{}/deployment_tasks'.format(release_id),
        ).json()

    @logwrap
    def get_end_deployment_tasks(self, cluster_id, end, start=None):
        """ Get list of all deployment tasks for cluster with end parameter.
        If  end=netconfig, return all tasks from the graph included netconfig
        """
        if not start:
            return self._get(
                url='/clusters/{0}/deployment_tasks?end={1}'.format(
                    cluster_id, end)
            ).json()
        return self._get(
            url='/clusters/{0}/deployment_tasks?start={1}&end={2}'.format(
                cluster_id, start, end),
        ).json()

    @logwrap
    def get_orchestrator_deployment_info(self, cluster_id):
        return self._get(
            url='/clusters/{}/orchestrator/deployment'.format(cluster_id),
        ).json()

    @logwrap
    def put_deployment_tasks_for_cluster(self, cluster_id, data, node_id):
        """ Put  task to be executed on the nodes from cluster.:
        Params:
        cluster_id : Cluster id,
        node_id: Node ids where task should be run, can be node_id=1,
        or node_id =1,2,3,
        data: tasks ids"""
        return self._put(
            '/clusters/{0}/deploy_tasks?nodes={1}'.format(
                cluster_id, node_id), json=data).json()

    @logwrap
    def put_deployment_tasks_for_release(self, release_id, data):
        return self._put(
            '/releases/{}/deployment_tasks'.format(release_id),
            json=data).json()

    @logwrap
    def set_hostname(self, node_id, new_hostname):
        """ Set a new hostname for the node"""
        data = dict(hostname=new_hostname)
        return self._put(url='/nodes/{0}/'.format(node_id), json=data).json()

    @logwrap
    def get_network_template(self, cluster_id):
        return self._get(
            url='/clusters/{}/network_configuration/template'.format(
                cluster_id),
        ).json()

    @logwrap
    def upload_network_template(self, cluster_id, network_template):
        return self._put(
            '/clusters/{}/network_configuration/template'.format(cluster_id),
            json=network_template).json()

    @logwrap
    def delete_network_template(self, cluster_id):
        return self._delete(
            url='/clusters/{}/network_configuration/template'.format(
                cluster_id),
        ).json()

    @logwrap
    def get_network_groups(self):
        return self._get(url='/networks/').json()

    @logwrap
    def get_network_group(self, network_id):
        return self._get(url='/networks/{0}/'.format(network_id)).json()

    @logwrap
    def add_network_group(self, network_data):
        return self._post(url='/networks/', json=network_data).json()

    @logwrap
    def del_network_group(self, network_id):
        return self._delete(url='/networks/{0}/'.format(network_id))

    @logwrap
    def update_network_group(self, network_id, network_data):
        return self._put(url='/networks/{0}/'.format(network_id),
                         json=network_data).json()

    @logwrap
    def create_vm_nodes(self, node_id, data):
        logger.info("Uploading VMs configuration to node {0}: {1}".
                    format(node_id, data))
        url = "/nodes/{0}/vms_conf/".format(node_id)
        return self._put(url, json={'vms_conf': data}).json()

    @logwrap
    def spawn_vms(self, cluster_id):
        url = '/clusters/{0}/spawn_vms/'.format(cluster_id)
        return self._put(url).json()

    @logwrap
    def upload_configuration(self, config, cluster_id, role=None,
                             node_id=None):
        """Upload configuration.

        :param config: a dictionary of configuration to upload.
        :param cluster_id: An integer number of cluster id.
        :param role: a string of role name.
        :param node_id: An integer number of node id.
        :return: a decoded JSON response.
        """
        data = {'cluster_id': cluster_id, 'configuration': config}
        if role is not None:
            data['node_role'] = role
        if node_id is not None:
            data['node_id'] = node_id
        url = '/openstack-config/'
        return self._post(url, json=data).json()

    @logwrap
    def get_configuration(self, configuration_id):
        """Get uploaded configuration by id.

        :param configuration_id: An integer number of configuration id.
        :return: a decoded JSON response.
        """
        return self._get(
            url='/openstack-config/{0}'.format(configuration_id),
        ).json()

    @logwrap
    def list_configuration(self, cluster_id, role=None, node_id=None):
        """Get filtered list of configurations.

        :param cluster_id: An integer number of cluster id.
        :param role: a string of role name.
        :param node_id: An integer number of node id.
        :return: a decoded JSON response.
        """
        url = '/openstack-config/?cluster_id={0}'.format(cluster_id)
        if role is not None:
            url += '&node_role={0}'.format(role)
        if node_id is not None:
            url += '&node_id={0}'.format(node_id)
        return self._get(url=url).json()

    @logwrap
    def delete_configuration(self, configuration_id):
        """Delete configuration by id.

        :param configuration_id: An integer number of configuration id.
        :return: urllib2's object of response.
        """
        url = '/openstack-config/{0}'.format(configuration_id)
        return self._delete(url=url)

    @logwrap
    def apply_configuration(self, cluster_id, role=None, node_id=None):
        """Apply configuration.

        :param cluster_id: An integer number of cluster id.
        :param role: a string of role name.
        :param node_id: An integer number of node id.
        :return: a decoded JSON response.
        """
        data = {'cluster_id': cluster_id}
        if role is not None:
            data['node_role'] = role
        if node_id is not None:
            data['node_id'] = node_id
        url = '/openstack-config/execute/'
        return self._put(url, json=data).json()

    @logwrap
    def get_vip_info(self, cluster_id):
        """Get all available vips.

        :param cluster_id: Id of cluster.
        :return: a decoded JSON response.
        """
        return self._get(
            url="/clusters/{}/network_configuration/ips/vips".format(
                cluster_id),
        ).json()

    @logwrap
    def get_vip_info_by_name(self, cluster_id, name):
        """Get vip data by its name.

        :param cluster_id: Id of cluster.
        :param name: Name of vip.
        :return: vip info with specified name.
        """
        vips_data = self.get_vip_info(cluster_id)
        logger.debug("available vips are {}".format(vips_data))
        vip_data = [vip for vip in vips_data if vip['vip_name'] == name]
        return vip_data

    @logwrap
    def update_vip_ip(self, cluster_id, vip_id, data):
        return self._put(
            "/clusters/{0}/network_configuration/ips/"
            "{1}/vips".format(cluster_id, vip_id), json=data).json()

    @logwrap
    def upload_node_attributes(self, attributes, node_id):
        """Upload node attributes for specified node.

        :param attributes: a dictionary of attributes to upload.
        :param node_id: an integer number of node id.
        :return: a decoded JSON response.
        """
        url = '/nodes/{}/attributes/'.format(node_id)
        return self._put(url, json=attributes).json()

    @logwrap
    def get_node_attributes(self, node_id):
        """Get attributes for specified node.

        :param node_id: an integer number of node id.
        :return: a decoded JSON response.
        """
        return self._get(url='/nodes/{}/attributes/'.format(node_id)).json()

    @logwrap
    def get_all_tasks_list(self):
        return self._get(url='/transactions/').json()

    @logwrap
    def get_deployment_task_hist(self, task_id):
        url = '/transactions/{task_id}/deployment_history'.format(
            task_id=task_id)
        return self._get(
            url=url,
        ).json()

    @logwrap
    def redeploy_cluster_changes(self, cluster_id, data=None):
        """Deploy the changes of cluster settings

        :param cluster_id: int, target cluster ID
        :param data: dict, updated cluster attributes (if empty, the already
                     uploaded attributes will be (re)applied)
        :return: a decoded JSON response
        """
        if data is None:
            data = {}
        return self._put(
            "/clusters/{}/changes/redeploy".format(cluster_id),
            json=data).json()

    @logwrap
    def assign_ip_address_before_deploy_start(self, cluster_id):
        return self._get(
            url='/clusters/{}/orchestrator/deployment/defaults/'.format(
                cluster_id)
        )

    @logwrap
    def get_deployment_info_for_task(self, task_id):
        return self._get(
            url='/transactions/{}/deployment_info'.format(task_id),
        ).json()

    @logwrap
    def get_cluster_settings_for_deployment_task(self, task_id):
        return self._get(
            url='/transactions/{}/settings'.format(task_id),
        ).json()

    @logwrap
    def get_network_configuration_for_deployment_task(self, task_id):
        return self._get(
            url='/transactions/{}/network_configuration/'.format(task_id),
        ).json()
