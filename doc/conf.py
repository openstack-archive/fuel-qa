# -*- coding: utf-8 -*-
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
import sys

sys.path.insert(0,
                os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
]

autodoc_default_flags = ['members', 'show-inheritance', 'inherited-members']
autodoc_member_order = 'bysource'

source_suffix = '.rst'

master_doc = 'index'

project = 'Fuel QA'
copyright = 'Copyright 2015 Mirantis, Inc.' \
            'Licensed under the Apache License, Version 2.0' \
            ' (the "License"); you may not use this file except in' \
            ' compliance with the License. You may obtain a copy' \
            ' of the License at http://www.apache.org/licenses/LICENSE-2.0'

exclude_patterns = ['_build']

pygments_style = 'sphinx'

html_theme = 'sphinxdoc'
htmlhelp_basename = 'fuel-qadoc'

intersphinx_mapping = {'http://docs.python.org/': None}
