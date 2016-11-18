#!/bin/bash
set -o errexit
set -o xtrace

for f in /usr/share/fuel-openstack-metadata/openstack.yaml \
    /usr/lib/python2.7/site-packages/fuel_agent/drivers/nailgun.py \
    /usr/lib/python2.7/site-packages/nailgun/fixtures/openstack.yaml; do
  sed -i -e 's/generic-lts-trusty/generic-lts-xenial/g' \
    -e '/^\([[:blank:]]*\)\("*\)hpsa-dkms/d' ${f}
done

echo "Done"