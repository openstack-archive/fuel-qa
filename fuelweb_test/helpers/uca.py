#    Copyright 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from proboscis import asserts

from fuelweb_test import settings


def change_cluster_uca_config(cluster_attributes):
    'Returns cluster attributes with UCA repo configuration.'

    # check attributes have uca options

    for option in ["pin_haproxy", "pin_rabbitmq", "pin_ceph"]:
        asserts.assert_true(
            option in cluster_attributes["editable"]["repo_setup"],
            "{0} is not in cluster attributes: {1}".
            format(option, str(cluster_attributes["editable"]["repo_setup"])))

    # enable UCA repository

    uca_options = cluster_attributes["editable"]["repo_setup"]
    uca_options["pin_haproxy"]["value"] = settings.UCA_PIN_HAPROXY
    uca_options["pin_rabbitmq"]["value"] = settings.UCA_PIN_RABBITMQ
    uca_options["pin_ceph"]["value"] = settings.UCA_PIN_RABBITMQ

    return cluster_attributes
