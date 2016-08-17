.. index:: Base tests

General OpenStack/Fuel Tests
****************************

General tests
=============

Base Test Case
--------------
.. automodule:: fuelweb_test.tests.base_test_case
   :members:

Admin Node Tests
----------------
.. automodule:: fuelweb_test.tests.test_admin_node
   :members:

Test Admin Node Backup-Restore
------------------------------
.. automodule:: fuelweb_test.tests.test_backup_restore
   :members:

Test Bonding base
-----------------
.. automodule:: fuelweb_test.tests.test_bonding_base
   :members:

Test Bonding
------------
.. automodule:: fuelweb_test.tests.test_bonding
   :members:

Test Bond offloading types
--------------------------
.. automodule:: fuelweb_test.tests.test_bond_offloading
   :members:

Test By Tempest
---------------
.. automodule:: fuelweb_test.tests.test_by_tempest
   :members:

Test Ceph
---------
.. automodule:: fuelweb_test.tests.test_ceph
   :members:

Test Cli
--------
.. automodule:: fuelweb_test.tests.test_cli
   :members:

Test Cli Base
-------------
.. automodule:: fuelweb_test.tests.test_cli_base
   :members:

Test Cli role component (creade/update/delete role)
---------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_cli.test_cli_role
   :members:

Test Cli deploy (deploy neutron tun)
------------------------------------
.. automodule:: fuelweb_test.tests.tests_cli.test_cli_deploy
   :members:

Test Cli deploy ceph neutron tun
--------------------------------
.. automodule:: fuelweb_test.tests.tests_cli.test_cli_deploy_ceph
   :members:

Test custom hostname
--------------------
.. automodule:: fuelweb_test.tests.test_custom_hostname
   :members:

Test Environment Action
-----------------------
.. automodule:: fuelweb_test.tests.test_environment_action
   :members:

Test ha NeutronTUN deployment group 1 (controller+baseos multirole and ceph for images/objects)
-----------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_tun.test_ha_tun_group_1
   :members:

Test ha NeutronTUN deployment group 2 (ceph for all, baseos node and ceph for all, untag networks and changed OS credentials)
-----------------------------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_tun.test_ha_tun_group_2
   :members:

Test ha NeutronTUN deployment group 3 (5 controllers, ceph for images/ephemeral and no volumes, ceph for images/ephemeral)
--------------------------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_tun.test_ha_tun_group_3
   :members:

Test ha neutron vlan deployment group 1 (cinder/ceph for images and ceph for volumes/swift)
-------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_1
   :members:

Test ha neutron vlan deployment group 2 (cinder/ceph for ephemeral and cinder/ceph for images/ephemeral)
--------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_2
   :members:

Test ha neutron vlan deployment group 3(no volumes storage/ceph volumes, ephemeral)
-----------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_3
   :members:

Test ha neutron vlan deployment group 4(cinder volumes, ceph images and rados gw/ default storage)
--------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_4
   :members:

Test ha neutron vlan deployment group 5 (ceph for volumes/images/ephemeral/rados and cinder/ceph for images/ephemeral/rados)
----------------------------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_5
   :members:

Test ha neutron vlan deployment group 6 (no volumes and ceph for images/ephemeral/rados and ceph for volumes/images/ephemeral)
------------------------------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_6
   :members:

Test ha neutron vlan deployment group 7 (no volumes/ceph for images and cinder/swift/base os)
---------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_deployments.tests_neutron_vlan.test_ha_vlan_group_7
   :members:

Test Sahara OS component with vlan and ceph
-------------------------------------------
.. automodule:: fuelweb_test.tests.tests_os_components.test_sahara_os_component
   :members:

Test Murano OS component with vlan
----------------------------------
.. automodule:: fuelweb_test.tests.tests_os_components.test_murano_os_component
   :members:

Test mixed OS components
------------------------
.. automodule:: fuelweb_test.tests.tests_os_components.test_mixed_os_components
   :members:

Test failover group 1
---------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover_group_1
   :members:

Test failover group 2
---------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover_group_2
   :members:

Test failover mongo
-------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover_mongo
   :members:

Test Mongo Multirole
--------------------
.. automodule:: fuelweb_test.tests.tests_multirole.test_mongo_multirole
   :members:

Test scale neutron vlan deployment add/delete compute/cinder+cinder+ceph
------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_5
   :members:

Test scale neutron tun deployment add/delete compute+cinder+ceph+ephemeral
--------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_6
   :members:

Test High Availability on one controller
----------------------------------------
.. automodule:: fuelweb_test.tests.test_ha_one_controller
   :members:

Test High Availability on one controller base
---------------------------------------------
.. automodule:: fuelweb_test.tests.test_ha_one_controller_base
   :members:

Test jumbo frames
-----------------
.. automodule:: fuelweb_test.tests.test_jumbo_frames
   :members:

Test Multiple Networks
----------------------
.. automodule:: fuelweb_test.tests.test_multiple_networks
   :members:

Test multirole group 1 (controller+ceph/compute+cinder and controller+ceph+cinder/compute+ceph+cinder)
------------------------------------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_multirole.test_multirole_group_1
   :members:

Test network templates base
---------------------------
.. automodule:: fuelweb_test.tests.test_net_templates_base
   :members:


Test network templates
----------------------
.. automodule:: fuelweb_test.tests.test_net_templates
   :members:

Test Neutron
------------
.. automodule:: fuelweb_test.tests.test_neutron
   :members:

Test Neutron Public
-------------------
.. automodule:: fuelweb_test.tests.test_neutron_public
   :members:

Test Neutron VXLAN
------------------
.. automodule:: fuelweb_test.tests.test_neutron_tun
   :members:

Test Neutron VXLAN base
-----------------------
.. automodule:: fuelweb_test.tests.test_neutron_tun_base
   :members:

Test Neutron IPv6 base functionality
------------------------------------
.. automodule:: fuelweb_test.tests.test_neutron_ipv6
   :members:

Test Node reinstallation
------------------------
.. automodule:: fuelweb_test.tests.test_node_reinstallation
   :members:

Test offloading types
---------------------
.. automodule:: fuelweb_test.tests.test_offloading_types
   :members:

Test Pull Requests
------------------
.. automodule:: fuelweb_test.tests.test_pullrequest
   :members:

Test Reduced Footprint
----------------------
.. automodule:: fuelweb_test.tests.test_reduced_footprint
   :members:

Test scale group 1 (add controllers with stop and add ceph nodes with stop)
---------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_1
   :members:

Test scale group 2 (replace primary controller and remove 2 controllers)
------------------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_2
   :members:

Test scale group 3 (add/delete compute and add/delete cinder)
-------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_3
   :members:

Test scale group 4 (add/delete ceph and add/delete cinder+ceph)
---------------------------------------------------------------
.. automodule:: fuelweb_test.tests.tests_scale.test_scale_group_4
   :members:

Test Services
-------------
.. automodule:: fuelweb_test.tests.test_services
   :members:

Test Ubuntu bootstrap
---------------------
.. automodule:: fuelweb_test.tests.test_ubuntu_bootstrap
   :members:

Test CentOS bootstrap
---------------------
.. automodule:: fuelweb_test.tests.test_centos_bootstrap
   :members:

Test Vcenter
------------
.. automodule:: fuelweb_test.tests.test_vcenter
   :members:

Test Ironic
-----------
.. automodule:: fuelweb_test.tests.test_ironic_base
  :members:

Test Services reconfiguration
-----------------------------
.. automodule:: fuelweb_test.tests.test_services_reconfiguration
  :members:

Test RH-based computes
----------------------
.. automodule:: fuelweb_test.tests.test_rh_compute
  :members:

Gating tests
============

Test Fuel agent
---------------
.. automodule:: gates_tests.tests.test_review_in_fuel_agent
  :members:

Test Fuel cli
-------------
.. automodule:: gates_tests.test_review_in_fuel_client
  :members:

Fuel mirror verification
========================

Tests to check that mirror is created in various scenarios
----------------------------------------------------------
Fuel create mirror is made to simplify process of mirror creation for our
customers who do not have internet access on-site. It is rewritten from bash
to python.

Fuel create mirror features:

1) Minimize size of packages in a mirror;

2) Download packages in parallel.

Such features can cause some problems:

1) During packages resolving to minimize mirror size we found such issues:

1.1) Incorrect versions. When we have multiple mirrors, some version can be
skipped due to name duplication. But it is still needed by bootstrap/deploy.

1.2) Mirror/version collisions. Sometimes package present in number of mirrors
and not always correct version corresponds to correct site.

1.3) There are special mirror on Fuel iso, which differs from
http://mirror.fuel-infra.org/ .

2) With concurrent packages fetching complications are:

2.1) Some mirrors are unable to support download in multiple threads and fail
or reject to support concurrency. In such cases we are abandoning concurrent
downloads on such mirrors.

2.2) Common concurrency pitfalls: race conditions for resources like lists to
process.

2.3) Problems with offset based downloads. Some packages were broken and it had
been found out only during package installation.

.. automodule:: fuelweb_test.tests.tests_mirrors.test_create_mirror
   :members:

Tests to verify installation from packages mirrors
--------------------------------------------------
After mirror is created we should be able to deploy environment with it.

Fuel-mirror updates default repo urls for deployment and we do not have to
set them up for new environments.But be careful. If you want to deploy
environments with vanilla mirrors from iso, You should update settings in
environment. Currently there is no option to update default mirrors from
UI/cli.

Fuel-mirror updates repo list with internal structures:
https://github.com/bgaifullin/packetary/blob/packetary3/contrib/fuel_mirror/fuel_mirror/commands/create.py#L224-L243

Repository should be able to do two things:

1) Create bootstrap iso for provisioning;

2) Provide packages for deployment. Packages from dependencies in http://mirror.fuel-infra.org/ do not cover all the needed packages.
So we need to mix in list of required packages:
https://github.com/bgaifullin/packetary/blob/packetary3/contrib/fuel_mirror/etc/config.yaml#L46-L96

Problems:

1) We need to install not only 'depends', but also 'recommends' packages:
https://wiki.ubuntu.com/LucidLynx/ReleaseNotes/#Recommended_packages_installed_by_default
http://askubuntu.com/questions/18545/installing-suggested-recommended-packages

2) We have a problem with support of a custom packages list.
It is only tracked via system test failure without exact team assigned for a
job. Also debootstrap and other tools are not informative about package errors.
It may fail with 'unable to mount', '/proc not mounted', 'file not found' even
if a problem is a missing package.

.. automodule:: fuelweb_test.tests.tests_mirrors.test_use_mirror
   :members:


GD based tests
==============

Test Neutron
------------
.. automodule:: fuelweb_test.tests.gd_based_tests.test_neutron
   :members:

Test Neutron Vlan Ceph Mongo
----------------------------
.. automodule:: fuelweb_test.tests.gd_based_tests.test_neutron_vlan_ceph_mongo
   :members:


Plugins tests
=============

Contrail tests
--------------
.. automodule:: fuelweb_test.tests.plugins.plugin_contrail.test_fuel_plugin_contrail
   :members:

Elasticsearch-Kibana tests
--------------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_elasticsearch.test_plugin_elasticsearch
   :members:

Emc tests
---------
.. automodule:: fuelweb_test.tests.plugins.plugin_emc.test_plugin_emc
   :members:

Example tests
-------------
.. automodule:: fuelweb_test.tests.plugins.plugin_example.test_fuel_plugin_example
   :members:

Example tests for plugin installation after cluster create
----------------------------------------------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_example.test_fuel_plugin_example_postdeploy
   :members:

Glusterfs tests
---------------
.. automodule:: fuelweb_test.tests.plugins.plugin_glusterfs.test_plugin_glusterfs
   :members:

InfluxDB-Grafana tests
----------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_influxdb.test_plugin_influxdb
   :members:

Lbaas tests
-----------
.. automodule:: fuelweb_test.tests.plugins.plugin_lbaas.test_plugin_lbaas
   :members:

LMA collector tests
-------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_lma_collector.test_plugin_lma_collector
   :members:

LMA infrastructure alerting tests
---------------------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_lma_infra_alerting.test_plugin_lma_infra_alerting
   :members:

Reboot tests
------------
.. automodule:: fuelweb_test.tests.plugins.plugin_reboot.test_plugin_reboot_task
   :members:

Vip reservation tests
---------------------
.. automodule:: fuelweb_test.tests.plugins.plugin_vip_reservation.test_plugin_vip_reservation
   :members:

Zabbix tests
------------
.. automodule:: fuelweb_test.tests.plugins.plugin_zabbix.test_plugin_zabbix
   :members:

Patching tests
==============

Patching tests
--------------
.. automodule:: fuelweb_test.tests.tests_patching.test_patching
   :members:


Security tests
==============

Nessus scan tests
-----------------
.. automodule:: fuelweb_test.tests.tests_security_test_run_nessus
   :members:


Strength tests
==============

Cic maintenance mode tests
--------------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_cic_maintenance_mode
   :members:

Failover tests
--------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover
   :members:

Base failover tests
-------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover_base
   :members:

Failover with CEPH tests
------------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_failover_with_ceph
   :members:

Huge environments tests
-----------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_huge_environments
   :members:

Image based tests
-----------------
.. automodule:: fuelweb_test.tests.tests_strength.test_image_based
   :members:

Load tests
----------
.. automodule:: fuelweb_test.tests.tests_strength.test_load
   :members:

Master node failover tests
--------------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_master_node_failover
   :members:

Neutron tests
-------------
.. automodule:: fuelweb_test.tests.tests_strength.test_neutron
   :members:

Base Neutron tests
------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_neutron_base
   :members:

OSTF repeatable tests
---------------------
.. automodule:: fuelweb_test.tests.tests_strength.test_ostf_repeatable_tests
   :members:

Restart tests
-------------
.. automodule:: fuelweb_test.tests.tests_strength.test_restart
   :members:

Upgrade tests
=============

Test Data-Driven Upgrade
------------------------
.. automodule:: fuelweb_test.tests.tests_upgrade.test_clone_env
.. automodule:: fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_base
.. automodule:: fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade
.. automodule:: fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_ceph_ha
.. automodule:: fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_net_tmpl
.. automodule:: fuelweb_test.tests.tests_upgrade.test_data_driven_upgrade_plugin
.. automodule:: fuelweb_test.tests.tests_upgrade.test_node_reassignment
.. automodule:: fuelweb_test.tests.tests_upgrade.upgrader_tool
   :members:

OS upgrade tests
================

Test OpenStack Upgrades
-----------------------
.. automodule:: fuelweb_test.tests.tests_upgrade.upgrade_base
   :members:

.. automodule:: fuelweb_test.tests.tests_upgrade.test_os_upgrade
   :members:

Tests for separated services
============================

Test for separate keystone service
----------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_keystone
   :members:

Test for separate keystone service and ceph
-------------------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_keystone_ceph
   :members:

Test for separate horizon service
---------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_horizon
   :members:

Test for separate mysql service
-------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_db
   :members:

Test for separate mysql service and ceph
----------------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_db_ceph
   :members:

Test for separate multiroles
----------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_multiroles
   :members:

Test for separate rabbitmq service
----------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_rabbitmq
   :members:

Test for separate rabbitmq service and ceph
-------------------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_rabbitmq_ceph
   :members:

Deployment with platform components
-----------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_deploy_platform_components
   :members:

Template based tests
--------------------
.. automodule:: fuelweb_test.actions_tests
