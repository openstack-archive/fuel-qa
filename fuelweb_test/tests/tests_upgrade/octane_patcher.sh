#!/bin/sh
set -e
cd /usr/lib/python*/site-packages/octane
echo -n $* | xargs -d" " -tI% sh -c 'curl -s "https://review.openstack.org/changes/%/detail?O=2002" | grep current_revision | cut -d: -f2 | sed "s/[, ]//g" | xargs -tI{} sh -c "curl -s https://review.openstack.org/changes/%/revisions/{}/patch?download | base64 -d | patch -p2"'