.. index:: Base tests

General Openstack/Fuel Tests
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

Test Clone Environment
----------------------
.. automodule:: fuelweb_test.tests.test_clone_env
   :members:

Test custom hostname
--------------------
.. automodule:: fuelweb_test.tests.test_custom_hostname
   :members:

Test Environment Action
-----------------------
.. automodule:: fuelweb_test.tests.test_environment_action
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

Test Node reinstallation
------------------------
.. automodule:: fuelweb_test.tests.test_node_reinstallation
   :members:

Test Node reassignment
----------------------
.. automodule:: fuelweb_test.tests.test_node_reassignment
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

Test Services
-------------
.. automodule:: fuelweb_test.tests.test_services
   :members:

Test Ubuntu bootstrap
---------------------
.. automodule:: fuelweb_test.tests.test_ubuntu_bootstrap
   :members:

Test Vcenter
------------
.. automodule:: fuelweb_test.tests.test_vcenter
   :members:

Test Zabbix
-----------
.. automodule:: fuelweb_test.tests.test_zabbix
   :members:

Test Ironic
-----------
.. automodule:: fuelweb_test.tests.test_ironic_base
  :members:


Fuel mirror verification
========================

Tests to check that mirror is created in various scenarios
----------------------------------------------------------
Утилита сделана так чтобы ускорить процесс создания зеркал и минимизировать расходы свободного места.
Это достигается двумя действиями:
1) что минимизировано число пакетов и не делается полная копия зеркала
2) скачивание идёт в несколько потоков
Проблемы могут возникнуть с resolve-ингом и с обработкой в несколько потоков:
1) При создании копии зеркала были найдены следующие проблемы с резолвингом пакетов:
1.1) Некорректные обработки версий пакетов.
1.2) Неправильные указания основ для зеркалирования. Необходимо следить за совпадением версий и компонентов зеркал.
1.3) На master есть своё особое зекрало, которое отличается от http://mirror.fuel-infra.org/
2) При работе в несколько потоков были найдены проблемы с:
2.1) Некоторые зеркала не справляются с загрузкой в несколько потоков и необходимо занижать параметры по-умолчанию по количеству потоков.
2.2) Общие проблемы с многопоточностью - борьба за общие ресурсы (списки для обработки). Возможные проблемы - отсутствие данных в конечном репозитории при доступности их в исходных данных.
2.3) Проблемы с закачкой по offset-ам. Получались битые пакеты.

.. automodule:: fuelweb_test.tests.tests_mirrors.test_create_mirror
   :members:

Tests to verify installation from packages mirrors
--------------------------------------------------
During tests we found such caveats:
Репозиторий должен служить двум целям. Во-первых - это создание bootstrap образа
для убунты, второе - набор пакетов, необходимых для установки openstack, вспомогательных систем и
административных утилит.
Для этого зеркала должны отображать сразу два набора пакетов - первый это набор пакетов для
установки системы
Есть дополнительная задача для зеркала - быть provider-ом fuel пакетов на мастер ноду. Она сейчас
решается через https://github.com/openstack/fuel-main/tree/master/packages и
https://github.com/openstack/fuel-main/tree/master/mirror . Это зеркало, как правило, устанавливается без проблем
и позволяет ставить большинство нужных пакетов на мастер ноде для работы с fuel.

Проблемы:
1) Необходимо устанавливать пакеты не только depends, но и recommends
https://wiki.ubuntu.com/LucidLynx/ReleaseNotes/#Recommended_packages_installed_by_default
http://askubuntu.com/questions/18545/installing-suggested-recommended-packages
2) Для сборки системы необходимо не только зеркало пакетов, недоступных как dependencies для mirror.fuel-infra.org,
но и набор required.
3) Для установки openstack необходимо не только зеркало пакетов, недоступных как dependencies для mirror.fuel-infra,
но и пакеты, устанавливаемые puppet-ом. Например - утилиты администратора как tmux, screen, htop, iotop.
Нормально что эти утилиты не выводятся по dependencies из множества пакетов openstack, но при этом
используются для установки и поддержки openstack.
Для этого в процессе работы был найден список файлов, достаточный для deploymenta openstack.
https://github.com/bgaifullin/packetary/blob/packetary3/contrib/fuel_mirror/etc/config.yaml#L47-L96
Проблема поддержки этого файла в том что его генерация не автоматизированна и отлавливать проблемы
нужно будет на основе падений интеграционных тестов с отлавливанием сообщений о недостаточности пакетов.
Вдвойне неудобно искать информацию о падении пакетов на этапе создания образа так как утилита debootstrap
выдаёт обрывочные сообщения, которые нужно исследовать а не просто сообщения в формате "пакет не установлен".

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

Test Upgrade
------------
.. automodule:: fuelweb_test.tests.tests_upgrade.test_upgrade
   :members:

Test Upgrade Chains
-------------------
.. automodule:: fuelweb_test.tests.tests_upgrade.test_upgrade_chains
   :members:

OS upgrade tests
================

Test Openstack Upgrades
-----------------------
.. automodule:: fuelweb_test.tests.test_os_upgrade
   :members:

Tests for separated services
============================

Test for separate keystone service
----------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_keystone
   :members:

Test for separate horizon service
---------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_horizon
   :members:

Test for separate mysql service
-------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_db
   :members:

Test for separate multiroles
----------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_multiroles
   :members:

Test for separate rabbitmq service
----------------------------------
.. automodule:: fuelweb_test.tests.tests_separate_services.test_separate_rabbitmq
   :members:

Template based tests
--------------------
.. automodule:: fuelweb_test.actions_tests
