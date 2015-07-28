#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os

from OpenSSL import crypto

from fuelweb_test import logger
from fuelweb_test import logwrap

from fuelweb_test.settings import DISABLE_SSL
from fuelweb_test.settings import PATH_TO_CERT
from fuelweb_test.settings import PATH_TO_PEM
from fuelweb_test.settings import USER_OWNED_CERT


@logwrap
def generate_user_own_cert(cn, path_to_cert=PATH_TO_CERT,
                           path_to_pem=PATH_TO_PEM):
    logger.debug("Trying to generate user certificate files")
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)
    cert = crypto.X509()
    cert.get_subject().OU = 'Mirantis Fuel-QA Team'
    cert.get_subject().CN = cn
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(315360000)
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha1')
    with open(path_to_pem, 'wt') as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    logger.debug("Generated PEM file {}".format(path_to_pem))
    with open(path_to_cert, 'wt') as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    logger.debug("Generated PEM file {}".format(path_to_cert))


@logwrap
def change_cluster_ssl_config(attributes, CN):
    logger.debug("Trying to change cluster {} ssl configuration")
    is_ssl_available = attributes['editable'].get('public_ssl', None)
    if DISABLE_SSL and is_ssl_available:
        attributes['editable']['public_ssl']['services'][
            'value'] = False
        attributes['editable']['public_ssl']['horizon'][
            'value'] = False
    elif not DISABLE_SSL and is_ssl_available:
        attributes['editable']['public_ssl']['hostname'][
            'value'] = CN
        if USER_OWNED_CERT:
            generate_user_own_cert(CN)
            attributes['editable']['public_ssl'][
                'cert_source']['value'] = 'user_uploaded'
            cert_data = {}
            with open(PATH_TO_PEM, 'r') as f:
                cert_data['content'] = f.read()
            cert_data['name'] = os.path.basename(PATH_TO_PEM)
            attributes['editable']['public_ssl'][
                'cert_data']['value'] = cert_data


@logwrap
def copy_cert_from_master(admin_remote, cluster_id,
                          path_to_store=PATH_TO_CERT):
    path_to_cert = \
        '/var/lib/fuel/keys/{}/haproxy/public_haproxy.crt'.format(
            cluster_id)
    admin_remote.download(path_to_cert, path_to_store)
    logger.debug("Copied cert from admin node to the {}".format(
        path_to_store))
