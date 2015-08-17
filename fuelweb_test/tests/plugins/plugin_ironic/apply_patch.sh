# run commands on master node:
sudo apt-get install git
git clone https://github.com/stackforge/fuel-web.git
cd fuel-web/
git fetch https://review.openstack.org/stackforge/fuel-web refs/changes/49/211349/10 && git checkout FETCH_HEAD
dockerctl copy nailgun/nailgun/consts.py nailgun:/usr/lib/python2.6/site-packages/nailgun/consts.py
dockerctl copy nailgun/nailgun/orchestrator/neutron_serializers.py nailgun:/usr/lib/python2.6/site-packages/nailgun/orchestrator/neutron_serializers.py
dockerctl restart nailgun