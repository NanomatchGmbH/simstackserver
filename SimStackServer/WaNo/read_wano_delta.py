import json
import pathlib


def read_wano_delta(configuration_path: pathlib.Path):
    with configuration_path.open("rt") as infile:
        outdict = json.load(infile)
    return outdict

