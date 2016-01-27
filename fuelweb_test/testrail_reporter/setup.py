#!/usr/bin/env python

from setuptools import setup, find_packages


setup(
    name='testrail_reporter',
    packages=find_packages(),
    scripts=['bin/report'],
    install_requires=[
        'requests',
        'pytest-runner',
        'xunitparser',
        'metayaml',
    ],
)
