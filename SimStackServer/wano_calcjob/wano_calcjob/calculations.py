"""
Calculations provided by wano_calcjob.

Register calculations via the "aiida.calculations" entry point in setup.json.
"""
import os

from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import SinglefileData
from aiida import orm
from aiida.parsers import Parser
from aiida.plugins import DataFactory
from lxml import etree

from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

WaNoParameters = DataFactory('wano')


class WaNoCalcJob(CalcJob):
    """
    AiiDA calculation plugin wrapping the diff executable.

    Simple AiiDA plugin wrapper for 'diffing' two files.
    """
    typemap = {
        "Float": orm.Float,
        "Boolean": orm.Bool,
        "String": orm.Str,
        "Int": orm.Int,
        "File": orm.SinglefileData
    }

    @classmethod
    def define(cls, spec):
        """Define inputs and outputs of the calculation."""
        # yapf: disable
        super(WaNoCalcJob, cls).define(spec)
        myxml = "/home/strunk/nanomatch/git/SimStackServer/SimStackServer/wano_calcjob/tests/inputs/wanos/Deposit/Deposit3.xml"
        cls._build_spec_from_wano(wfxml=myxml, spec=spec)

        # set default values for AiiDA options
        spec.inputs['metadata']['options']['resources'].default = {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 1,
                }
        spec.inputs['metadata']['options']['parser_name'].default = 'wano'

        # new ports
        spec.input('metadata.options.output_filename', valid_type=str, default='patch.diff')

        spec.input('parameters', valid_type=WaNoParameters, help='Command line parameters for diff')
        #spec.input('abc.robot.yyy.ge',valid_type=orm.Float, default='mine')
        #spec.input('humbo',valid_type=orm.Float)
        spec.input_namespace('harbl.my.garbl.mod.prop')
        spec.input('harbl.my.garbl.mod.prop.humbo', valid_type=orm.Float)


        spec.input('file1', valid_type=SinglefileData, help='First file to be compared.')
        spec.input('file2', valid_type=SinglefileData, help='Second file to be compared.')
        spec.output('wano', valid_type=SinglefileData, help='diff between file1 and file2.')

        spec.exit_code(100, 'ERROR_MISSING_OUTPUT_FILES', message='Calculation did not produce all expected output files.')

    @classmethod
    def _build_spec_from_wano(cls, wfxml, spec):
        wmr = cls._parse_wano_xml(wfxml)
        namespaces, vars = cls._wano_to_namespaces_and_vars(wmr)
        for namespace in namespaces:
            spec.input_namespace(namespace, dynamic=True)
        for path, vartype in vars.items():
            spec.input(path, valid_type=cls.typemap[vartype], required = False)

        wmr:WaNoModelRoot
        outputfiles = wmr.get_output_files(only_static=True)
        spec.output_namespace("files")
        for myfile in outputfiles:
            spec.output("files.%s"%myfile, valid_type=SinglefileData)

        exec_command = wmr.exec_command
        spec.input('metadata.options.exec_command', valid_type = str, default = exec_command)


    @classmethod
    def _parse_wano_xml(cls, wfxml):
        from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
        with open(wfxml, 'rt') as infile:
            xml = etree.parse(infile)
        wano_dir_root = os.path.dirname(wfxml)
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
        wmr = WaNoModelRoot(wano_dir_root = wano_dir_root, model_only = True)
        wmr.parse_from_xml(xml)
        wmr = wano_without_view_constructor_helper(wmr)
        wmr.datachanged_force()
        wmr.datachanged_force()
        return wmr
        # Now we have the wano, what now?

    @classmethod
    def _clean_path(cls, path):
        return path.replace(" ","_")\
            .replace("[","_")\
            .replace("]","_")\
            .replace("(","_")\
            .replace(")","_")\
            .replace(",","_")\
            .replace("__","_")\
            .strip("_")

    @classmethod
    def _wano_to_namespaces_and_vars(cls, wmr):
        #mypaths = wmr.get_all_variable_paths(export = False)
        mypaths = wmr.get_paths_and_type_dict_aiida()
        namespaces = set()
        for path in mypaths:
            namespace = cls._clean_path(".".join(path.split(".")[:-1]))
            if namespace == "":
                continue
            else:
                namespaces.add(namespace)
        outpaths = {}
        for path in mypaths:
            outpaths[cls._clean_path(path)] = mypaths[path]
        return namespaces, outpaths

    # Plan: Make a type TreeWalker in WaNomodels
    # InputPathLists will be called: WListEx1 WListEx2 WListEx3
    # They should be expanded in the WaNo
    # Take care of the exec command somehow, output 5
    def prepare_for_submission(self, folder):
        """
        Create input files.

        :param folder: an `aiida.common.folders.Folder` where the plugin should temporarily place all files needed by
            the calculation.
        :return: `aiida.common.datastructures.CalcInfo` instance
        """
        codeinfo = datastructures.CodeInfo()
        codeinfo.cmdline_params = self.inputs.parameters.cmdline_params(
            file1_name=self.inputs.file1.filename,
            file2_name=self.inputs.file2.filename)
        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.stdout_name = self.metadata.options.output_filename
        codeinfo.withmpi = self.inputs.metadata.options.withmpi

        # Prepare a `CalcInfo` to be returned to the engine
        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = [
            (self.inputs.file1.uuid, self.inputs.file1.filename, self.inputs.file1.filename),
            (self.inputs.file2.uuid, self.inputs.file2.filename, self.inputs.file2.filename),
        ]
        calcinfo.retrieve_list = [self.metadata.options.output_filename]

        return calcinfo

from aiida.common.exceptions import NotExistent

class WaNoCalcJobParser(Parser):
    def parse(self, **kwargs):
        try:
            retrieved_folder = self.retrieved
        except NotExistent as _:
            return self.exit(self.exit_codes.ERROR_MISSING_OUTPUT_FILES)

        filename_stdout = self.node.get_attribute('output_filename')

        try:
            tensor_file = self.retrieved.get_object_content(filename_tensor)
        except (IOError, OSError):
            tensor_file = None

        self.out('output_parameters', orm.Dict(dict=parsed_data))

        for filename in sorted(self.retrieved.list_object_names(dynmat_folder), key=natural_sort):

            #filename_stdout = self.node.get_option('output_filename')  # or get_attribute(), but this is clearer
