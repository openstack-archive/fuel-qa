#!/bin/bash
source /root/openrc;
​
image_ids_count=$1
volume_ids_count=$2
total_count=$(($image_ids_count+$volume_ids_count))
​
net_id=`nova net-list | awk '/net04\ / {print $2}'`;
flavor_id=`nova flavor-list | awk '/m1.micro/ {print $2}'`;
image_id=`nova image-list | awk '/TestVM/ {print $2}'`;
​
seq 1 $total_count | xargs -I {} nova floating-ip-create
seq 1 $volume_ids_count | xargs -I {} cinder create --image-id $image_id --display_name=bootable_volume_{} 1
​
for id in `seq 1 $image_ids_count`
do
    nova boot --image $image_id --flavor $flavor_id --nic net-id=$net_id test_boot_image_$id;
done
​
​
for id in `seq 1 $volume_ids_count`
do
    volume_id=`nova volume-list | awk '/available/ && $14 == "" {print $2}' | awk 'NR==1'`;
    nova boot --block-device source=volume,id=$volume_id,dest=volume,size=10,shutdown=preserve,bootindex=0 --flavor $flavor_id --nic net-id=$net_id test_boot_volume_$id;
done
​
for i in `seq 1 120`
do
​
    non_active_inastance_count=`nova list | awk '!/ACTIVE/&&/test_/' | wc -l`
    if ((non_active_inastance_count==0))
    then break;
    else
        echo "$non_active_inastance_count instances still not active"
        sleep 5;
​
    fi
done
​
for node_name in `nova list | awk '/ACTIVE/&&/test_/ {print $4}'`
do
    floating_id=`nova floating-ip-list | awk '$6 == "-" {print $4}'| awk 'NR==1'`;
    nova add-floating-ip $node_name $floating_id;
done
​
for sec_group in `neutron security-group-list | awk '/default/ {print $2}'`
do
    neutron security-group-rule-create --protocol tcp --port-range-min 22  --port-range-max 22 --direction ingress $sec_group;
    neutron security-group-rule-create --protocol icmp --direction ingress $sec_group;
done