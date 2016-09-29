.. index:: System tests

System tests
************

Core
====

Repository
----------
.. automodule:: system_test.core.repository
   :members:

Discover
--------
.. automodule:: system_test.core.discover
   :members:

Decorators
----------
.. automodule:: system_test.core.decorators
   :members:

Factory
-------
.. automodule:: system_test.core.factory
   :members:

Config
------
.. automodule:: system_test.core.config
   :members:

Actions
=======

Base actions
------------
.. automodule:: system_test.actions.base
   :members:

Fuelmaster actions
------------------
.. automodule:: system_test.actions.fuelmaster_actions
   :members:

OSTF actions
------------
.. automodule:: system_test.actions.ostf_actions
   :members:

Plugins actions
---------------
.. automodule:: system_test.actions.plugins_actions
   :members:

Strength actions
----------------
.. automodule:: system_test.actions.strength_actions
   :members:

VCenter actions
---------------
.. automodule:: system_test.actions.vcenter_actions
   :members:

General tests
=============

Release tests
-------------
.. automodule:: system_test.tests.test_releases
   :members:

ActionTest
----------
.. automodule:: system_test.tests.base
   :members:

Case deploy Environment
-----------------------
.. automodule:: system_test.tests.test_create_deploy_ostf
   :members:

Deploy cluster and check RadosGW
--------------------------------
.. automodule:: system_test.tests.test_deploy_check_rados
   :members:

Delete cluster after deploy
---------------------------
.. automodule:: system_test.tests.test_delete_after_deploy
   :members:

Redeploy cluster after stop
---------------------------
.. automodule:: system_test.tests.test_redeploy_after_stop
   :members:

Redeploy cluster after reset
----------------------------
.. automodule:: system_test.tests.test_redeploy_after_reset
   :members:

Fuel master migration
---------------------
.. automodule:: system_test.tests.test_fuel_migration
   :members:

Strength tests
==============

Destroy controllers
-------------------
.. automodule:: system_test.tests.strength.test_destroy_controllers
   :members:

Fill root and check pacemaker
-----------------------------
.. automodule:: system_test.tests.strength.test_filling_root
   :members:

Plugin tests
============

Example plugin Base
-------------------
.. automodule:: system_test.tests.plugins.plugin_example
    :members:

Example plugin
--------------
.. automodule:: system_test.tests.plugins.plugin_example.test_plugin_example
    :members:

Example plugin v3
-----------------
.. automodule:: system_test.tests.plugins.plugin_example.test_plugin_example_v3
    :members:

vCenter tests
=============

vCenter/DVS
-----------
.. automodule:: system_test.tests.vcenter.test_vcenter_dvs
    :members:

vCenter/DVS failover
--------------------
.. automodule:: system_test.tests.vcenter.test_vcenter_failover
    :members:

vCenter/DVS cluster actions
---------------------------
.. automodule:: system_test.tests.vcenter.test_vcenter_cluster_actions
    :members:

Helpers
=======

Decorators
----------
.. automodule:: system_test.helpers.decorators
   :members:
