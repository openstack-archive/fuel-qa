#!/bin/sh
set -ex
PATCH_DIR=$1
shift

show_only_unmerged() {
  xargs -tI% sh -c 'curl -s "https://review.openstack.org/changes/%/detail?O=2002" | grep -q "\"status\": \"MERGED\"" && (echo http://review.openstack.org/% MERGED > /dev/stderr) || echo %'
}

show_only_unapplied() {
  xargs -tI% sh -c 'curl -s "https://review.openstack.org/changes/%/detail?O=2002" | sed -nE "/current_revision/ {s/[ ]+?.current_revision.: .//;s/.,\$//p;q}" | xargs -tI{} sh -c "curl -s https://review.openstack.org/changes/%/revisions/{}/patch?download | base64 -d | patch -N --follow-symlinks --batch -p2 --silent --dry-run 2>&1 >/dev/null && echo % || (echo http://review.openstack.org/% cant be applied > /dev/stderr)"'
}

cr_filter() {
  grep -oE '[0-9]+?'
}



apply_patches() {
  cd $1
  shift
  cr_filter | xargs -tI% sh -c 'curl -s "https://review.openstack.org/changes/%/detail?O=2002" | sed -nE "/current_revision/ {s/[ ]+?.current_revision.: .//;s/.,\$//p;q}" | xargs -tI{} sh -c "curl -s https://review.openstack.org/changes/%/revisions/{}/patch?download | base64 -d | patch --batch -p2 && echo http://review.openstack.org/% successfully"'
}

test $# -ge 1 && echo $* | apply_patches ${PATCH_DIR}
