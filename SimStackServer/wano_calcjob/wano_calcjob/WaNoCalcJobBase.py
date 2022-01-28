import os
import re
from pathlib import Path

import yaml
from aiida import orm
from aiida.common import datastructures
from aiida.engine import CalcJob
from aiida.orm import SinglefileData
from jinja2 import Template
from lxml import etree

from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
from SimStackServer.wano_calcjob.wano_calcjob.wano_calcjob_exceptions import UnknownTypeError
from TreeWalker.TreeWalker import TreeWalker
from TreeWalker.flatten_dict import flatten_dict


class WaNoCalcJob(CalcJob):
    """
    WaNo CalcJob Wrapper plugin.
    """
    _cached_input_namespaces = None
    _cached_output_namespaces = None
    _cached_inputs = None
    _cached_outputs = None
    _cached_output_files = None
    _cached_inputfile_paths = None
    _cached_extra_inputfiles = None
    _cached_simstack_to_aiida_pathmap = None
    _cached_aiida_to_simstack_pathmap = None
    _parser_name = None

    typemap = {
        "Float": orm.Float,
        "FString": (orm.SinglefileData, orm.Str),
        "Boolean": orm.Bool,
        "String": orm.Str,
        "Int": orm.Int,
        "File": (orm.SinglefileData, orm.Str)
    }

    _myxml = None
    _wano_path = None

    @staticmethod
    def _guess_type(input_value):
        if isinstance(input_value, float):
            return "Float"
        if isinstance(input_value, int):
            return "Int"
        if isinstance(input_value, str):
            return "String"
        if isinstance(input_value, bool):
            return "Boolean"
        else:
            raise UnknownTypeError("Could not find type of %s: %s" % (input_value, type(input_value)))

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
    def _get_output_dict_from_wano_dir(cls):
        myxml = cls._myxml
        mydir = Path(myxml).parent
        outdict_fn = mydir/"output_dict.yml"
        returndict = {}
        if outdict_fn.is_file():
            with open(outdict_fn, 'rt') as infile:
                outdict = yaml.safe_load(infile.read())
            flattened_outdict = flatten_dict(outdict)
            for entry, value in flattened_outdict.items():
                mytype = cls._guess_type(value)
                returndict[entry] = mytype
        return returndict
        ## outconf still todo:
        #outconf_fn = mydir/"output_config.ini"

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
        spec.inputs['metadata']['options']['parser_name'].default = cls._parser_name
        spec.exit_code(100, 'ERROR_MISSING_OUTPUT_FILES', message='Calculation did not produce all expected output files.')
        spec.exit_code(0, 'EXIT_NORMAL', message='Normal exit condition.')

    #Todo TImo, here: you need to test this. It should be complete now.

    @classmethod
    def _build_spec_from_wano(cls, wfxml, spec):
        wmr = cls._parse_wano_xml(wfxml)
        input_namespaces = cls.input_namespaces()
        input_vars = cls.input_vars()
        for namespace in input_namespaces:
            spec.input_namespace(namespace, dynamic=True)
        for path, vartype in input_vars.items():
            spec.input(path, valid_type=cls.typemap[vartype], required = False)

        spec.input_namespace("static_extra_files", dynamic=True)
        spec.input_namespace("filename_locations", dynamic=True)
        for path in cls.extra_inputfiles():
            dotpath = "static_extra_files." + cls.clean_path(cls.dot_to_none(path))
            spec.input(dotpath, valid_type = orm.SinglefileData, required = True)
        spec.input("static_extra_files.rendered_wanoyml", valid_type=orm.SinglefileData)

        wmr: WaNoModelRoot
        output_files = cls.output_files()
        output_namespaces = cls.output_namespaces()
        output_vars = cls.output_vars()

        for ons in output_namespaces:
            if ons == "files":
                spec.output_namespace(ons, dynamic = True)
            else:
                spec.output_namespace(ons)

        for path, vartype in output_vars.items():
            spec.output(path, valid_type=cls.typemap[vartype], required = False)

        for myfile in output_files:
            spec.output(cls.clean_path(cls.dot_to_none(myfile)), valid_type=SinglefileData)

        exec_command = wmr.exec_command
        spec.input('metadata.options.exec_command', valid_type = str, default = exec_command)

    @classmethod
    def dot_to_none(cls, inputpath):
        return inputpath.replace(".","")

    @classmethod
    def dot_to_two_underscores(cls, inputpath):
        return inputpath.replace(".", "__")

    @classmethod
    def _set_caches(cls):
        wmr = cls._parse_wano_xml(cls._myxml)
        wano_namespaces_and_vars_dict = cls._wano_to_namespaces_and_vars(wmr)
        cls._cached_input_namespaces = wano_namespaces_and_vars_dict["namespaces"]
        cls._cached_inputs = wano_namespaces_and_vars_dict["input_types_by_cleaned_path"]
        cls._cached_outputs = wano_namespaces_and_vars_dict["output_types_by_cleaned_path"]
        cls._cached_output_namespaces = wano_namespaces_and_vars_dict["output_namespaces"]
        cls._cached_output_files = wano_namespaces_and_vars_dict["outputfiles"]
        cls._cached_inputfile_paths = wano_namespaces_and_vars_dict["inputfile_paths"]
        cls._cached_extra_inputfiles = wano_namespaces_and_vars_dict["extra_inputfile_paths"]
        cls._cached_simstack_to_aiida_pathmap = wano_namespaces_and_vars_dict["simstack_to_aiida_pathmap"]
        cls._cached_aiida_to_simstack_pathmap = wano_namespaces_and_vars_dict["aiida_to_simstack_pathmap"]

    @classmethod
    def input_namespaces(cls):
        if cls._cached_input_namespaces is None:
            cls._set_caches()
        return cls._cached_input_namespaces

    @classmethod
    def inputfile_paths(cls):
        if cls._cached_inputfile_paths is None:
            cls._set_caches()
        return cls._cached_inputfile_paths

    @classmethod
    def extra_inputfiles(cls):
        if cls._cached_extra_inputfiles is None:
            cls._set_caches()
        return cls._cached_extra_inputfiles

    @classmethod
    def get_simstack_to_aiida_pathmap(cls):
        if cls._cached_simstack_to_aiida_pathmap is None:
            cls._set_caches()
        return cls._cached_simstack_to_aiida_pathmap

    @classmethod
    def get_aiida_to_simstack_pathmap(cls):
        if cls._cached_aiida_to_simstack_pathmap is None:
            cls._set_caches()
        return cls._cached_aiida_to_simstack_pathmap

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
        wano_dir_root = Path(os.path.dirname(wfxml))
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
        #MODELROOTDIRECT
        wmr = WaNoModelRoot(wano_dir_root = wano_dir_root, model_only = True)
        wmr.parse_from_xml(xml)
        wmr = wano_without_view_constructor_helper(wmr)
        wmr.datachanged_force()
        wmr.datachanged_force()
        return wmr

    @classmethod
    def clean_path(cls, path):
        # replaces "45.gdg.2.1421.j55.33" with "ELE_45.gdg.ELE_2.ELE_1421.j55.ELE_33" because aiida does not like integer ports
        path = re.sub(r"(\.|^)(\d*)(\.|$)",r"\1ELE_\2\3", path)
        if isinstance(path, int):
            return "L_ELE_%d"%path
        return path.replace(" ","_")\
            .replace("[","_")\
            .replace("]","_")\
            .replace("(","_")\
            .replace(")","_")\
            .replace(",","_")\
            .replace("+","_")\
            .replace("-","_")\
            .replace("/","_")\
            .replace("\\","_")\
            .replace("__","_")\
            .strip("_")

    @classmethod
    def _wano_to_namespaces_and_vars(cls, wmr):
        mypaths = wmr.get_paths_and_type_dict_aiida()
        namespaces = set()
        inputfile_paths = []
        for path, mytype in mypaths.items():
            namespace = cls.clean_path(".".join(path.split(".")[:-1]))
            if mytype in ["File", "FString"]:
                inputfile_paths.append(path)
            if namespace == "":
                continue
            else:
                namespaces.add(namespace)
            #else:
            #    print("found type",mytype)
        inpaths = {}
        for path in mypaths:
            inpaths[cls.clean_path(path)] = mypaths[path]
        
        output_namespaces = ["files"]
        outputfiles = wmr.get_output_files(only_static=True)
        outputfiles = set(outputfiles)
        outputfiles.add("output_config.ini")
        outputfiles.add("output_dict.yml")
        outputfiles = list(outputfiles)
        outputs_in_namespace = []

        # wmr needs a


        outpaths = {}

        simstack_to_aiida_pathmap = {}
        aiida_to_simstack_pathmap = {}

        for myfile in outputfiles:
            outputs_in_namespace.append("files.%s"%myfile)
            simstack_file = "files." + myfile
            aiida_file = "files__" + cls.dot_to_none(myfile)
            simstack_to_aiida_pathmap[simstack_file] = aiida_file
            aiida_to_simstack_pathmap[aiida_file] = simstack_file


        output_namespaces = set(output_namespaces)
        non_file_outputs = cls._get_output_dict_from_wano_dir()
        for path, mytype in non_file_outputs.items():
            namespace = cls.clean_path(".".join(path.split(".")[:-1]))
            if namespace == "":
                continue
            else:
                output_namespaces.add(namespace)

        for path in non_file_outputs:
            clean_path = cls.clean_path(path)

            # When querying paths from AiiDA it somehow translates dots into double underscores.
            double_underscore_clean_path = cls.dot_to_two_underscores(clean_path)
            simstack_to_aiida_pathmap[path] = double_underscore_clean_path
            aiida_to_simstack_pathmap[double_underscore_clean_path] = path
            outpaths[clean_path] = non_file_outputs[path]

        output_namespaces = list(output_namespaces)

        extra_inputfile_paths = wmr.get_extra_inputs_aiida()
        # We return input_namepsaces, input_paths, output_namespaces, output_paths (without files), outputfiles
        return {
            "namespaces": namespaces,
            "input_types_by_cleaned_path": inpaths,
            "output_namespaces": output_namespaces,
            "output_types_by_cleaned_path": outpaths,
            "outputfiles": outputfiles,
            "inputfile_paths": inputfile_paths,
            "extra_inputfile_paths": extra_inputfile_paths,
            "simstack_to_aiida_pathmap" : simstack_to_aiida_pathmap,
            "aiida_to_simstack_pathmap": aiida_to_simstack_pathmap
        }

    @classmethod
    def deref_by_listpath(cls, toderef, listpath):
        if len(listpath) == 0:
            return toderef
        toderef_path = listpath.pop(0)
        toderef = toderef[cls.clean_path(toderef_path)]
        return cls.deref_by_listpath(toderef, listpath)
        

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
        codeinfo.cmdline_params = ["exec_command.sh"]

        with folder.open("exec_command.sh", 'wt') as outfile:
            outfile.write(self.inputs["metadata"]["options"]["exec_command"] + "\n")

        calcinfo = datastructures.CalcInfo()
        calcinfo.codes_info = [codeinfo]
        local_copy_list = []
        #calcinfo.remote_copy_list = []
        uuid_to_loc = {}
        for uuidkey, loc in self.inputs["filename_locations"].items():
            uuid_to_loc[uuidkey[1:].replace("_","-")] = loc


        for localfile_path_without in self.extra_inputfiles():
            try:
                localfile_path = "static_extra_files." + self.dot_to_none(localfile_path_without)
                fileobj = self.deref_by_listpath(self.inputs, localfile_path.split("."))
                myname = uuid_to_loc[str(fileobj.uuid)].value
                local_copy_list.append((fileobj.uuid, fileobj.filename, myname))
            except KeyError as e:
                pass
                #print("Most probably encountered during multipleof", localfile_path)

        local_copy_list.append( (self.inputs.static_extra_files.rendered_wanoyml.uuid, "rendered_wano.yml", "rendered_wano.yml") )
        for localfile_path in self.inputfile_paths():
            try:
                fileobj = self.deref_by_listpath(self.inputs, localfile_path.split("."))
                myname = uuid_to_loc[str(fileobj.uuid)].value
                local_copy_list.append((fileobj.uuid, fileobj.filename, myname))
            except KeyError as e:
                pass
                #print("Most probably encountered during multipleof", localfile_path)

        calcinfo.local_copy_list = local_copy_list


        retrieve_list = []
        for outputfile in self.output_files():
            retrieve_list.append(( outputfile, ".", outputfile.count("/")+1 ))
        retrieve_list.append(("output_dict.yml",".",1))
        retrieve_list.append(("output_config.ini", ".", 1))
        calcinfo.retrieve_list = retrieve_list

        # codeinfo wird mit verdi code an lokale exe gekoppelt

        codeinfo = datastructures.CodeInfo()
        #collected_variables = self.inputs
        #exec_command = self.inputs.metadata.options.exec_command
        #Template(exec_command).render(collected_variables)

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
