#!/usr/bin/env python3
from __future__ import print_function
import sys
import yaml

with open(sys.argv[1],'r') as infile:
    fileone = yaml.load(infile)

with open(sys.argv[1],'w') as outfile:
    outfile.write(yaml.dump(fileone,default_flow_style=None))
