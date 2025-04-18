#!/usr/bin/env python3
import sys
import yaml
from yaml import CLoader

with open(sys.argv[1], "r") as infile:
    fileone = yaml.load(infile, Loader=CLoader)

with open(sys.argv[1], "w") as outfile:
    outfile.write(yaml.dump(fileone, default_flow_style=None))
