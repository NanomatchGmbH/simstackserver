"""
Calculations provided by wano_calcjob.

Register calculations via the "aiida.calculations" entry point in setup.json.
"""

from aiida.plugins import DataFactory
from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob

from TreeWalker.TreeWalker import TreeWalker

WaNoParameters = DataFactory('wano')

def rewrite_path(inpath):
    outpath = [WaNoCalcJob.clean_path(mypath) for mypath in inpath]
    return outpath

def clean_dict_for_aiida(input_dictionary):
    tw = TreeWalker(input_dictionary)
    visitor_functions = {
        "path_visitor_function":None,
        "path_rewrite_function": WaNoCalcJob.clean_path,
        "subdict_visitor_function": None,
        "data_visitor_function": None
    }
    output_dictionary = tw.walker_from_dict(visitor_functions, capture=True)
    return output_dictionary

class DepositCalcJob(WaNoCalcJob):
    _myxml = "/home/strunk/nanomatch/git/SimStackServer/SimStackServer/wano_calcjob/tests/inputs/wanos/Deposit/Deposit3.xml"

