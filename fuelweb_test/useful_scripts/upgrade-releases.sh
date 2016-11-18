#/bin/bash
set -o xtrace
set -o errexit

update_releases=$(mktemp)
cat << EOF > ${update_releases}
update releases set "attributes_metadata" =
  replace("attributes_metadata", 'lts-trusty', 'lts-xenial')
  where name like '%Ubuntu%14.04%';
update releases set "attributes_metadata" =
  replace("attributes_metadata", 'hpsa-dkms\n', '')
  where name like '%Ubuntu%14.04%';
EOF
cat ${update_releases} | su postgres -c 'psql nailgun'
rm ${update_releases}