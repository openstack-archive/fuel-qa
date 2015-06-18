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

project = 'Fuel QA'
source_suffix = '.rst'
master_doc = 'index'

pygments_style = 'sphinx'
templates_path = ['_templates']
html_theme = 'mirantis'
htmlhelp_basename = 'fuel-qadoc'
html_favicon = '_static/favicon.ico'

html_theme_path = ['_templates']
html_static_path = ['_static']
htmlhelp_basename = 'fueldoc'
html_use_smartypants = False
html_use_index = True
html_split_index = False
html_show_sourcelink = False
html_show_sphinx = False
html_show_copyright = True

html_theme_options = {
    'navbar_title': "Documentation",
    'navbar_site_name': "Modules",
    'navbar_sidebarrel': True,
    'navbar_pagenav': True,
    'navbar_pagenav_name': "Section",
    'globaltoc_depth': 2,
    'globaltoc_includehidden': "true",
    'navbar_class': "navbar",
    'navbar_fixed_top': "true",
    'source_link_position': "nav",
    'bootswatch_theme': "yeti",
    'bootstrap_version': "3",
}

autodoc_default_flags = ['members', 'show-inheritance', 'inherited-members']
autodoc_member_order = 'bysource'
copyright = 'Copyright 2015 Mirantis, Inc.' \
            'Licensed under the Apache License, Version 2.0' \
            ' (the "License"); you may not use this file except in' \
            ' compliance with the License. You may obtain a copy' \
            ' of the License at http://www.apache.org/licenses/LICENSE-2.0'

exclude_patterns = ['_build']

intersphinx_mapping = {'http://docs.python.org/': None}
