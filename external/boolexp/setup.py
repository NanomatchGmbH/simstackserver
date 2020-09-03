#!/usr/bin/env python
from distutils.core import setup
import os

try:
    p = os.popen('pandoc -f markdown -t rst README.md | sed \'{s/^\\s*#!\\(.*\\)/.. code-block:: \\1\\n/; s/^:://g}\'')
    long_descr = ''.join(p.readlines())
except:
    long_descr = ''

setup(
    name="boolexp",
    version="0.1",
    description='Safe boolean expression evaluator',
    author='Peter Facka',
    url='https://bitbucket.org/pfacka/boolexp',
    author_email='pfacka@binaryparadise.com',
    keywords='boolean expression BNF safe evaluation',
    license='MIT Licence (http://opensource.org/licenses/MIT)',
    packages=[
        'boolexp',
    ],
    requires=[
        'pyparsing(>=1.5.0)',
    ],
    provides=['boolexp (0.1)'],
    classifiers=[
      'Development Status :: 3 - Alpha',
      'Environment :: Web Environment',
      'Intended Audience :: Developers',
      'Operating System :: Microsoft :: Windows',
      'Operating System :: MacOS :: MacOS X',
      'Operating System :: POSIX',
      'Programming Language :: Python :: 2.7',
      'Programming Language :: Python :: 3',
      'License :: OSI Approved :: MIT License',
      ],
)
