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

from core.helpers.log_helpers import logwrap
from core.models.fuel_client import Client as FuelClient

from fuelweb_test import logger

from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import RELEASE_VERSION


class NailgunClient(object):
    """NailgunClient"""  # TODO documentation

    def __init__(self, session):
        logger.info(
            'Initialization of NailgunClient using shared session \n'
            '(auth_url={})'.format(session.auth.auth_url))
        self.client = FuelClient(session=session)
        self.session = session

    def __repr__(self):
        klass, obj_id = type(self), hex(id(self))
        url = getattr(self, 'url', None)
        return "[{klass}({obj_id}), url:{url}]".format(klass=klass,
                                                       obj_id=obj_id,
                                                       url=url)

    def _get(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.get(url=url, connect_retries=1, **kwargs)

    def _delete(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.delete(url=url, connect_retries=1, **kwargs)

    def _post(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.post(url=url, connect_retries=1, **kwargs)

    def _put(self, url, **kwargs):
        if 'endpoint_filter' not in kwargs:
            kwargs.update(endpoint_filter={'service_type': 'fuel'})
        return self.session.put(url=url, connect_retries=1, **kwargs)

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
    def get_node_by_id(self, node_id):
        return self._get(url="/nodes/{}".format(node_id)).json()

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
    def deploy_custom_graph(self, cluster_id, graph_type, node_ids=None,
                            tasks=None):
        """Method to deploy custom graph on cluster.

        :param cluster_id: Cluster to be custom deployed
        :param graph_type: Type of a graph to deploy
        :param node_ids: nodes to deploy. None or empty list means all.
        :param tasks: list of string with task names in graph
        :return: ``task_uuid`` -- unique ID of accepted transaction
        """
        scenario = {"cluster": int(cluster_id),
                    "graphs": [
                        {"type": graph_type,
                         "tasks": tasks,
                         "nodes": node_ids
                         }],
                    "dry_run": False,
                    "force": False}
        endpoint = '/graphs/execute/'
        return self._post(endpoint, json=scenario).json()

    @logwrap
    def get_release_tasks(self, release_id):
        """Method to get release deployment tasks.

        :param release_id: Id of release to get tasks
        :return: list of deployment graphs
        """
        return self._get(
            '/releases/{rel_id}/deployment_graphs/'.format(
                rel_id=release_id)).json()

    @logwrap
    def get_release_tasks_by_type(self, release_id, graph_type):
        """Method to get release deployment tasks by type.

        :param release_id: Id of release to get tasks
        :param graph_type: Type of a graph to deploy
        :return: list of deployment graphs for a given type
        """
        return self._get(
            "/releases/{0}/deployment_graphs/{1}".format(
                release_id, graph_type)).json()

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
        msg = 'get_releases_details is deprecated in favor of get_release'
        warn(msg, DeprecationWarning)
        logger.warning(msg)
        return self._get(url="/releases/{}".format(release_id)).json()

    @logwrap
    def get_node_disks(self, node_id):
        return self._get(url="/nodes/{}/disks".format(node_id)).json()

    @logwrap
    def put_node_disks(self, node_id, data):
        return self._put(
            url="/nodes/{}/disks".format(node_id), json=data).json()

    @logwrap
    def get_deployable_releases(self):
        return sorted(
            [
                release for release
                in self.get_releases() if release['is_deployable']],
            key=lambda rel: rel['id']
        )

    @logwrap
    def get_release_id(self, release_name=OPENSTACK_RELEASE,
                       release_version=RELEASE_VERSION):
        for release in self.get_releases():
            if (release_name.lower() in release["name"].lower() and
                    release_version.lower() in release["version"].lower()):
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
        warn('get_ostf_test_sets has been moved to '
             'core.models.fuel_client.Client.ostf.get_test_sets',
             DeprecationWarning)
        return self.client.ostf.get_test_sets(cluster_id=cluster_id)

    @logwrap
    def get_ostf_tests(self, cluster_id):
        warn('get_ostf_tests has been moved to '
             'core.models.fuel_client.Client.ostf.get_tests',
             DeprecationWarning)
        return self.client.ostf.get_tests(cluster_id=cluster_id)

    @logwrap
    def get_ostf_test_run(self, cluster_id):
        warn('get_ostf_test_run has been moved to '
             'core.models.fuel_client.Client.ostf.get_test_runs',
             DeprecationWarning)
        return self.client.ostf.get_test_runs(cluster_id=cluster_id)

    @logwrap
    def ostf_run_tests(self, cluster_id, test_sets_list):
        warn('ostf_run_tests has been moved to '
             'core.models.fuel_client.Client.ostf.run_tests',
             DeprecationWarning)
        return self.client.ostf.run_tests(
            cluster_id=cluster_id, test_sets=test_sets_list)

    @logwrap
    def ostf_run_singe_test(self, cluster_id, test_sets_list, test_name):
        warn('ostf_run_singe_test has been moved to '
             'core.models.fuel_client.Client.ostf.run_tests',
             DeprecationWarning)
        return self.client.ostf.run_tests(
            cluster_id=cluster_id, test_sets=test_sets_list,
            test_name=test_name)
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
    def get_settings(self, data=None):
        return self._get(url="/settings").json()

    @logwrap
    def send_fuel_stats(self, enabled=False):
        settings = self.get_settings()
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
    def get_custom_cluster_deployment_tasks(self, cluster_id, custom_type):
        """ Get list of all deployment tasks for cluster."""
        return self._get(
            '/clusters/{}/deployment_tasks/?graph_type={}'.format(
                cluster_id,
                custom_type
            )).json()

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
    def put_deployment_tasks_for_cluster(self, cluster_id, data, node_id,
                                         force=False):
        """Put  task to be executed on the nodes from cluster

        :param cluster_id: int, cluster id
        :param data: list, tasks ids
        :param node_id: str, Node ids where task should be run,
               can be node_id=1, or node_id =1,2,3,
        :param force: bool, run particular task on nodes and do not care
               if there were changes or not
        :return:
        """
        return self._put(
            '/clusters/{0}/deploy_tasks?nodes={1}{2}'.format(
                cluster_id, node_id, '&force=1' if force else ''),
            json=data).json()

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
                             node_id=None, node_ids=None):
        """Upload configuration.

        :param config: a dictionary of configuration to upload.
        :param cluster_id: An integer number of cluster id.
        :param role: a string of role name.
        :param node_id: An integer number of node id.
        :param node_ids: a list of node ids
        :return: a decoded JSON response.
        """
        data = {'cluster_id': cluster_id, 'configuration': config}
        if role is not None:
            data['node_role'] = role
        if node_id is not None:
            data['node_id'] = node_id
        if node_ids is not None:
            data['node_ids'] = node_ids
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
    def update_vip_ip(self, cluster_id, data):
        return self._post(
            "/clusters/{0}/network_configuration/ips/vips".format(cluster_id),
            json=data).json()

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
    def get_deployed_cluster_attributes(self, cluster_id):
        url = '/clusters/{}/attributes/deployed/'.format(cluster_id)
        return self._get(url).json()

    @logwrap
    def get_deployed_network_configuration(self, cluster_id):
        url = '/clusters/{}/network_configuration/deployed'.format(
            cluster_id)
        return self._get(url).json()

    @logwrap
    def get_default_cluster_settings(self, cluster_id):
        url = '/clusters/{}/attributes/defaults'.format(cluster_id)
        return self._get(url).json()

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

    # ConfigDB Extension

    @logwrap
    def get_components(self, comp_id=None):
        """Get all existing components

        :param comp_id: component id
        :return: components data
        """
        endpoint = '/config/components'
        endpoint = '{path}/{component_id}'.format(
            path=endpoint, component_id=comp_id) if comp_id else endpoint
        return self._get(endpoint).json()

    @logwrap
    def create_component(self, data):
        """ Create component with specified data

        :param data:
        :return:
        """
        return self._post('/config/components', json=data).json()

    @logwrap
    def get_environments(self, env_id=None):
        """Get all existing environments

        :param env_id: environment id
        :return: env data
        """
        endpoint = '/config/environments'
        endpoint = '{path}/{env_id}'.format(
            env_id=env_id, path=endpoint) if env_id else endpoint
        return self._get(endpoint).json()

    @logwrap
    def create_environment(self, data):
        """ Create env with specified data

        :param data:
        :return:
        """
        return self._post('/config/environments', json=data).json()

    @logwrap
    def get_global_resource_id_value(self, env_id, resource_id,
                                     effective=False):
        """ Get global resource value for specified env and resource

        :param env_id:  str or int
        :param resource_id: int
        :param effective: true or false
        :return: global resource value
        """
        endpoint = '/config/environments/' \
                   '{env_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource_id)
        endpoint = endpoint + '?effective' if effective else endpoint

        return self._get(endpoint).json()

    @logwrap
    def get_global_resource_name_value(self, env_id, resource_name,
                                       effective=False):
        """ Get global resource value for specified env and resource

        :param env_id:  str or int
        :param resource_name: str or int
        :param effective: true or false
        :return: global resource value
        """
        endpoint = '/config/environments/' \
                   '{env_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource_name)
        endpoint = endpoint + '?effective' if effective else endpoint

        return self._get(endpoint).json()

    @logwrap
    def put_global_resource_value(self, env_id, resource, data):
        """Put global resource value

        :param env_id: str or int
        :param resource: name or id
        :param data: data in dict format
        """
        endpoint = '/config/environments/' \
                   '{env_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource)
        return self._put(endpoint, json=data)

    @logwrap
    def put_global_resource_override(self, env_id, resource, data):
        """Put global resource override value

        :param env_id: str or int
        :param resource: name or id
        :param data: data in dict format
        """
        endpoint = '/config/environments/' \
                   '{env_id}/resources/{resource}' \
                   '/overrides'.format(env_id=env_id, resource=resource)
        return self._put(endpoint, json=data)

    @logwrap
    def get_node_resource_id_value(self, env_id, resource_id, node_id,
                                   effective=False):
        """ Get node level resource value for specified env, resource and node

        :param env_id: str or int
        :param resource_id: id
        :param node_id: str or int
        :param effective: true or false
        :return: node resource value
        """
        endpoint = '/config/environments/' \
                   '{env_id}/nodes/{node_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource_id,
                                    node_id=node_id)
        endpoint = endpoint + '?effective' if effective else endpoint

        return self._get(endpoint).json()

    @logwrap
    def get_node_resource_name_value(self, env_id, resource_name, node_id,
                                     effective=False):
        """ Get node level resource value for specified env, resource and node

        :param env_id: str or int
        :param resource_name: name in string format
        :param node_id: str or int
        :param effective: true or false
        :return: node resource value
        """
        endpoint = '/config/environments/' \
                   '{env_id}/nodes/{node_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource_name,
                                    node_id=node_id)
        endpoint = endpoint + '?effective' if effective else endpoint

        return self._get(endpoint).json()

    @logwrap
    def put_node_resource_value(self, env_id, resource, node_id, data):
        """ Put node resource value

        :param env_id: str or int
        :param resource: name or id
        :param node_id: str or int
        :param data: data in dict format
        """
        endpoint = '/config/environments/' \
                   '{env_id}/nodes/{node_id}/resources/{resource}' \
                   '/values'.format(env_id=env_id, resource=resource,
                                    node_id=node_id)
        return self._put(endpoint, json=data)

    @logwrap
    def put_node_resource_overrides(self, env_id, resource, node_id, data):
        """Put node resource override value

        :param env_id: str or int
        :param resource: name or id
        :param node_id: str or int
        :param data: data in dict format
        """
        endpoint = '/config/environments/' \
                   '{env_id}/nodes/{node_id}/resources/{resource}' \
                   '/overrides'.format(env_id=env_id, resource=resource,
                                       node_id=node_id)
        return self._put(endpoint, json=data)

    @logwrap
    def plugins_list(self):
        """Get list of installed plugins"""
        endpoint = '/plugins'
        return self._get(endpoint).json()

    @logwrap
    def add_new_role(self, rel_id, data):
        """Uses POST to create new role with data

        :param rel_id: str or int
        :param data: data in dict format
        """

        endpoint = '/releases/{rel_id}/roles'.format(rel_id=rel_id)
        return self._post(endpoint, json=data)

    @logwrap
    def update_role_data(self, rel_id, role_name, data):
        """Update tag's data

        :param rel_id: str or int
        :param role_name: str
        :param data: data in dict format
        """
        endpoint = '/releases/{rel_id}/roles/{role_name}'.format(
            rel_id=rel_id, role_name=role_name)
        return self._put(endpoint, json=data).json()

    @logwrap
    def get_role_data(self, rel_id, role_name):
        """Gets tag's data

        :param rel_id: str or int
        :param role_name: str
        """
        endpoint = '/releases/{rel_id}/roles/{role_name}'.format(
            rel_id=rel_id, role_name=role_name)
        return self._get(endpoint).json()

    @logwrap
    def add_new_tag(self, parent_id, data, parent='releases'):
        """Uses POST to create new tag with data

        :param parent_id: str or int
        :param data: data in dict format
        :param parent: str

        Parent could be 'releases' or 'clusters'
        """

        endpoint = '/{parent}/{id}/tags'.format(
            parent=parent, id=parent_id)
        return self._post(endpoint, json=data)

    @logwrap
    def get_tag_data(self, parent_id, tag_name, parent='releases'):
        """Gets tag's data

        :param parent_id: str or int
        :param tag_name: str
        :param parent: str

        Parent could be 'releases' or 'clusters'
        """
        endpoint = '/{parent}/{id}/tags/{tag_name}'.format(
            parent=parent, id=parent_id, tag_name=tag_name)
        return self._get(endpoint).json()

    @logwrap
    def update_tag_data(self, parent_id, tag_name, data, parent='releases'):
        """Update tag's data

        :param parent_id: str or int
        :param tag_name: str
        :param data: data in dict format
        :param parent: str

        Parent could be 'releases' or 'clusters'
        """
        endpoint = '/{parent}/{id}/tags/{tag_name}'.format(
            parent=parent, id=parent_id, tag_name=tag_name)
        return self._put(endpoint, json=data).json()

    @logwrap
    def del_tag(self, parent_id, tag_name, parent='releases'):
        """Delete tag

        :param parent_id: str or int
        :param tag_name: str
        :param parent: str

        Parent could be 'releases' or 'clusters'
        """
        endpoint = '/{parent}/{id}/tags/{tag_name}'.format(
            parent=parent, id=parent_id, tag_name=tag_name)
        return self._delete(endpoint)

    @logwrap
    def get_all_tags(self, parent_id, parent='releases'):
        """Get all tags from parent

        :param parent_id: str or int
        :param parent: str

        Parent could be 'releases' or 'clusters'
        """
        endpoint = '/{parent}/{id}/tags'.format(parent=parent, id=parent_id)
        return self._get(endpoint).json()
