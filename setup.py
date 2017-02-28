#!/usr/bin/env python
from setuptools import setup, find_packages

__doc__="""
URL Resolver Field for Django
"""

version = '0.0.1'

setup(
    name='django-urlresolverfield',
    version=version,
    description='URL Resolver Field for Django',
    author='Fusionbox programmers',
    author_email='programmers@fusionbox.com',
    long_description=__doc__,
    url='https://github.com/fusionbox/django-urlresolverfield',
    packages=find_packages(),
    package_data={},
    namespace_packages=[],
    platforms='any',
    license='BSD',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
    ],
)
