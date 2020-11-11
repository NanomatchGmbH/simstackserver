"""
Calculations provided by wano_calcjob.
"""

from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob
from os.path import join

from wano_calcjob.WaNoCalcJobParserBase import WaNoCalcJobParser

class lightforge2CalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "lightforge2", "lightforge2.xml")
    _parser_name = "lightforge2"
class lightforge2Parser(WaNoCalcJobParser):
    _calcJobClass = lightforge2CalcJob

class IntraOverlapCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "IntraOverlap", "IntraOverlap.xml")
    _parser_name = "IntraOverlap"
class IntraOverlapParser(WaNoCalcJobParser):
    _calcJobClass = IntraOverlapCalcJob

class ExcitonPreProcessorCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "ExcitonPreProcessor", "ExcitonPreProcessor.xml")
    _parser_name = "ExcitonPreProcessor"
class ExcitonPreProcessorParser(WaNoCalcJobParser):
    _calcJobClass = ExcitonPreProcessorCalcJob

class DihedralParametrizer2CalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "DihedralParametrizer2", "DihedralParametrizer2.xml")
    _parser_name = "DihedralParametrizer2"
class DihedralParametrizer2Parser(WaNoCalcJobParser):
    _calcJobClass = DihedralParametrizer2CalcJob

class StokesShiftAnalysisCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "StokesShiftAnalysis", "StokesShiftAnalysis.xml")
    _parser_name = "StokesShiftAnalysis"
class StokesShiftAnalysisParser(WaNoCalcJobParser):
    _calcJobClass = StokesShiftAnalysisCalcJob

class Deposit3CalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "Deposit3", "Deposit3.xml")
    _parser_name = "Deposit3"
class Deposit3Parser(WaNoCalcJobParser):
    _calcJobClass = Deposit3CalcJob

class EmissionCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "Emission", "Emission.xml")
    _parser_name = "Emission"
class EmissionParser(WaNoCalcJobParser):
    _calcJobClass = EmissionCalcJob

class lightforge2_analysisCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "lightforge2_analysis", "lightforge2_analysis.xml")
    _parser_name = "lightforge2_analysis"
class lightforge2_analysisParser(WaNoCalcJobParser):
    _calcJobClass = lightforge2_analysisCalcJob

class ScriptCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "Script", "Script.xml")
    _parser_name = "Script"
class ScriptParser(WaNoCalcJobParser):
    _calcJobClass = ScriptCalcJob

class TCADCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "TCAD", "TCAD.xml")
    _parser_name = "TCAD"
class TCADParser(WaNoCalcJobParser):
    _calcJobClass = TCADCalcJob

class OrientationAnalysisCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "OrientationAnalysis", "OrientationAnalysis.xml")
    _parser_name = "OrientationAnalysis"
class OrientationAnalysisParser(WaNoCalcJobParser):
    _calcJobClass = OrientationAnalysisCalcJob

class ExtendJsCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "ExtendJs", "ExtendJs.xml")
    _parser_name = "ExtendJs"
class ExtendJsParser(WaNoCalcJobParser):
    _calcJobClass = ExtendJsCalcJob

class QuantumPatch3CalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "QuantumPatch3", "QuantumPatch3.xml")
    _parser_name = "QuantumPatch3"
class QuantumPatch3Parser(WaNoCalcJobParser):
    _calcJobClass = QuantumPatch3CalcJob

class GSPAnalysisCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "GSPAnalysis", "GSPAnalysis.xml")
    _parser_name = "GSPAnalysis"
class GSPAnalysisParser(WaNoCalcJobParser):
    _calcJobClass = GSPAnalysisCalcJob

class Parametrizer3CalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "Parametrizer3", "Parametrizer3.xml")
    _parser_name = "Parametrizer3"
class Parametrizer3Parser(WaNoCalcJobParser):
    _calcJobClass = Parametrizer3CalcJob

class VariableExporterCalcJob(WaNoCalcJob):
    _myxml = join(WaNoCalcJob.wano_repo_path(), "VariableExporter", "VariableExporter.xml")
    _parser_name = "VariableExporter"
class VariableExporterParser(WaNoCalcJobParser):
    _calcJobClass = VariableExporterCalcJob

