"""
Calculations provided by wano_calcjob.
"""

from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob
from os.path import join

from wano_calcjob.WaNoCalcJobParserBase import WaNoCalcJobParser


class DepositCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "Deposit3", "Deposit3.xml")

class DepositParser(WaNoCalcJobParser):
    _calcJobClass = DepositCalcJob