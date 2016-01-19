from proboscis.asserts import assert_equal, assert_true
from proboscis import test
from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import TestBasic, SetupEnvironment


@test(groups=["fuel_plugin_upstream"])
class UpstreamPlugin(TestBasic):
    """ExamplePlugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_ha_controller_neutron_example"])
    @log_snapshot_after_test
    def deploy_with_upstream_repos(self):
        admin_ip = self.env.get_admin_node_ip()
        logger.info(
            SSHManager().execute_on_remote(
                admin_ip,
                """bash -c 'yum -y install git tar createrepo \
                    rpm dpkg-devel dpkg-dev rpm-build python-pip;
                    git clone https://github.com/openstack/fuel-plugins;
                    cd fuel-plugins;
                    python setup.py sdist;
                    cd dist;
                    pip install *.tar.gz'""")
        )
        logger.info(
            SSHManager().execute_on_remote(
                admin_ip,
                """
                git clone https://github.com/mwhahaha/fuel-plugin-upstream ;
                cd fuel-plugin-upstream ;
                sed -i 's/liberty-9.0/mikata-9.0/' -i metadata.yaml ;
                fpb --build . ;
                fuel plugins --install *.rpm
                """)
        )
        data = {
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        attr = self.fuel_web.get_cluster_attributes(cluster_id)
        repos = attr['editable']['repo_setup']['repos']['value']
        for repo in repos:
            if repo['name'] in ('mos', 'mos-updates',
                                'mos-security', 'mos-holdback'):
                repo['uri'] = ('http://perestroika-repo-tst.infra.mirantis.net'
                               '/mos-repos/ubuntu/9.0-for-UCA-test/')
        self.client.update_cluster_attributes(cluster_id, attr)

        plugin_name = 'fuel_plugin_upstream'
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller', 'fuel-plugin-upstream'],
                'slave-02': ['controller', 'fuel-plugin-upstream'],
                'slave-03': ['controller', 'fuel-plugin-upstream'],
                'slave-04': ['compute', 'cinder', 'fuel-plugin-upstream'],
            }
        )
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id,test_sets=[
            'sanity','smoke','ha'])