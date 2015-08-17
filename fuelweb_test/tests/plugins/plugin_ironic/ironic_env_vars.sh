#!/usr/bin/env bash
export NODES_COUNT=4
export ENV_NAME=yyekovenko-ironic5
export VENV_PATH=/home/yyekovenko/venv/fuelweb_test
export IRONIC_PLUGIN_PATH=/home/yyekovenko/ironic_resources/fuel-plugin-ironic-1.0-1.0.0-1.noarch.rpm
export ISO_PATH=/home/yyekovenko/ironic_resources/fuel-7.0-248-2015-08-28_10-26-09.iso
export UBUNTU_IMAGE_PATH=/home/yyekovenko/ironic_resources/trusty-server-cloudimg-amd64.img

export BAREMETAL_NET='10.109.47.1/24'

export IRONIC_VM_MAC='64:49:29:47:d9:a6'
export IRONIC_VM2_MAC='64:a7:a3:c1:74:26'
export HW_SERVER_IP=172.18.170.7
export HW_SSH_USER=ironic
export HW_SSH_PASS=ironic_password

export IRONIC_BM_MAC='00:25:90:7f:79:60'
export IPMI_SERVER_IP=185.8.58.246
export IPMI_USER=engineer
export IPMI_PASS=09ejm7HGViwbg