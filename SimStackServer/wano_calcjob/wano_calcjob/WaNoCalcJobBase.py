import os

from aiida import orm
from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import SinglefileData
from jinja2 import Template
from lxml import etree

from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from TreeWalker.TreeWalker import TreeWalker


class WaNoCalcJob(CalcJob):
    """
    WaNo CalcJob Wrapper plugin.
    """
    _cached_input_namespaces = None
    _cached_output_namespaces = None
    _cached_inputs = None
    _cached_outputs = None
    _cached_output_files = None
    typemap = {
        "Float": orm.Float,
        "Boolean": orm.Bool,
        "String": orm.Str,
        "Int": orm.Int,
        "File": orm.SinglefileData
    }
    _myxml = None
    _wano_path = None

    @classmethod
    def wano_repo_path(cls):
        if cls._wano_path is None:
            myfile = __file__
            wanodir = os.path.dirname(os.path.abspath(os.path.realpath(myfile)))
            wanodir = os.path.join(wanodir,"..","wano_repo")
            cls._wano_path = wanodir
            return wanodir
        else:
            return cls._wano_path

    @classmethod
    def define(cls, spec):
        """Define inputs and outputs of the calculation."""
        # yapf: disable
        super(WaNoCalcJob, cls).define(spec)
        myxml = cls._myxml
        cls._build_spec_from_wano(wfxml=myxml, spec=spec)

        # set default values for AiiDA options
        spec.inputs['metadata']['options']['resources'].default = {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 1,
        }
        spec.inputs['metadata']['options']['parser_name'].default = 'Deposit3'
        spec.exit_code(100, 'ERROR_MISSING_OUTPUT_FILES', message='Calculation did not produce all expected output files.')
        spec.exit_code(0, 'EXIT_NORMAL', message='Normal exit condition.')




    @classmethod
    def _build_spec_from_wano(cls, wfxml, spec):
        wmr = cls._parse_wano_xml(wfxml)
        input_namespaces = cls.input_namespaces()
        input_vars = cls.input_vars()
        for namespace in input_namespaces:
            spec.input_namespace(namespace, dynamic=True)
        for path, vartype in input_vars.items():
            spec.input(path, valid_type=cls.typemap[vartype], required = False)

        wmr:WaNoModelRoot
        output_files = cls.output_files()
        output_namespaces = cls.output_namespaces()

        for ons in output_namespaces:
            spec.output_namespace(ons)

        for myfile in output_files:
            spec.output(cls.clean_path(cls.dot_to_none(myfile)), valid_type=SinglefileData)

        exec_command = wmr.exec_command
        spec.input('metadata.options.exec_command', valid_type = str, default = exec_command)

    @classmethod
    def dot_to_none(cls, inputpath):
        return inputpath.replace(".","")

    @classmethod
    def _set_caches(cls):
        wmr = cls._parse_wano_xml(cls._myxml)
        namespaces, vars, output_namespaces, outputs, outputfiles = cls._wano_to_namespaces_and_vars(wmr)
        cls._cached_input_namespaces = namespaces
        cls._cached_inputs = vars
        cls._cached_outputs = outputs
        cls._cached_output_namespaces = output_namespaces
        cls._cached_output_files = outputfiles

    @classmethod
    def input_namespaces(cls):
        if cls._cached_input_namespaces is None:
            cls._set_caches()
        return cls._cached_input_namespaces

    @classmethod
    def input_vars(cls):
        if cls._cached_inputs is None:
            cls._set_caches()
        return cls._cached_inputs

    @classmethod
    def output_namespaces(cls):
        if cls._cached_output_namespaces is None:
            cls._set_caches()
        return cls._cached_output_namespaces

    @classmethod
    def output_vars(cls):
        if cls._cached_outputs is None:
            cls._set_caches()
        return cls._cached_outputs

    @classmethod
    def output_files(cls):
        if cls._cached_output_files is None:
            cls._set_caches()
        return cls._cached_output_files

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

    @classmethod
    def clean_path(cls, path):
        if isinstance(path, int):
            return "L_ELE_%d"%path
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
        mypaths = wmr.get_paths_and_type_dict_aiida()
        namespaces = set()
        for path in mypaths:
            namespace = cls.clean_path(".".join(path.split(".")[:-1]))
            if namespace == "":
                continue
            else:
                namespaces.add(namespace)
        outpaths = {}
        for path in mypaths:
            outpaths[cls.clean_path(path)] = mypaths[path]

        output_namespaces = ["files"]
        outputfiles = wmr.get_output_files(only_static=True)
        outputs_in_namespace = []
        outputs = []
        for myfile in outputfiles:
            outputs_in_namespace.append("files.%s"%myfile)

        # We return input_namepsaces, input_paths, output_namespaces, output_paths (without files), outputfiles
        return namespaces, outpaths, output_namespaces, outputs, outputfiles

    # Take care of the exec command somehow, output 5
    def prepare_for_submission(self, folder):
        """
        Create input files.

        :param folder: an `aiida.common.folders.Folder` where the plugin should temporarily place all files needed by
            the calculation.
        :return: `aiida.common.datastructures.CalcInfo` instance
        """
        # we need to render everything here, i.e.
        # When initializing, we will have a rendered XML file from SimStackServer
        # It will know the filenames of the files - we need logical filename still to know where to put it
        # ExecCommand will be rendered by SSS and given
        # Who renders the input files?
        #
        codeinfo = datastructures.CodeInfo()
        codeinfo.code_uuid = self.inputs.code.uuid
        #codeinfo.stdout_name = self.options.output_filename
        #codeinfo.cmdline_params = ['-in', self.options.input_filename]

        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        calcinfo.local_copy_list = []
        calcinfo.remote_copy_list = []
        retrieve_list = []
        for outputfile in self.output_files():
            retrieve_list.append(outputfile)
        calcinfo.retrieve_list = retrieve_list
        print(retrieve_list)

        # codeinfo wird mit verdi code an lokale exe gekoppelt

        codeinfo = datastructures.CodeInfo()
        collected_variables = self.inputs
        exec_command = self.inputs.metadata.options.exec_command
        codeinfo.cmdline_params = " ".split(exec_command)[1:]
        Template(exec_command).render(collected_variables)

        codeinfo.code_uuid = self.inputs.code.uuid
        codeinfo.withmpi = self.inputs.metadata.options.withmpi



        # Write WaNo Files into folder and render them there,
        # Add them to local copy list
        # Prepare a `CalcInfo` to be returned to the engine
        #calcinfo.local_copy_list = [
        #    (self.inputs.file1.uuid, self.inputs.file1.filename, self.inputs.file1.filename),
        #    (self.inputs.file2.uuid, self.inputs.file2.filename, self.inputs.file2.filename),
        #]
        #calcinfo.retrieve_list = [self.metadata.options.output_filename]

        #print("STarting with calcinfo", calcinfo.retrieve_list)
        return calcinfo


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
