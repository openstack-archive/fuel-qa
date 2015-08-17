#!/usr/bin/env bash
export NODES_COUNT=5
export ENV_NAME=yyekovenko-ironic3
export VENV_PATH=/home/yyekovenko/venv/fuelweb_test
export IRONIC_PLUGIN_PATH=/home/yyekovenko/ironic_resources/fuel-plugin-ironic-1.0-1.0.0-1.noarch.rpm
export ISO_PATH=/home/yyekovenko/ironic_resources/fuel-7.0-248-2015-08-28_10-26-09.iso
export UBUNTU_IMAGE_PATH=/home/yyekovenko/ironic_resources/trusty-server-cloudimg-amd64.img

export BAREMETAL_NET='10.109.8.0/24'

export IRONIC_VM_MAC='52:54:00:86:f4:56'

export VM_SERVER_IP=172.18.170.7
export LDAP_USER=<USER>
export LDAP_PASSWORD=<PWD>
