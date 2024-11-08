import abc
import copy
import datetime
import io
import json
import pathlib
import re
import subprocess
import time
import logging
import os
import shutil
import sys
import jsonschema
import traceback
import uuid
from abc import abstractmethod, abstractclassmethod
from enum import Flag, auto
from glob import glob
from io import StringIO
from os.path import join

from pathlib import Path

from os import path
from typing import Optional, Dict

import yaml
from lxml import etree
import lxml.html

from SimStackServer.SecureWaNos import SecureWaNos, SecureModeGlobal
from SimStackServer.Util.Exceptions import SecurityError
from SimStackServer.Util.localhost_checker import is_localhost
from nestdictmod.nestdictmod import NestDictMod
from SimStackServer.WaNo.WaNoTreeWalker import subdict_skiplevel_path_version


import numpy as np
import networkx as nx

from SimStackServer.EvalHandler import eval_numpyexpression
from SimStackServer.MessageTypes import JobStatus
from SimStackServer.Reporting import Templates
from SimStackServer.Reporting.ReportRenderer import ReportRenderer
from SimStackServer.Util.FileUtilities import mkdir_p, StringLoggingHandler, abs_resolve_file
from SimStackServer.Util.ResultRepo import ResultRepo
from clusterjob import FAILED
from nestdictmod.flatten_dict import flatten_dict
from jinja2 import Template


class ParserError(Exception):
    pass

class JobSubmitException(Exception):
    pass

class JustCopyException(Exception):
    pass

class Status(Flag):
    UNINITIALIZED = auto()
    READY = auto()
    SUBMITTED = auto()
    RUNNING = auto()
    ABORTED = auto()
    SUCCESS = auto()
    FAILED = auto()
    GONE = auto()


def _is_basetype(check_type):
    """
    Checks whether the type is able to convert from xml_element.text or needs to be further interpreted.

    :param check_type (type or object): The type or object to check.
    :return (bool): is it a basetype?
    """
    # This can be made a bit better, but currently we just ask, whether a to_xml exists:
    return not hasattr(check_type, "to_xml")

def _str_to_bool(value: str):
    if value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False
    else:
        raise ValueError(f"Unknown bool '{value}'.")

class XMLYMLInstantiationBase(object):
    """
    XMLYMLInstantiationBase provides XML and YML parsers and writers for more or less trivial data types.

    To use it: Inherit from it and define the field property.
    An example would be:
    @classmethod
    @property
    def fields(cls):
        return cls._fields

    with
        fields = [("AnInteger",np.int64,0,"A sample integer", "a/m"),(...)]

    """
    def __init__(self, *args, **kwargs):

        self._field_values = {}
        self._field_types = {}
        self._field_explanations = {}
        self._field_defaults = {}
        self._field_attribute_or_member = {}
        self._field_names = set()
        self._setup_empty_field_values()
        self._last_dump_time = time.time()

        for key,value in kwargs.items():
            if self.contains(key):
                if value != None:
                    self._field_values[key] = value

    def contains(self,key):
        return key in self._field_names

    def field_type(self, fieldname: str):
        return self._field_types[fieldname]

    def set_field_value(self, fieldname, value):
        #this_index = [i for i in range(len(self._fields)) if self._fields if self._fields[i][0] == fieldname]
        #assert isinstance(value, self._fields[this_index][2]), "value is not of correct type"
        #self._fields[this_index][2] = value
        value = self._field_types[fieldname](value)

        assert isinstance(value, self._field_types[fieldname]), "Value for field %s does not have the correct type"%fieldname
        self._field_values[fieldname] = value

    def get_field_value(self, fieldname):
        return(self._field_values[fieldname])

    @classmethod
    @abstractmethod
    def fields(cls):
        """
        This function defines the fields, which the child class posesses.
        For each field, the field_values dict will be instantiated and the default will be written inside.
        Note to future programmers:
           Based on this information you could also define a __getattr__ function to obtain the property dynamically.
           I did not do this to still allow for completion in the IDE.
        :return (List of Tuples of size 4) : A List of tuples, which contain:
            The name of the field, the type, the default, an explanation.
        """
        raise NotImplementedError("This method has to be implemented in child methods.")
        # Returns list so IDEs can infer the type.
        return []

    def _setup_empty_field_values(self):
        """
        This function just initializes all fields with their default. It also checks, whether the appropriate child class contains an accessor function.

        :return : Nothing
        """
        for field, fieldtype, default , explanation, attribute_or_member in self.fields():
            self._field_values[field] = fieldtype(default)
            self._field_types[field] = fieldtype
            self._field_explanations[field] = explanation
            self._field_defaults[field] = default
            self._field_attribute_or_member[field] = attribute_or_member
            self._field_names.add(field)
            assert hasattr(self,field), "Field %s not found as property function."% field

    def _set_resource_if_present(self, key, indict, default = None):
        """
        A parser helper function. If key is in indict, overwrite field_values, otherwise do nothing.
        If default is set and key is not in indict, provide default.

        :param key (str): Name of the thing to change in field_values
        :param indict (dict): Dictionary of content
        :return: Nothing
        """
        if key in indict:
            self._field_values[key] = self._field_types[key](indict[key])
        elif not default is None:
            self._field_values[key] = self._field_types[key](default)

    def to_xml(self, parent_element):
        """

        :return etree.Element: Prepared XML element
        """
        for name, fieldvalue in self._field_values.items():
            attr_or_member = self._field_attribute_or_member[name]
            if attr_or_member == 'a':
                parent_element.attrib[name] = str(fieldvalue)
            else:
                ape = etree.Element(name)
                if not _is_basetype(fieldvalue):
                    fieldvalue.to_xml(ape)
                else:
                    ape.text = str(fieldvalue)
                parent_element.append(ape)

    def from_xml(self, in_xml):
        """

        :param in_xml: An lxml etree XML Element
        :return:
        """
        for child in in_xml:
            field = child.tag
            if not field in self._field_values:
                continue

            childtype = self._field_types[field]
            if _is_basetype(childtype):
                if childtype == JobStatus:
                    self._field_values[field] = childtype(int(child.text))
                elif childtype == bool:
                    self._field_values[field] = _str_to_bool(child.text)
                else:
                    self._field_values[field] = childtype(child.text)
            else:
                insert_element = childtype()
                insert_element.from_xml(child)
                self._field_values[field] = insert_element

        for field, value in in_xml.attrib.items():
            if not field in self._field_values:
                continue
            childtype = self._field_types[field]
            if childtype == JobStatus:
                self._field_values[field] = childtype(int(value))
            elif childtype == bool:
                self._field_values[field] = _str_to_bool(value)
            else:
                self._field_values[field] = self._field_types[field](value)

    def from_dict(self, in_dict):
        """

        :param in_dict (dict): Dictionary with the values to reinstate the class.
        :return: Nothing.
        """
        for field, value in in_dict.items():
            if not field in self._field_values:
                continue
            childtype = self._field_types[field]

            if _is_basetype(childtype):
                if childtype == JobStatus:
                    self._field_values[field] = childtype(int(value))
                elif childtype == bool:
                    self._field_values[field] = _str_to_bool(value)
                else:
                    self._field_values[field] = childtype(value)
            else:
                insert_ele = childtype()
                insert_ele.from_dict(value)
                self._field_values[field] = insert_ele


    def to_dict(self, parent_dict):
        """

        :return (dict): This class as a dictionary to be fed into from_dict for example.
        """
        for name, fieldvalue in self._field_values.items():

            if _is_basetype(fieldvalue):
                parent_dict[name] = str(fieldvalue)
            else:
                parent_dict[name] = {}
                fieldvalue.to_dict(parent_dict[name])

    @classmethod
    def new_instance_from_xml(cls, filename):
        with open(filename, 'rt') as infile:
            myxml = etree.parse(infile).getroot()
        a = cls()

        a.from_xml(myxml)
        return a

    def dump_xml_to_file(self, filename):
        me = etree.Element("Workflow")
        me.attrib["wfname"] = self.name
        self.to_xml(me)
        with open(filename, 'wt') as infile:
            infile.write(etree.tostring(me,encoding="utf8",pretty_print=True).decode()+"\n")

    def from_json(self, filename: pathlib.Path):
        with filename.open('rt') as infile:
            mydict = json.load(infile)
        self.from_dict(mydict)

    def to_json(self, filename: pathlib.Path):
        outdict = {}
        self.to_dict(outdict)
        with filename.open('wt') as outfile:
            json.dump(outdict, outfile)

    def fill_in_variables(self, vardict):
        pass



# Tomorrow: Modify this factory to play nice with TreeWalker
#   Override isdict and islist for ForEachGraph
#   Suddenly everything has a URI
#

def workflow_element_factory(name):
    """
    Placeholder function to generate WorkflowElements based on their name. Currently only returns the class of WorkflowElement
    :param name:
    :return:
    """
    if name == "WorkflowExecModule":
        return WorkflowExecModule
    elif name == "StringList":
        return StringList
    elif name == "WorkflowElementList":
        return WorkflowElementList
    elif name == "WFPass":
        return WFPass
    elif name == "ForEachGraph":
        return ForEachGraph
    elif name == "IfGraph":
        return IfGraph
    elif name == "VariableElement":
        return VariableElement
    elif name == "WhileGraph":
        return WhileGraph
    elif name == "SubGraph":
        return SubGraph
    elif name == "int":
        return int
    elif name == "str":
        return str
    elif name == "bool":
        return bool
    else:
        #print(globals())
        if name.startswith("np."):
            name = name[3:]
            classobj = getattr(globals()["np"],name)
            assert np.issubdtype(classobj, np.number), "Only allowed to import actual numbertypes"
            return classobj
    raise NotImplementedError("Please add type %s to workflow element factory"%name)


class UnknownWFEError(Exception):
    pass


class WorkflowElementList(object):
    def __init__(self, *args, **kwargs):
        self._logger = logging.getLogger("WorkflowElementList")
        self._clear()
        for inputvar in args:
            if isinstance(inputvar,list):
                #print(inputvar)
                for fieldtype, myobj in inputvar:
                    self._add_to_list(fieldtype, myobj)
        self._recreate_uid_to_seqnum()

    def _clear(self):
        self._storage = []
        self._typelist = []
        self._uid_to_seqnum = {}

    def merge_other_list(self, other_list):
        for st, tp in zip(other_list._storage, other_list._typelist):
            self._storage.append(st)
            self._typelist.append(tp)
        self._recreate_uid_to_seqnum()

    def fill_in_variables(self, vardict):
        for myid, my_str in enumerate(self._storage):
            if isinstance(my_str,str):
                current_string = my_str
                for key,item in vardict.items():
                    current_string = current_string.replace(key,item)
                    self._logger.info("Replacing %s with %s and %s, Outcome was: %s"%(my_str, key, item, current_string))
                self._storage[myid] = current_string
            else:
                if not _is_basetype(my_str):
                    my_str.fill_in_variables(vardict)

    def _recreate_uid_to_seqnum(self):
        self._uid_to_seqnum = {}
        for seqnum,element in enumerate(self._storage):
            if hasattr(element,"uid"):
                self._uid_to_seqnum[element.uid] = seqnum

    def _add_to_list(self, mytype, actual_object):
        self._typelist.append(mytype)
        self._storage.append(actual_object)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.compare_with_other_list(other)
        else:
            return False

    def compare_with_other_list(self, other_list):
        if len(other_list._storage) != len(self._storage):
            return False
        for element1, element2 in zip(self._storage, other_list._storage):
            if element1 != element2:
                return False
        return True

    def __getitem__(self, item):
        assert isinstance(item,int)
        return self._storage[item]

    def __len__(self):
        return len(self._storage)

    def __iter__(self):
        for item in self._storage:
            yield item

    def get_element_by_uid(self, uid):
        return self._storage[self._uid_to_seqnum[uid]]

    def to_xml(self, parent_element):
        """

        :return etree.Element: Prepared XML element
        """
        for myid,(element,ele_type) in enumerate(zip(self._storage,self._typelist)):
            element: WorkflowExecModule
            if hasattr(element,"name"):
                elementname = element.name
            else:
                elementname = "Ele_%d" % myid

            xml_ele = etree.Element(elementname)
            xml_ele.attrib["id"] = str(myid)
            xml_ele.attrib["type"] = ele_type
            if not _is_basetype(element):
                element.to_xml(xml_ele)
            else:
                xml_ele.text = str(element)
            parent_element.append(xml_ele)

    def from_xml(self, in_xml):
        """

        :param in_xml: An lxml etree XML Element
        :return:
        """
        self._clear()
        seqnum = 0
        for child in in_xml:
            field = child.attrib["type"]

            try:
                fieldobject = workflow_element_factory(field)
                if not _is_basetype(fieldobject):
                    myfo = fieldobject()
                    myfo.from_xml(child)
                else:
                    try:
                        myfo = fieldobject(child.text)
                    except TypeError as e:
                        self._logger.exception("Could not instantiate object. Type was: %s. Text was: %s"%(type(fieldobject),child.text))
                        raise e from e
                self._storage.append(myfo)
                self._typelist.append(field)
                if "uid" in child.attrib:
                    uid = child.attrib["uid"]
                    self._uid_to_seqnum[uid] = len(self._storage) - 1
            except UnknownWFEError as e:
                pass

    def from_dict(self, in_dict):
        """

        :param in_dict (dict): Dictionary with the values to reinstate the class.
        :return: Nothing.
        """
        """

        :param in_xml: An lxml etree XML Element
        :return:
        """
        self._clear()
        for c_id, child in in_dict.items():
            field = child["type"]
            try:
                fieldobject = workflow_element_factory(field)
                if not _is_basetype(fieldobject):
                    myfo = fieldobject()
                    myfo.from_dict(child["value"])
                else:
                    myfo = fieldobject(child["value"])
                self._storage.append(myfo)
                self._typelist.append(field)
            except UnknownWFEError as e:
                pass

    def to_dict(self, parent_dict):
        """

        :return (dict): This class as a dictionary to be fed into from_dict for example.
        """
        for myid, (element, ele_type) in enumerate(zip(self._storage, self._typelist)):
            element: WorkflowExecModule
            if hasattr(element, "name"):
                elementname = element.name
            else:
                elementname = "Ele_%d" % myid

            parent_dict[myid] = {}
            mydict = parent_dict[myid]
            mydict["name"] = elementname
            mydict["type"] = ele_type

            if not _is_basetype(element):
                mydict["value"] = dict()

                element.to_dict(mydict["value"])
            else:
                mydict["value"] = str(element)


class StringList(WorkflowElementList):
    """
    A WorkflowElementList, which you can conveniently initialize with only Strings

    """
    def __init__(self, *args, **kwargs):
        strings = []
        arglist = list(args)
        delete = []
        for arg in arglist:
            if isinstance(arg, list):
                strings = arg
                delete.append(arg)
        for todel in delete:
            arglist.remove(todel)

        super().__init__(arglist, **kwargs)

        self._storage = strings
        for i in strings:
            self._typelist.append("str")

    def rename(self, replacedict):
        for i in range(0, len(self._storage)):
            if self._storage[i] in replacedict:
                self._storage[i] = replacedict[self._storage[i]]

class Resources(XMLYMLInstantiationBase):
    """
    Class to store computational resources. Used to create jobs. Host refers to the HPC master this is running on.
    """
    _connected_server_text = "<Connected Server>"
    _fields = [
        ("resource_name", str, _connected_server_text, "Name of the resource. Valid resource if unset", "a"),
        ("walltime", np.uint64, 86399, "Walltime in seconds", "a"),
        ("cpus_per_node", np.uint64, 1, "Number of CPUs per Node", "a"),
        ("nodes",np.uint64, 1, "Number of Nodes", "a"),
        ("queue", str, "default", "String representation of queue", "m"),
        ("memory", np.uint64, 4096,  "Memory in Megabytes", "a"),
        ("custom_requests", str, "", "Comma separated list specifying additional parameters not covered here.","m"),
        ("base_URI", str, "", "Base URI for resource", "m"),
        ("port", np.uint64, 22, "Port to access resource", "m"),
        ("username", str, "", "Username on resource", "m"),
        ("basepath", str, "simstack_workspace", "Basepath where to execute workflows relative to home/username", "m"),
        ("queueing_system", str, "unset", "Queuing System, e.g. slurm, pbs...", "m"),
        ("sw_dir_on_resource", str, "/home/nanomatch/nanomatch", "Software directory on cluster", "m"),
        ("extra_config", str, "None Required (default)", "Filepath on cluster to configuration file required before Serverstart is possible", "m"),
        ("ssh_private_key", str, "UseSystemDefault", "File to ssh private key", "m"),
        ("sge_pe", str, "", "SGE Parallel Environment. Only applicable to SGE queue", "m"),
        ("reuse_results", bool, False, "Reuse existing results", "a"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert len(self.render_order()) == len(self._fields), "Please add all fields to render_order."

    def render_order(self):
        """
        Order this will usually be displayed in
        :return:
        """
        return [
            "resource_name",
            "base_URI",
            "port",
            "username",
            "ssh_private_key",
            "sw_dir_on_resource",
            "basepath",
            "queueing_system",
            "extra_config",
            "nodes",
            "cpus_per_node",
            "walltime",
            "memory",
            "queue",
            "custom_requests",
            "sge_pe",
            "reuse_results"
        ]

    @classmethod
    def fields(cls):
        return cls._fields

    @property
    def resource_name(self):
        return self._field_values["resource_name"]

    @property
    def walltime(self):
        return self._field_values["walltime"]

    @property
    def cpus_per_node(self):
        return self._field_values["cpus_per_node"]

    @property
    def nodes(self):
        return self._field_values["nodes"]

    @property
    def queue(self):
        return self._field_values["queue"]

    @property
    def custom_requests(self):
        return self._field_values["custom_requests"]

    @property
    def memory(self):
        return self._field_values["memory"]

    @property
    def base_URI(self):
        return self._field_values["base_URI"]

    @property
    def port(self):
        return self._field_values["port"]

    @property
    def username(self):
        return self._field_values["username"]

    @property
    def basepath(self):
        return self._field_values["basepath"]

    @property
    def queueing_system(self):
        return self._field_values["queueing_system"]

    @property
    def sge_pe(self):
        return self._field_values["sge_pe"]

    @property
    def sw_dir_on_resource(self):
        return self._field_values["sw_dir_on_resource"]

    @property
    def ssh_private_key(self):
        return self._field_values["ssh_private_key"]

    @property
    def extra_config(self):
        return self._field_values["extra_config"]

    @property
    def reuse_results(self):
        return self._field_values["reuse_results"]

    def overwrite_unset_fields_from_default_resources(self, default_resources : 'Resources'):
        queue = self.queue
        if default_resources.base_URI == self.base_URI:
            # In this case this WaNo will run on the same computer
            self.set_field_value("base_URI",None)
            self.set_field_value("resource_name",self._connected_server_text)
        replace_set = {"default", "", None, "None", "unset"}
        if queue in replace_set:
            self.set_field_value("queue", default_resources.queue)
        queueing_system = self.queueing_system
        if queueing_system in replace_set:
            self.set_field_value("queueing_system", default_resources.queueing_system)
        sge_pe = self.sge_pe
        if sge_pe in replace_set:
            self.set_field_value("sge_pe", default_resources.sge_pe)

class ReportError(Exception):
    pass





class WorkflowExecModule(XMLYMLInstantiationBase):
    _fields = [
        ("uid", str, None, "uid of this WorkflowExecModule.", "a"),
        ("given_name", str, "WFEM", "Name of this WorkflowExecModule.", "a"),
        ("path", str, "unset", "Path to this WFEM in the workflow.", "a"),
        ("wano_xml", str, "unset", "Name of the WaNo XML.", "a"),
        ("outputpath", str, "unset", "Path to the output directory of this wfem in the workflow.", "a"),
        ("original_result_directory", str, "", "Path to the output directory of the wfem where the results were originally computed.", "a"),
        ("inputs",       WorkflowElementList, None, "List of Input URLs", "m"),
        ("outputs",      WorkflowElementList, None, "List of Outputs URLs", "m"),
        ("exec_command", str,                 None, "Command to be executed as part of BSS. Example: 'date'", "m"),
        ("resources", Resources, None, "Computational resources", "m"),
        ("runtime_directory",str, "unstarted", "The directory this wfem was started in","m"),
        ("jobid", str, "unstarted", "The id of the job this wfem was started with.", "m"),
        ("external_runtime_directory", str, "", "If this is a non-local job, the directory on the external directory is stored here.","m")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "WorkflowExecModule"
        self._conda_base_prefix = self._get_conda_basedir()
        self._logger = logging.getLogger(self.uid)
        self._runtime_variables = {}
        self._aiida_valuedict = None
        self._xmlbasename = os.path.basename(self.wano_xml)
        self._rendered_body_html = None
        self._failed = False
        self._my_external_cluster_manager = None

    @staticmethod
    def _get_conda_basedir():
        conda_prefix = os.environ["CONDA_PREFIX"]
        envloc = conda_prefix.find('/envs/')
        conda_base_prefix = conda_prefix[0:envloc]
        return conda_base_prefix

    @classmethod
    def fields(cls):
        return cls._fields

    def reset_resources_to_localhost(self):
        self.resources.set_field_value("base_URI", "localhost")

    def fill_in_variables(self, vardict):
        self._logger.info("Doing inputs of wanoid %s"%self.uid)
        self._field_values["inputs"].fill_in_variables(vardict)
        self._logger.info("Doing outputs of wanoid %s"%self.uid)
        self._field_values["outputs"].fill_in_variables(vardict)
        self._logger.info("Done")
        for key, item in vardict.items():
            self._field_values["outputpath"] = self._field_values["outputpath"].replace(key,item)
        self._runtime_variables.update(vardict)

    def set_failed(self):
        self._failed = True

    @property
    def failed(self):
        return self._failed

    def get_runtime_variables(self):
        return self._runtime_variables

    def check_if_job_is_local(self):
        trivial_local = self.resources.resource_name in [None, Resources._connected_server_text]
        if trivial_local:
            return True
        # The next two lines allow us to fake two SimStackServers on the same machine for unit testing.
        username = os.getlogin()
        if username != self.resources.username:
            return False
        return is_localhost(self.resources.base_URI)

    def rename(self, renamedict):
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

    def _get_clustermanager_from_job(self):
        from SimStackServer.RemoteServerManager import RemoteServerManager
        remote_server_manager = RemoteServerManager.get_instance()
        return remote_server_manager.server_from_resource(self.resources)

    def _get_mamba_variables(self) -> Dict[str, str]:
        """ Gets all manually exported conda variables. """
        for com in ["mamba", "conda"]:
            try:
                conda_command = [com, "env", "config", "vars", "list", "--json"]
                proc = subprocess.run(conda_command, capture_output=True, encoding="Utf-8")
                if proc.returncode != 0:
                    self._logger.error(f"Could not parse Conda variables. Stdout was: {proc.stdout}, Stderr: {proc.stderr}")
                    continue
                text = proc.stdout
                vardict = json.loads(text)
                return vardict
            except FileNotFoundError:
                pass
        return {}

    def _get_prolog_unicore_compatibility(self, resources):
        """

        :param resources:
        :return:
        """
        exported_variables = self._get_mamba_variables()

        varstring = [f"export {var}={content}" for var, content in exported_variables.items()]
        varstring = "\n".join(varstring)

        script = f"""
UC_NODES={resources.nodes}; export UC_NODES;
UC_PROCESSORS_PER_NODE={resources.cpus_per_node}; export UC_PROCESSORS_PER_NODE;
UC_TOTAL_PROCESSORS={resources.cpus_per_node*resources.nodes}; export UC_TOTAL_PROCESSORS;
UC_MEMORY_PER_NODE={resources.memory}; export UC_MEMORY_PER_NODE;
BASEFOLDER="{self._conda_base_prefix}"

# The following are exports to resolve previous and future
# versions of the SimStackServer conda / python interpreters
###########################################################
# These are the exports present in SimStackServer conda environment:
{varstring}
# End

simstack_server_mamba_source () {{{{
    MICROMAMBA_BIN="$BASEFOLDER/envs/simstack_server_v6/bin/micromamba"
    if [ -f "$MICROMAMBA_BIN" ]
    then
        export MAMBA_ROOT_PREFIX=$BASEFOLDER
        eval "$($MICROMAMBA_BIN shell hook -s posix)"
        export MAMBA_EXE=micromamba
    else
        if [ -d "$BASEFOLDER/../local_anaconda" ]
        then
            source $BASEFOLDER/../local_anaconda/etc/profile.d/conda.sh
        else
            source $BASEFOLDER/etc/profile.d/conda.sh
        fi
        export MAMBA_EXE=conda
    fi
}}}}

# Following are the legacy exports:
if [ -d "$BASEFOLDER/../local_anaconda" ]
then
    # In this case we are in legacy installation mode:
    export NANOMATCH="$BASEFOLDER/../.."
fi

if [ -f "$BASEFOLDER/nanomatch_environment_config.sh" ]
then
    source "$BASEFOLDER/nanomatch_environment_config.sh"
fi
if [ -f "$BASEFOLDER/simstack_environment_config.sh" ]
then
    source "$BASEFOLDER/simstack_environment_config.sh"
fi
if [ -f "/etc/simstack/simstack_environment_config.sh" ]
then
    source "/etc/simstack/simstack_environment_config.sh"
fi
###########################################################

"""
        return script

    @staticmethod
    def _time_from_seconds_to_clusterjob_timestring(time_in_seconds):
        days = int(time_in_seconds // 86400)
        rest = time_in_seconds - days* 86400
        hours = int(rest // 3600)
        rest = rest - hours * 3600
        minutes = rest // 60
        rest = rest - minutes*60
        seconds = rest


        timestring = ""
        if days > 0:
            timestring += "%d-"%days
        if hours > 0 or days > 0:
            timestring += "%d:"%hours
        if minutes > 0 or hours > 0 or days > 0:
            timestring += "%02d:"%minutes
        timestring += "%02d"%seconds
        return timestring


    def run_jobfile(self, external_cluster_manager = None):
        actual_resources = self.resources
        queueing_system = actual_resources.queueing_system
        temphandler = StringLoggingHandler()
        temphandler.setLevel(logging.DEBUG)
        do_internal = False
        do_aiida = False
        dont_run = False
        self.set_runtime_directory(abs_resolve_file(self.runtime_directory))

        if not external_cluster_manager is None:

            from SimStackServer.ClusterManager import ClusterManager
            external_cluster_manager : ClusterManager
            with external_cluster_manager.connection_context():
                ext_dir_name = external_cluster_manager.mkdir_random_singlejob_exec_directory(self.given_name)

                ext_dir_abs = external_cluster_manager.put_directory(self.runtime_directory, ext_dir_name, basepath_override=actual_resources.basepath)
                external_wfem = copy.deepcopy(self)


                external_wfem.set_runtime_directory(ext_dir_abs)
                external_wfem.reset_resources_to_localhost()
                external_cluster_manager.submit_single_job(external_wfem)
            self._my_external_cluster_manager = external_cluster_manager
            self.set_external_runtime_directory(ext_dir_abs)
            self.set_jobid(f"ext:{self.uid}")
            return
        if queueing_system == "Internal":
            queueing_system = "slurm"
            do_internal = True
        elif queueing_system == "AiiDA":
            queueing_system = "slurm"
            do_aiida = True
        elif queueing_system == "OnlyScript" or queueing_system == 'Filegenerator':
            queueing_system = "slurm"
            do_internal = True
            dont_run = True

        rootlogger = logging.getLogger('')
        rootlogger.addHandler(temphandler)
        try:
            import clusterjob
            #Sanity checks
            # check if runtime directory is not unset
            queue = actual_resources.queue

            kwargs = {}
            kwargs["queue"] = queue
            if queue is None or queue == "None" or queue == "":
                # In case of empty string or unset, we let clusterjob decide
                del kwargs["queue"]
            if queue  == "default" and queueing_system in ["pbs","slurm", "sge"]:
                # In case of pbs and slurm we let the queueing system decide:
                del kwargs["queue"]

            if actual_resources.custom_requests.strip() != "" and actual_resources.custom_requests != "None":
                #we expect stuff like:
                # -m "hostgroup1 hostgroup2", -B "fwiefj"
                c_requests = actual_resources.custom_requests
                crsplit = c_requests.strip().split(",")

                for field in crsplit:
                    splitfield = field.strip().split(" ")
                    if len(splitfield) < 2:
                        raise JobSubmitException("Could not interpret additional resource specifiers. They were: %s"%c_requests)
                    key = splitfield[0]
                    val = " ".join(splitfield[1:])
                    kwargs[key] = val

            mytime = actual_resources.walltime
            if mytime < 61:
                # We have to allocate at least 61 seconds
                # to work around the specificities of clusterjob.
                mytime = 61
            mytimestring = self._time_from_seconds_to_clusterjob_timestring(mytime)

            toexec = """%s
    cd $CLUSTERJOB_WORKDIR
    #LOCAL_EXEC_HOSTFILE_PLACEHOLDER
    %s
"""%(self._get_prolog_unicore_compatibility(actual_resources), self.exec_command)
            if queueing_system == "sge":
                kwargs["sge_pe"] = actual_resources.sge_pe
            try:
                jobscript = clusterjob.JobScript(toexec, backend=queueing_system, jobname = self.given_name,
                                                 time = mytimestring, nodes = int(actual_resources.nodes),
                                                 ppn = int(actual_resources.cpus_per_node), mem = actual_resources.memory,
                                                 stdout = self.given_name + ".stdout", stderr = self.given_name + ".stderr",
                                                 workdir = self.runtime_directory, **kwargs
                )


                #with open(self.runtime_directory + "/" + "jobscript.sh", 'wt') as outfile:
                #    outfile.write(str(jobscript)+ '\n')
                if not do_internal and not do_aiida:
                    asyncresult = jobscript.submit()
                    if asyncresult.status == FAILED:
                        queue_to_qsub = {
                            "lsf": "bsub",
                            "slurm": "sbatch",
                            "pbs": "qsub",
                            "sge": "qsub",
                            "sge_smp": "qsub"
                        }
                        myexe = queue_to_qsub[queueing_system]
                        exists = shutil.which(myexe)
                        if exists == None:
                            raise JobSubmitException("Did not find submission utility %s in path." %myexe)
                        raise JobSubmitException("Job failed immediately after submission.")
                    #self._async_result_workaround = asyncresult
                    self.set_jobid(asyncresult.job_id)
                elif do_aiida:
                    from aiida.orm import load_code
                    from aiida.plugins import CalculationFactory
                    from aiida.engine import submit
                    import aiida
                    valdict = self._aiida_valuedict
                    wano_name = valdict["wano_name"]
                    del valdict["wano_name"]
                    aiida.load_profile()
                    wano_code = load_code(label="wano-default-exec")
                    inputs =  {
                        'code': wano_code,
                        'metadata': {
                            'options': {
                                'withmpi': False,
                            }
                        }
                    }
                    aiida_resource_dict = {
                        'num_mpiprocs_per_machine': int(actual_resources.cpus_per_node),
                        'num_cores_per_mpiproc' : 1,
                        'num_machines': int(actual_resources.nodes)
                    }
                    inputs['metadata']['options']['resources'] = aiida_resource_dict

                    if not actual_resources.queue in ["default", "None", None]:
                        inputs['metadata']['options']['queue_name'] = actual_resources.queue

                    if actual_resources.queue != "default":
                        inputs['metadata']['options']['max_wallclock_seconds'] = int(actual_resources.walltime)
                    # We also need to set the env variables here
                    # i.e. Nanomatch
                    # UC_PROCESSORS_PER_NODE
                    envdict = {}
                    envdict["UC_NODES"] = str(actual_resources.nodes)
                    envdict["UC_PROCESSORS_PER_NODE"] =  str(actual_resources.cpus_per_node)
                    envdict["UC_TOTAL_PROCESSORS"] = str(actual_resources.cpus_per_node * actual_resources.nodes)
                    envdict["UC_MEMORY_PER_NODE"] = str(actual_resources.memory)
                    envdict["NANOMATCH"] = self._conda_base_prefix

                    inputs["metadata"]["options"]["exec_command"] = self.exec_command
                    inputs["metadata"]["options"]["environment_variables"] = envdict

                    inputs.update(self._aiida_valuedict)
                    output = submit(CalculationFactory(wano_name), **inputs)
                    jobid = output.uuid
                    self.set_jobid(jobid)
                else:

                    runscript = self.runtime_directory + "/" + "jobscript.sh"
                    hostfile = self.runtime_directory + "/" + "HOSTFILE"
                    with open(runscript, 'wt') as outfile:
                        outfile.write(str(jobscript).replace(
                            "$SLURM_SUBMIT_DIR",
                            self.runtime_directory
                        ).replace(
                            "#LOCAL_EXEC_HOSTFILE_PLACEHOLDER",
                            f"export HOSTFILE={hostfile}"
                        ) + '\n'
                    )
                    with open(hostfile, 'wt') as hoststream:
                        for i in range(0, actual_resources.cpus_per_node):
                            hoststream.write("localhost\n")
                    if not dont_run:
                        from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
                        batchsys, _ = InternalBatchSystem.get_instance()
                        jobid = batchsys.add_work_to_current_bracket(int(actual_resources.cpus_per_node),"smp",runscript)
                    else:
                        jobid = 1
                    self._logger.debug("Submitted as internal job %d"%jobid)
                    self.set_jobid(jobid)
                    ## In this case we need to grab jobid after submission and
            except Exception as e:
                server_submit_stderr = join(self.runtime_directory, "submission_failed.stderr")
                self._logger.error("Exception: %s. Writing traceback to: %s"%(e, server_submit_stderr))
                with open(server_submit_stderr,'wt') as outfile:
                    traceback.print_exc(file=outfile)
                    outfile.write("\n\n")
                    outfile.write("During this exception, the following events were logged:\n")
                    outfile.write(temphandler.getvalue())
                    outfile.write("End of Log\n")
                raise e from e
        finally:
            # We remove the handler
            rootlogger.removeHandler(temphandler)


    def abort_job(self):
        actual_resources = self.resources
        if not self.check_if_job_is_local():
            self._logger.info("Aborting job in non-local server.")
            from SimStackServer.ClusterManager import ClusterManager
            cm : ClusterManager = self._get_clustermanager_from_job()
            with cm.connection_context():
                cm.send_abortsinglejob_message(self.uid)



        elif actual_resources.queueing_system == "AiiDA":
            from SimStackServer.SimAiiDA.AiiDAJob import AiiDAJob
            myjob = AiiDAJob(self.jobid)
            myjob.kill()
        elif actual_resources.queueing_system != "Internal":
            asyncresult = self._recreate_asyncresult_from_jobid(self.jobid)
            try:
                asyncresult.status
                asyncresult.cancel()
            except ValueError as e:
                # In this case the job was most probably not known by the queueing system anymore.
                pass
            except FileNotFoundError as e:
                # In this case the queueing system was most probably wrong.
                pass
            except Exception as e:
                # This is a workaround, because we somehow cannot catch clusterjob exceptions
                if "StatusParseError" in type(e).__name__:
                    return True
                raise
        else:
            from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
            batchsys, _ = InternalBatchSystem.get_instance()
            batchsys.abort_job(self.jobid)

    def _recreate_asyncresult_from_jobid(self, jobid):
        actual_resources = self.resources
        assert not actual_resources.queueing_system == "Internal", "Recreating asyncresult from jobid not supported for Internal queueing system"
        # This function is a placeholder still. We need to generate the asyncresult just from the jobid.
        # It will require a modified clusterjob
        from clusterjob import AsyncResult, JobScript
        if len(JobScript._backends) == 0:
            a = JobScript("DummyJob")
            assert len(JobScript._backends) > 0

        ar = AsyncResult(JobScript._backends[actual_resources.queueing_system])
        ar.job_id = self.jobid
        from clusterjob.status import PENDING
        ar._status = PENDING
        return ar

    def set_queueing_system(self, queueing_system):
        self._field_values["queueing_system"] = queueing_system

    def set_path(self, path):
        self._field_values["path"] = path

    @property
    def path(self):
        return self._field_values["path"]

    @property
    def wano_xml(self):
        return self._field_values["wano_xml"]

    def set_wano_xml(self, wano_xml):
        self._field_values["wano_xml"] = wano_xml

    def set_outputpath(self, outputpath):
        self._field_values["outputpath"] = outputpath

    @property
    def outputpath(self):
        return self._field_values["outputpath"]

    def completed_or_aborted(self):
        actual_resources = self.resources
        if self._my_external_cluster_manager != None:
            from SimStackServer.ClusterManager import ClusterManager
            self._my_external_cluster_manager:ClusterManager
            with self._my_external_cluster_manager.connection_context():
                result = self._my_external_cluster_manager.send_jobstatus_message(wfem_uid = self.uid)
            status = result["status"]
            self._logger.debug(f"Job status reported as: {status}")
            if status in ["finished", "aborted"]:
                return True
            return False

        if not actual_resources.queueing_system in ["Internal", "AiiDA"] :
            try:
                asyncresult = self._recreate_asyncresult_from_jobid(self.jobid)
                return asyncresult.status >= 0
            except ValueError as e:
                # In this case the queueing system did not know about our job anymore. Return True
                return True # The job will be checked for actual completion anyways
            except Exception as e:
                # This is a workaround, because we somehow cannot catch clusterjob exceptions
                if "StatusParseError" in type(e).__name__:
                    return True
                raise

        elif actual_resources.queueing_system == "AiiDA":
            from SimStackServer.SimAiiDA.AiiDAJob import AiiDAJob
            myjob = AiiDAJob(self.jobid)
            status = myjob.status()
            if status in ["completed","cancelled","done","notfound","crashed","failed"]:
                return True
            return False
        else:
            from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
            batchsys, _ = InternalBatchSystem.get_instance()
            status = batchsys.jobstatus(self.jobid)
            #self._logger.info(f"BATCHSYSTEM STATUS WAS {status}")
            if status in ["completed","cancelled","done","notfound","crashed","failed"]:
                return True
            return False

    def get_output_variables(self, render_report = False):
        # In case somebody uploaded report_template.html, we render it:
        report_renderer = None
        if render_report:
            report_template = join(self.runtime_directory, "report_template.body")
            try:
                self._logger.debug("Rendering output: %s" % report_template)
                report_renderer = ReportRenderer.render_everything(self.runtime_directory, render_report)
            except Exception as e:
                self._logger.exception("Exception during report rendering.")

            pass
        if report_renderer is None:
            #This is the case in which rendering did not work or was not requested:
            try:
                report_renderer = ReportRenderer.render_everything(self.runtime_directory, False)
            except Exception as e:
                self._logger.exception("Could not create report_renderer for variable instruction. Something went very wrong.")
                raise WorkflowAbort("Could not create report_renderer for variable instruction. Something went very wrong.")

        if not report_renderer is None:
            self._rendered_body_html = report_renderer.get_body()
        else:
            self._rendered_body_html = ""

        return report_renderer.consolidate_export_dictionaries()

    def get_rendered_body_html(self):
        # We have to write this:
        """
            <details class="wano" open="">
              <summary>Epcot Center</summary>
              <p class="report">Epcot is a theme park at Walt Disney World
                Resort featuring exciting attractions, international pavilions,
                award-winning fireworks and seasonal special events.</p>
              <p class="files">Epcot is a theme park at Walt Disney World Resort
                featuring exciting attractions, international pavilions,
                award-winning fireworks and seasonal special events.</p>
              <p class="result">Epcot is a theme park at Walt Disney World
                Resort featuring exciting attractions, international pavilions,
                award-winning fireworks and seasonal special events.</p>
            </details>
        :return:
        """
        detail_html = etree.Element("details")
        myclass = "wano"
        if self.failed:
            myclass += " failed"

        detail_html.attrib["class"] = "wano "
        summary_html = etree.SubElement(detail_html, "summary")
        summary_html.text = self.given_name

        if self._rendered_body_html is None or self._rendered_body_html == "":
            pass
        else:
            #body_html = '<p class="report">%s</p>'%(self._rendered_body_html)
            body_html_parsed = lxml.html.fragment_fromstring(self._rendered_body_html, create_parent="p")
            body_html_parsed.attrib["class"] = "report"
            detail_html.append(body_html_parsed)

        result = etree.SubElement(detail_html, "p")
        result.attrib["class"] = "result"
        result.text = ""
        return detail_html

    @property
    def uid(self):
        return self._field_values["uid"]

    def set_runtime_directory(self, runtime_directory):
        self._field_values["runtime_directory"] = runtime_directory

    def set_external_runtime_directory(self, runtime_directory):
        self._field_values["external_runtime_directory"] = runtime_directory

    def set_jobid(self, jobid):
        self._field_values["jobid"] = jobid

    def set_given_name(self,given_name):
        self._field_values["given_name"] = given_name

    @property
    def given_name(self):
        return self._field_values["given_name"]

    @property
    def resources(self):
        return self._field_values["resources"]

    @property
    def inputs(self):
        return self._field_values["inputs"]

    @property
    def outputs(self):
        return self._field_values["outputs"]

    @property
    def name(self):
        return self._name

    @property
    def exec_command(self):
        return self._field_values["exec_command"]

    def set_exec_command(self, exec_command):
        self._field_values["exec_command"] = exec_command

    @property
    def jobid(self):
        return self._field_values["jobid"]

    @property
    def runtime_directory(self):
        return self._field_values["runtime_directory"]

    @property
    def external_runtime_directory(self):
        return self._field_values["external_runtime_directory"]

    def set_aiida_valuedict(self, aiida_valuedict):
        self._aiida_valuedict = aiida_valuedict

    def get_aiida_valuedict(self, aiida_valuedict):
        assert self._aiida_valuedict is not None, "AiiDA value dict was not generated before query."
        return self._aiida_valuedict

    @property
    def original_result_directory(self):
        return self._field_values["original_result_directory"]
    
    def set_original_result_directory(self, directory_path):
        self._field_values["original_result_directory"] = directory_path

class DirectedGraph(object):
    def __init__(self, *args, **kwargs):
        self._graph = nx.DiGraph()
        self._default_node_attributes = { "status" : "waiting" }
        self._logger = logging.getLogger("WFGraph")

        #I only collect chose to check
        all_node_ids = set()
        for element in args:
            if isinstance(element,list):
                for fromid, toids in element:
                    all_node_ids.add(fromid)
                    if isinstance(toids, list):
                        for toid in toids:
                            self._graph.add_edge(fromid,toid)
                            all_node_ids.add(toid)
                    else:
                        self._graph.add_edge(fromid,toids)
                        all_node_ids.add(toids)

        status_dict = {}
        #for node in all_node_ids:
        #    status_dict[node] = "unstarted"
        #    nx.set_node_attributes(self._graph, status_dict, "status")

        #for node in nx.dfs_tree(self._graph):
        #   all_node_ids.remove(node)
        #    # All nodes have to be reached via a DFS
        # The code above was removed, because of the ForEach implementation. Now the graph will have breaks on each foreach

        self._init_graph_to_unstarted()

    def _init_graph_to_unstarted(self):
        for node in self._graph:
            self._graph.nodes[node]["status"] = "unstarted"

    def add_new_unstarted_connection(self, connection_tuple):
        """

        :param connection_tuple tuple(int,int): From To, nodes will be added if not present. Nodes will be unstarted, if not new
        :return:
        """
        nodefrom = connection_tuple[0]
        nodeto = connection_tuple[1]
        for node in [nodefrom,nodeto]:
            if not self._graph.has_node(node):
                self._graph.add_node(node)
                self._graph.nodes[node]["status"] = "unstarted"
        self._graph.add_edge(nodefrom,nodeto)

    def merge_other_graph(self, other_graph):
        self._graph = nx.compose(other_graph._graph, self._graph)

    def rename_all_nodes(self, explicit_overrides = None):
        if explicit_overrides is None:
            explicit_overrides = {}
        allnodename = list(self._graph.nodes)
        newnames = []
        rename_dict = {}
        for i,oldnodename in enumerate(allnodename):
            if oldnodename in explicit_overrides:
                rename_dict[oldnodename] = explicit_overrides[oldnodename]
            else:
                rename_dict[oldnodename] = str(uuid.uuid4())
        #inplace relabel nodes
        nx.relabel_nodes(self._graph,rename_dict,copy=False)
        return rename_dict

    def get_running_jobs(self):
        outnodes = [ node for node in self._graph if self._graph.nodes[node]["status"] == "running"]
        return outnodes

    def get_success_jobs(self):
        outnodes = [ node for node in self._graph if self._graph.nodes[node]["status"] == "success"]
        return outnodes

    def get_failed_jobs(self):
        outnodes = [node for node in self._graph if self._graph.nodes[node]["status"] == "failed"]
        return outnodes

    def get_success_failed_running_jobs(self):
        return self.get_success_jobs(), self.get_failed_jobs(), self.get_running_jobs()

    def start(self, node):
        assert self._graph.nodes[node]["status"] == "ready"
        self._graph.nodes[node]["status"] = "running"

    def finish(self, node):
        assert self._graph.nodes[node]["status"] == "running"
        self._graph.nodes[node]["status"] = "success"

    def fail(self, node):
        self._graph.nodes[node]["status"] = "failed"

    def is_workflow_finished(self):
        outnodes = [ node for node in self._graph if self._graph.nodes[node]["status"] != "success" ]
        return len(outnodes) == 0

    def to_xml(self, parent_element):
        toparse = "".join(nx.generate_graphml(self._graph))
        myetree = etree.fromstring(toparse)
        parent_element.append(myetree)

    def to_dict(self, parent_dict):
        parent_dict["graphml"] = nx.to_dict_of_dicts(self._graph)

    def from_dict(self, input_dict):
        self._graph = nx.from_dict_of_dicts(input_dict["graphml"])

    def from_xml(self, input_xml):
        found = False
        #print(etree.tostring(input_xml,encoding="utf8"))
        for child in input_xml:
            if child.tag == "{http://graphml.graphdrawing.org/xmlns}graphml":
                found = True
                etreestring = etree.tostring(child, encoding="utf8").decode()
                sio = StringIO(etreestring)
                self._graph = nx.read_graphml(sio)
                break
        if not found:
            raise ParserError("No graph element found.")

    def report_order_generator(self):
        nodes = self._graph.nodes
        for a in nx.bfs_tree(self._graph, "0"):
            yield a

    def get_next_ready(self):
        nodes = self._graph.nodes

        for a in nx.dfs_tree(self._graph):
            if a == "0":
                nodes[a]["status"] = "success"
            if nodes[a]["status"] == "unstarted":
                candidate = True
                self._logger.debug("%s was unstarted. Testing ready"%a)
                predecessors = self._graph.predecessors(a)
                foundpred = False
                for pred in predecessors:
                    foundpred = True
                    self._logger.debug("pred %s status: %s"%(pred,nodes[pred]["status"]))
                    if nodes[pred]["status"] != "success":
                        candidate = False
                        break
                    #print("%d was preceeded by %d"%(a,pred))
                if foundpred is False:
                    self._logger.debug("No predecessor found for %s. Skipping"%a)
                    continue

                if candidate:
                    self._logger.debug("%s setting to ready"%a)
                    nodes[a]["status"] = "ready"

        for node in self._graph:
            self._logger.debug("Outnode %s was ready." %node)
        outnodes = [ node for node in self._graph if self._graph.nodes[node]["status"] == "ready"]
        return outnodes

    def traverse(self):
        for a in nx.dfs_tree(self._graph):
            print(a)

class WorkflowAbort(Exception):
    pass

class SubGraph(XMLYMLInstantiationBase):
    _fields = [
        ("elements", WorkflowElementList, None, "List of Linear Workflow Elements (this can also be fors or splits)","m"),
        ("graph", DirectedGraph, None,
         "Directed Graph of all Elements. All elements in elements have to be referenced here."
         "There must not be cycles (we should check this). In case an element is a ForEach or "
         "another workflow this workflow does not need to be encoded here.", "m")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "SubGraph"
        self._logger = logging.getLogger("SubGraph")

    def fields(cls):
        return cls._fields

    @property
    def elements(self) -> WorkflowElementList:
        return self._field_values["elements"]

    def fill_in_variables(self, vardict):
        for element in self.elements:
            element.fill_in_variables(vardict)

    @property
    def graph(self) -> DirectedGraph:
        return self._field_values["graph"]

    def rename_all_nodes(self, explicit_overrides = None) -> dict:
        if explicit_overrides is None:
            explicit_overrides = {}
        rename_dict = self.graph.rename_all_nodes(explicit_overrides)
        for val in rename_dict.keys():
            assert val not in self.graph._graph.nodes, "Found reference to old node in graph, which should not be there."

        for element in self.elements:
            if hasattr(element, "rename"):
                element.rename(rename_dict)
            else:
                self._logger.warning("Element %s does not have explicit rename function yet. Please add even if empty."%type(element))
        return rename_dict


class IfGraph(XMLYMLInstantiationBase):
    _fields = [
        ("truegraph", SubGraph, None, "Graph to instantiate If in case condition is true", "m"),
        ("falsegraph", SubGraph, None, "Graph to instantiate If in case condition is false", "m"),
        ("true_final_ids", StringList, [], "These are the final uids of the subgraph. Required for linking copies of the subgraph.", "m"),
        ("false_final_ids", StringList, [],"These are the final uids of the subgraph. Required for linking copies of the subgraph.", "m"),
        ("finish_uid", str, "", "UID, which will be completed, once IfGraph is completed. Every subgraph will link to this node","a"),
        ("condition", str, "", "Condition, which evaluates to true or false", "a"),
        ("uid", str, "", "UID of this Foreach","a")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "IfGraph"
        self._logger = logging.getLogger("IfGraph")

    def fill_in_variables(self, vardict):
        self._field_values["true_final_ids"].fill_in_variables(vardict)
        self._field_values["false_final_ids"].fill_in_variables(vardict)
        self.truegraph.fill_in_variables(vardict)
        self.falsegraph.fill_in_variables(vardict)
        for key,value in vardict.items():
            if key.startswith("${"):
                self._field_values["condition"] = self._field_values["condition"].replace(key,value)

    @property
    def true_final_ids(self) -> StringList:
        return self._field_values["true_final_ids"]

    def rename(self, renamedict):
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s" % (myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

        # If we were linked to, our finish uid is rewritten externally, otherwise we have to provide our own
        # new finish uuid
        finish_uid = self.finish_uid
        if finish_uid in renamedict:
            self._field_values["finish_uid"] = renamedict[finish_uid]
        else:
            newuid = uuid.uuid4()
            self._field_values["finish_uid"] = newuid
            renamedict[finish_uid] = newuid

    @property
    def false_final_ids(self) -> StringList:
        return self._field_values["false_final_ids"]

    def resolve_connect(self, base_storage, input_variables, output_variables):
        condition = self.condition
        for vardict in output_variables, input_variables:
            for key in sorted(vardict, key=len, reverse = True):
                item = vardict[key]
                try:
                    int(item)
                    float(item)
                except ValueError as e:
                    #if its not int or float, we assume it is string
                    item = '"%s"'%str(item)
                condition = condition.replace(key, str(item))
        from ast import literal_eval
        self._logger.info("Condition %s resolved to %s"%(self.condition, condition))
        #outcome = literal_eval(condition)
        try:
            outcome = eval(condition)
        except (NameError,SyntaxError) as e:
            self._logger.exception("Exception during evaluation of condition.")
            self._logger.error("Variables during exception were:")
            self._logger.error("Input var: {0}".format(input_variables))
            self._logger.error("Output var: {0}".format(output_variables))
            raise WorkflowAbort from e

        if type(outcome) != bool:
            raise WorkflowAbort("Condition %s was resolved to %s of type: %s"%(condition, outcome, type(outcome)))
        return self._connect_subgraph(outcome)

    def _connect_subgraph(self, condition_is_true_or_false):
        if condition_is_true_or_false:
            mygraph = copy.deepcopy(self.truegraph)
            final_ids = self.true_final_ids
        else:
            mygraph = copy.deepcopy(self.falsegraph)
            final_ids = self.false_final_ids

        override = {"temporary_connector": self.uid}
        rename_dict = mygraph.rename_all_nodes(explicit_overrides=override)

        new_connections = []
        if not "temporary_connector" in rename_dict:
            raise WorkflowAbort("mygraph did not contain start id temporary_connector. Renamed keys were: %s" % (
                ",".join(rename_dict.keys())))
        for uid in final_ids:
            if not uid in rename_dict:
                raise WorkflowAbort(
                    "mygraph did not contain final id %s. Renamed keys were: %s" % (uid,",".join(rename_dict.keys())))
        for uid in final_ids:
            new_connections.append((rename_dict[uid],self.finish_uid))

        # At this point new_connection should contain all renamed connections to integrate subgraph.elements in the basegraph
        # we return all subgraph.elements and all connections and get this communicated into the base graph
        return new_connections, [mygraph.elements], [mygraph.graph]

    @property
    def finish_uid(self) -> str:
        return self._field_values["finish_uid"]

    @property
    def uid(self):
        return self._field_values["uid"]

    @property
    def truegraph(self) -> SubGraph:
        return self._field_values["truegraph"]

    @property
    def falsegraph(self) -> SubGraph:
        return self._field_values["falsegraph"]

    @property
    def condition(self) -> str:
        return self._field_values["condition"]

    def fields(cls):
        return cls._fields

class ForEachGraph(XMLYMLInstantiationBase):
    _fields = [
        ("subgraph", SubGraph, None, "Graph to instantiate For Each Element","m"),
        ("iterator_files", StringList, [], "Files and globpatterns to iterate over", "m"),
        ("iterator_variables", StringList, [], "Variables, which have to be iterated over", "m"),
        ("iterator_definestring", str, "", "String, which defines variable iterators", "m"),
        ("iterator_name", str, "", "Name of my iterator", "a"),
        #("parent_ids", StringList, [] , "Before a single job in this foreach starts, parent_ids has to be fulfilled","m"),
        ("subgraph_final_ids", StringList, [], "These are the final uids of the subgraph. Required for linking copies of the subgraph.", "m"),
        ("finish_uid", str, "", "UID, which will be completed, once ForEachGraph is completed. Every subgraph will link to this node","a"),
        ("uid", str, "", "UID of this Foreach","a")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "ForEachGraph"
        self._logger = logging.getLogger("ForEachGraph")

    @property
    def iterator_name(self) -> str:
        return self._field_values["iterator_name"]

    @property
    def iterator_files(self) -> StringList:
        return self._field_values["iterator_files"]

    @property
    def iterator_variables(self) -> StringList:
        return self._field_values["iterator_variables"]

    @property
    def iterator_definestring(self) -> str:
        return self._field_values["iterator_definestring"]

    def fill_in_variables(self, vardict):
        self._field_values["subgraph"].fill_in_variables(vardict)
        for key, value in vardict.items():
            self._field_values["iterator_definestring"] = self._field_values["iterator_definestring"].replace(str(key),str(value))

    @property
    def subgraph_final_ids(self) -> StringList:
        return self._field_values["subgraph_final_ids"]

    def resolve_connect(self, base_storage, input_variables, output_variables):
        allvars = []
        if len(self.iterator_files) != 0:
            allvars = self._resolve_file_iterator(base_storage)
            iterator_names = [self.iterator_name]
        elif len(self.iterator_variables) != 0:
            allvars = self._resolve_variable_iterator(input_variables, output_variables)
            iterator_names = [self.iterator_name]
        elif self.iterator_definestring != "":
            # TODO: continue here
            iterator_names, allvars = self._resolve_multivar_iterator(input_variables, output_variables)
        if len(allvars) == 0:
            self._logger.warning("Empty variable iterator. Skipping ForEach.")
        return self._multiply_connect_subgraph(iterator_names, allvars)

    def _resolve_multivar_iterator(self, input_variables, output_variables):
        iterator_names = self.iterator_name.replace(" ", "").split(",")
        num_iters = len(iterator_names)
        results = []
        expression = self.iterator_definestring
        for key, value in output_variables.items():
            expression = expression.replace(str(key), str(value))
        for key, value in input_variables.items():
            expression = expression.replace(str(key), str(value))
        iteresult_generator = eval_numpyexpression(expression)
        for result in iteresult_generator:
            if num_iters > 1:
                if len(result) != num_iters:
                    raise WorkflowAbort("Define iterators cannot be unpacked")
            # We unpack the iterator here to have actual lists and check for the correct sizing
            results.append(result)
        return iterator_names, results


    def _resolve_file_iterator(self, base_storage):
        relfiles = self.iterator_files
        allfiles = []
        for myfile_rel in relfiles:
            myfile = join(base_storage,myfile_rel)
            isglob = "*" in myfile
            if isglob:
                allfiles += glob(myfile)
            else:
                allfiles += [myfile]
            self._logger.info("Iterating over %s when looking for %s."% (", ".join([str(e) for e in allfiles]), myfile  ))
        base_store_len = len(base_storage)
        # We want to resolve this iterator relative to base_storage:
        allfiles = [myfile[base_store_len:] for myfile in allfiles]
        return allfiles

    def _resolve_variable_iterator(self, input_variables, output_variables):
        relvars = self.iterator_variables

        assert len(relvars) == 1
        myvar = relvars[0]
        asteriskvar = myvar.replace("*","[^.]+")
        asteriskvar = "^%s$"%asteriskvar
        myregex = re.compile(asteriskvar)
        outvars = []
        for var in input_variables.keys():
            result = myregex.match(var)
            if result is not None:
                outvars.append(var)

        for var in output_variables.keys():
            result = myregex.match(var)
            if result is not None:
                outvars.append(var)

        # In case we did not find explicit matches, the user might have requested to import a dictionary.

        if len(outvars) == 0:
            resultvarset = set()

            asteriskvar = myvar.replace("*","[^.]+")
            # we only check if the start matches:
            asteriskvar = "^%s"%asteriskvar
            myregex = re.compile(asteriskvar)

            for var in input_variables.keys():
                result = myregex.match(var)
                if result is not None:
                    resultvarset.add(result.group())

            for var in output_variables.keys():
                result = myregex.match(var)
                if result is not None:
                    resultvarset.add(result.group())

            outvars = list(resultvarset)

        # This function will do a list of all matched variables
        return outvars

    def _multiply_connect_subgraph(self, iterator_names, resolved_files):
        #duplicate this and iterate over multi_iterator
        new_connections = []
        new_activity_elementlists = []
        new_graphs = []
        comma_iter_name = ",".join(iterator_names).replace(" ","")
        comma_iter_name = "${%s_ITER}"%comma_iter_name
        for iterator_value, myvalues in enumerate(resolved_files):
            mygraph = copy.deepcopy(self.subgraph)
            print("Entering with ",myvalues)

            if isinstance(myvalues, tuple):
                myvalues = list(myvalues)
            if not isinstance(myvalues, list):
                myvalues = [myvalues]
            if len(myvalues) != len(iterator_names):
                out = StringIO()
                out.write("Mismatch between iterator values and number of declared iterators.")
                out.write("Values were: %s" %str(myvalues))
                out.write("Names were: %s" % str(iterator_names))
                raise WorkflowAbort(out.getvalue())
            #comma_iter_vals = ",".join([str(value) for value in myvalues])
            replacedict = { comma_iter_name : str(iterator_value) }

            for iterator_name, myvalue in zip(iterator_names, myvalues):
                updatedict = {
                    "${%s}"%iterator_name :str(myvalue),
                    #"${%s_ITER}"%iterator_name : str(iterator_value)
                }
                replacedict.update(updatedict)

            # We rename temporary connector to us. Like this we don't have to remove temporary connector in the end.
            override = {"temporary_connector": self.uid}
            rename_dict = mygraph.rename_all_nodes(explicit_overrides=override)
            if not "temporary_connector" in rename_dict:
                raise WorkflowAbort("mygraph did not contain start id temporary_connector. Renamed keys were: %s"%(",".join(rename_dict.keys())))


            mygraph.fill_in_variables(replacedict)

            for uid in self.subgraph_final_ids:
                if not uid in rename_dict:
                    raise WorkflowAbort(
                        "mygraph did not contain final id %s. Renamed keys were: %s" % (uid,",".join(rename_dict.keys())))
            for uid in self.subgraph_final_ids:
                new_connections.append((rename_dict[uid],self.finish_uid))

            new_activity_elementlists.append(mygraph.elements)
            new_graphs.append(mygraph.graph)
            # At this point new_connection should contain all renamed connections to integrate subgraph.elements in the basegraph
            # we return all subgraph.elements and all connections and get this communicated into the base graph
        return new_connections, new_activity_elementlists, new_graphs

    @property
    def finish_uid(self) -> str:
        return self._field_values["finish_uid"]

    #@property
    #def parent_ids(self) -> str:
    #    return self._field_values["parent_ids"]

    def rename(self, renamedict):
        # First we rename our own uid:
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

        # If we were linked to, our finish uid is rewritten externally, otherwise we have to provide our own
        # new finish uuid
        finish_uid = self.finish_uid
        if finish_uid in renamedict:
            self._field_values["finish_uid"] = renamedict[finish_uid]
        else:
            newuid = uuid.uuid4()
            self._field_values["finish_uid"] = newuid
            renamedict[finish_uid] = newuid
        # We should not rename_all_nodes in subgraph here. Subgraph will be resolved again, when resolve_connect is done
        # Variable replacements are in fill_in_variables

    @property
    def uid(self):
        return self._field_values["uid"]

    @property
    def subgraph(self) -> SubGraph:
        return self._field_values["subgraph"]

    def fields(cls):
        return cls._fields


class WhileGraph(XMLYMLInstantiationBase):
    _fields = [
        ("subgraph", SubGraph, None, "Graph to instantiate For Each Element","m"),
        ("iterator_name", str, "", "Name of my iterator", "a"),
        ("subgraph_final_ids", StringList, [], "These are the final uids of the subgraph. Required for linking copies of the subgraph.", "m"),
        ("finish_uid", str, "", "UID, which will be completed, once ForEachGraph is completed. Every subgraph will link to this node","a"),
        ("condition", str, "", "Condition, which evaluates to true or false", "a"),
        ("current_id", np.int64, 0, "Value of current iterator", "a"),
        ("uid", str, "", "UID of this Foreach","a")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "WhileGraph"
        self._logger = logging.getLogger("WhileGraph")

    @property
    def iterator_name(self) -> str:
        return self._field_values["iterator_name"]

    @property
    def current_id(self) -> np.int64:
        return self._field_values["current_id"]

    def fill_in_variables(self, vardict):
        self._field_values["subgraph"].fill_in_variables(vardict)

    @property
    def subgraph_final_ids(self) -> StringList:
        return self._field_values["subgraph_final_ids"]

    def rename(self, renamedict):
        # First we rename our own uid:
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

        # If we were linked to, our finish uid is rewritten externally, otherwise we have to provide our own
        # new finish uuid
        finish_uid = self.finish_uid
        if finish_uid in renamedict:
            self._field_values["finish_uid"] = renamedict[finish_uid]
        else:
            newuid = uuid.uuid4()
            self._field_values["finish_uid"] = newuid
            renamedict[finish_uid] = newuid
        # We should not rename_all_nodes in subgraph here. Subgraph will be resolved again, when resolve_connect is done
        # Variable replacements are in fill_in_variables

    def resolve_connect(self, base_storage, input_variables, output_variables):
        condition = self.condition
        replacedict = {
            "${%s_ITER}"%self.iterator_name : self.current_id,
            "${%s}"%self.iterator_name : self.current_id
            #"%s_VALUE"%self.iterator_name : self.current_id,
            #"%s"%self.iterator_name : self.current_id
        }
        input_variables.update(replacedict)
        # Replacedict has to be done both in input_vars and first, because when replacing the iterators, this might resolve to a variable name, inside input vars.
        for vardict in replacedict, output_variables, input_variables:
            for key, item in vardict.items():
                try:
                    int(item)
                    float(item)
                except ValueError as e:
                    #if its not int or float, we assume it is string
                    item = '"%s"'%str(item)
                condition = condition.replace(key, str(item))
        from ast import literal_eval
        self._logger.info("While Condition %s resolved to %s"%(self.condition, condition))
        #outcome = literal_eval(condition)
        try:
            outcome = eval(condition)
        except (NameError,SyntaxError) as e:
            self._logger.exception("Exception during evaluation of condition.")
            self._logger.error("Variables during exception were:")
            self._logger.error("Input var: {0}".format(input_variables))
            self._logger.error("Output var: {0}".format(output_variables))
            raise WorkflowAbort from e
        if type(outcome) != bool:
            raise WorkflowAbort("While Condition %s was resolved to %s of type: %s"%(condition, outcome, type(outcome)))
        return self._multiply_connect_subgraph(condition_is_true_or_false = outcome)

    def _multiply_connect_subgraph(self,condition_is_true_or_false):

        # We copy the graph once:
        mygraph = copy.deepcopy(self.subgraph)
        replacedict = {
            "${%s_ITER}"%self.iterator_name : str(self.current_id),
            "${%s}"%self.iterator_name : str(self.current_id)
            #"%s_VALUE"%self.iterator_name :str(self.current_id),
            #"%s"%self.iterator_name : str(self.current_id)
        }
        mygraph.fill_in_variables(replacedict)
        # We rename temporary connector to us. Like this we don't have to remove temporary connector in the end.
        nextgraph = WhileGraph(subgraph = self.subgraph,
                               iterator_name = self.iterator_name,
                               subgraph_final_ids = self.subgraph_final_ids,
                               finish_uid = self.finish_uid,
                               condition = self.condition,
                               current_id = 1 + self.current_id)

        nextgraph_elelist = WorkflowElementList([("WhileGraph",nextgraph)])
        override = {"temporary_connector": self.uid}
        rename_dict = mygraph.rename_all_nodes(explicit_overrides=override)
        if not "temporary_connector" in rename_dict:
            raise WorkflowAbort("mygraph did not contain start id temporary_connector. Renamed keys were: %s"%(",".join(rename_dict.keys())))

        for uid in self.subgraph_final_ids:
            if not uid in rename_dict:
                raise WorkflowAbort(
                    "mygraph did not contain final id %s. Renamed keys were: %s" % (uid,",".join(rename_dict.keys())))

        if condition_is_true_or_false:
            for uid in self.subgraph_final_ids:
                mygraph.graph.add_new_unstarted_connection((rename_dict[uid],nextgraph.uid))

            #We manage new connections above already
            new_connections = []

            new_activity_elementlists = []
            new_graphs = [mygraph.graph]
            new_activity_elementlists.append(mygraph.elements)
            new_activity_elementlists.append(nextgraph_elelist)
        else:
            new_graphs = []
            new_activity_elementlists = []
            # We don't add anything and link from us to finish uid.
            new_connections = [(self.uid, self.finish_uid)]

        return new_connections, new_activity_elementlists, new_graphs

    @property
    def finish_uid(self) -> str:
        return self._field_values["finish_uid"]

    @property
    def uid(self):
        return self._field_values["uid"]

    @property
    def subgraph(self) -> SubGraph:
        return self._field_values["subgraph"]

    @property
    def condition(self) -> str:
        return self._field_values["condition"]

    def fields(cls):
        return cls._fields


class VariableElement(XMLYMLInstantiationBase):
    _fields = [
        ("variable_name", str, "", "Name of this variable", "a"),
        ("equation", str, "", "Equation to set the new variable to", "a"),
        ("uid", str, "", "UID of this variable setter element.","a")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "VariableElement"
        self._logger = logging.getLogger("VariableElement")

    @property
    def equation(self) -> str:
        return self._field_values["equation"]

    def rename(self, renamedict):
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

    @property
    def variable_name(self) -> str:
        return self._field_values["variable_name"]

    def fill_in_variables(self, vardict):
        pass

    def evaluate_equation(self, input_variables, output_variables):
        equation = self.equation
        for vardict in [input_variables, output_variables]:
            for myvar, item in vardict.items():
                try:
                    int(item)
                    float(item)
                except ValueError as e:
                    #if its not int or float, we assume it is string
                    item = '"%s"'%str(item)
                equation = equation.replace(myvar, str(item))
        try:
            print("Evaluating",equation)
            print(input_variables, output_variables)
            result = eval(equation)
        except (NameError,SyntaxError) as e:
            self._logger.exception("Exception during evaluation of condition.")
            self._logger.error("Variables during exception were:")
            self._logger.error("Input var: {0}".format(input_variables))
            self._logger.error("Output var: {0}".format(output_variables))
            raise WorkflowAbort from e

        return result

    @property
    def subgraph_final_ids(self) -> StringList:
        return self._field_values["subgraph_final_ids"]

    @property
    def uid(self):
        return self._field_values["uid"]

    def fields(cls):
        return cls._fields



class WFPass(XMLYMLInstantiationBase):
    _fields = [
        ("uid", str, None, "uid of this WorkflowExecModule.", "a")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self.name = "WFPass"

    def fields(cls):
        return cls._fields

    @property
    def uid(self):
        return self._field_values["uid"]

    def rename(self, renamedict):
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid


class WorkflowBase(XMLYMLInstantiationBase):
    _fields = [
        ("elements", WorkflowElementList, None, "List of Linear Workflow Elements (this can also be fors or splits)", "m"),
        ("graph", DirectedGraph, None, "Directed Graph of all Elements. All elements in elements have to be referenced here."
                                       "There must not be cycles (we should check this). In case an element is a ForEach or "
                                       "another workflow this workflow does not need to be encoded here." , "m"),
        ("storage", str, "",            "Path to the storage directory assigned by the workflow client.", "a"),
        ("name", str, "Workflow", "Name of this workflow. Something like Hans or Fritz.", "a"),
        ("submit_name", str, "${SUBMIT_NAME}", "The name this workflow was submitted as. This has to be unique on the cluster (per user). The workflow will be rejected if its not.", "a"),
        ("status", int , JobStatus.READY, "Last checked status of the workflow", "a"),
        ("queueing_system",str, "unset", "Only present for legacy purposes. Do not use.", "a")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "Workflow"
        self._logger = logging.getLogger("Workflow")

    def _abs_resolve_storage(self):
        if not self.storage.startswith('/'):
            home = str(Path.home())
            self._field_values["storage"] = home + '/' + self._field_values["storage"]

    def fields(cls):
        return cls._fields

    @staticmethod
    def _get_template_dir():
        data_dir = os.path.dirname(os.path.realpath(Templates.__file__))
        return data_dir

    @property
    def queueing_system(self) -> str:
        return self._field_values["queueing_system"]


    def from_xml(self, in_xml):
        super().from_xml(in_xml)

    def from_dict(self, in_dict):
        super().from_dict(in_dict)

    def finalize(self):
        html_doc = """<!DOCTYPE html>
<html lang="en-us">
<head>
%s
</head>
<body>
<li class="indent">
%s
</li>
</body>
</html>
"""

        outstring_body = """"""
        headfile = join(self._get_template_dir(), "head.html")
        with open(headfile, "r") as headin:
            head = headin.read()

        for node in self.graph.report_order_generator():

            try:
                myelement = self.elements.get_element_by_uid(node)

                cp = path.commonprefix([self.storage, myelement.runtime_directory])
                relruntimedir = myelement.runtime_directory[len(cp):]
                if relruntimedir.startswith("/"):
                    relruntimedir = relruntimedir[1:]
                myelement:WorkflowExecModule
                body_html = myelement.get_rendered_body_html()
                # Here we rewrite sources:
                for element in body_html.iter():
                    for atr in ["src", "href"]:
                        if atr in element.attrib:
                            content = element.attrib[atr]
                            if content.startswith("http") or content.startswith("/"):
                                continue
                            else:
                                element.attrib[atr] = relruntimedir + "/" + content

                    body_html.iter()
                single_element = etree.tounicode(body_html, pretty_print=True, method="html")
                outstring_body+= """  <ul>
                   %s
                </ul>
                """ %single_element
            except KeyError:
                pass
            except AttributeError:
                # runtime directory is not setup upstairs everywhere
                pass
            except Exception as e:
                self._logger.exception("Exception during report rendering. Skipping.")
        html_doc = html_doc%(head, outstring_body)
        reportname = join(self.storage, "workflow_report.html")
        with open(reportname, 'w') as outfile:
            outfile.write(html_doc)

    @abc.abstractmethod
    def abort(self):
        self._field_values["status"] = JobStatus.ABORTED
        #This function has to be called from the child class

    @abc.abstractmethod
    def delete(self):
        self._field_values["status"] = JobStatus.MARKED_FOR_DELETION
        #This function has to be called from the child class

    def _stage_file(self,fromfile,tofile):
        # At the moment this should only be a cp, but later it can also be a scp
        shutil.copyfile(fromfile, tofile)

    def _get_job_directory(self, wfem: WorkflowExecModule):
        now = datetime.datetime.now()
        nowstr = now.strftime("%Y-%m-%d-%Hh%Mm%Ss")

        submitname = "%s-%s" %(nowstr, wfem.given_name)
        return submitname

    def get_filename(self):
        return path.join(self.storage, "rendered_workflow.xml")

    def to_xml(self, parent_element):
        self._field_values["status"] = int(self._field_values["status"])
        super().to_xml(parent_element)

    def to_dict(self, parent_dict):
        self._field_values["status"] = int(self._field_values["status"])
        super().to_dict(parent_dict)

    @property
    def elements(self) -> WorkflowElementList:
        return self._field_values["elements"]

    @property
    def graph(self) -> DirectedGraph:
        return self._field_values["graph"]

    @property
    def storage(self) -> str:
        return self._field_values["storage"]

    @property
    def name(self) -> str:
        return self._field_values["name"]

    @property
    def submit_name(self) -> str:
        return self._field_values["submit_name"]

    @property
    def status(self) -> str:
        return self._field_values["status"]

    def set_queueing_system(self, queueing_system):
        self._field_values["queueing_system"] = queueing_system

    @abc.abstractmethod
    def all_job_abort(self):
        raise NotImplementedError("Has to be implemented in child class")

    @abc.abstractmethod
    def delete_storage(self):
        raise NotImplementedError("Has to be implemented in child class")

    @abc.abstractmethod
    def jobloop(self):
        raise NotImplementedError("Has to be implemented in child class")

    @abc.abstractmethod
    def get_running_finished_job_list_formatted(self):
        raise NotImplementedError("Has to be implemented in child class")

class ReportCollector:
    def __init__(self):
        self._parents_by_uid = {}

    def announce_report(self, uid, parent_uid):
        self._parents_by_uid[uid] = parent_uid


class Workflow(WorkflowBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "Workflow"
        self._logger = logging.getLogger("Workflow")
        self._input_variables = {}
        self._output_variables = {}
        self._prepared_aiida_variables = None
        self._report_collector = None
        # self._report_collector  should record uids, when they happen and there place during execution
        # Assembly then knows their uid.
        self._path_to_aiida_uuid = {}
        self._filepath_to_aiida_uuid = {}
        from SimStackServer.RemoteServerManager import RemoteServerManager
        self._remote_server_manager = RemoteServerManager.get_instance()
        self._result_repo = ResultRepo()
        self._input_hashes = {}

    def all_job_abort(self):
        for job in self.graph.get_running_jobs():
            myjob = self.elements.get_element_by_uid(job)
            myjob: WorkflowExecModule
            myjob.abort_job()
            self.graph.fail(job)
            myjob.set_failed()

    def set_storage(self, path: pathlib.Path):
        self._field_values["storage"] = str(path.as_posix())

    def _check_if_job_is_local(self, job: WorkflowExecModule):
        return job.check_if_job_is_local()

    def _get_clustermanager_from_job(self, job: WorkflowExecModule):
        return self._remote_server_manager.server_from_resource(job.resources)

    def delete_storage(self):
        """
        This routine deletes all files this workflow has generated.
        It must not delete storage with a rm -r.
        It must only delete subfolder with rm -r, as otherwise a user could set storage = '/' and screw himself.
        :return:
        """

        exec_dir_path = join(self.storage,"exec_directories")
        workflow_data_path = join(self.storage,"workflow_data")
        rendered_workflow_path = join(self.storage,"rendered_workflow.xml")
        rendered_report_path = join(self.storage, "workflow_report.html")
        shutil.rmtree(exec_dir_path,ignore_errors=True)
        shutil.rmtree(workflow_data_path, ignore_errors=True)
        try:
            os.remove(rendered_workflow_path)
            os.remove(rendered_report_path)
        except FileNotFoundError as e:
            pass
        try:
            os.rmdir(self.storage)
        except (OSError, FileNotFoundError) as e:
            pass

    def jobloop(self):
        running_jobs = self.graph.get_running_jobs()
        secure_mode = SecureModeGlobal.get_secure_mode()

        if self.status == JobStatus.ABORTED:
            """
            for running_job in running_jobs:
                running_job : AsyncResult
                running_job.cancel()
            """
            return True
 
        for running_job in running_jobs:
            running = self.elements.get_element_by_uid(running_job)
            running : WorkflowExecModule
            if running.completed_or_aborted():
                try:
                    wfvars = self._postjob_care(running)
                    self.graph.finish(running_job)
                    print("Finished ",running_job)

                    if running.uid not in self._input_hashes:
                        self._logger.warning(f"[REPO] Result of {running} could not be stored in result database because its hash was not \
                                          computed before starting the job.")
                    else:
                        running_hash = self._input_hashes[running.uid]
                        self._result_repo.store_results(running_hash, running)

                except (jsonschema.exceptions.ValidationError, SecurityError) as e:
                    self.graph.fail(running_job)
                    running.set_failed()
                    runtime_dir = Path(running.runtime_directory)
                    self.abort()
                    assert runtime_dir != Path.home(), "Will not delete home dir"
                    assert runtime_dir != Path('/'), "Will not delete root"
                    if runtime_dir.is_dir():
                        shutil.rmtree(runtime_dir)

                    runtime_dir.mkdir(exist_ok=False)
                    with (runtime_dir / 'security_error.log').open('w') as outfile:
                        if isinstance(e, jsonschema.exceptions.ValidationError):
                            outfile.write(f"Encountered security error. Error was: {e.message}.")
                        else:
                            outfile.write(f"Encountered security error. Error was: {e}.")
                        traceback.print_tb(tb=e.__traceback__, file=outfile)

                    return True
                except WorkflowAbort as e:
                    self.graph.fail(running_job)
                    running.set_failed()
                    self._logger.error(str(e))
                    self._logger.error("Aborting workflow %s due to error in Job."%self.submit_name)
                    self.abort()
                    return True
                except Exception as e:
                    self._logger.exception("Exception during postjob care. Aborting workflow.")
                    self.abort()
                    return True

        ready_jobs = self.graph.get_next_ready()
        #self.graph.traverse()
        for rdjob in ready_jobs:
            tostart = self.elements.get_element_by_uid(rdjob)
            if isinstance(tostart,WorkflowExecModule):
                tostart : WorkflowExecModule
                try:
                    if not self._prepare_job(tostart):
                        self._logger.error("Error during job preparation. Aborting workflow %s"%self.submit_name)
                        self.abort()
                        return True
                    else:
                        self._field_values["status"] = JobStatus.RUNNING
                        self.graph.start(rdjob)
                        input_hash = self._result_repo.compute_input_hash(tostart)
                        if input_hash in self._input_hashes:
                            self._logger.warning(f"[REPO] A WFEM with the same hash as {tostart.outputpath} ({self._input_hashes[input_hash].outputpath}) has already been started in this workflow! \
                                                   This should not happen as all WFEMs within a workflow need to have a unique hash.")
                        else:
                            self._input_hashes[tostart.uid] = input_hash
                            if tostart.resources.reuse_results:
                                found_result, original_path = self._result_repo.load_results(input_hash, tostart)
                                if found_result:
                                    self._postjob_care(tostart)
                                    tostart.set_original_result_directory(original_path)
                                    self.graph.finish(rdjob)
                                    continue
                            else:
                                self._logger.info(f"[REPO] Any existing results will not be reused for {tostart.outputpath} since the feature is disabled by the resource configuration.")
                        if not self._check_if_job_is_local(tostart):
                            external_cluster_manager = self._get_clustermanager_from_job(tostart)
                        else:
                            external_cluster_manager = None

                        queueing_system = tostart.resources.queueing_system
                        tostart.run_jobfile(
                            external_cluster_manager=external_cluster_manager
                        )
                        self._logger.info("Started job >%s< in directory <%s> ."%(rdjob, tostart.runtime_directory))
                except Exception as e:
                    print(e)
                    traceback.print_exc()
                    self.graph.fail(rdjob)
                    tostart.set_failed()
                    self._logger.exception("Uncaught exception during job preparation. Aborting workflow %s"%self.submit_name)
                    self.abort()
                    return True
            elif isinstance(tostart, WFPass):
                # If this is encountered it is just passed on. These can be used as anchors inside the workflow.
                self.graph.start(rdjob)
                self.graph.finish(rdjob)
            elif isinstance(tostart, VariableElement):
                if secure_mode:
                    raise WorkflowAbort("Secure Mode WFs must not contain VariableElements.")
                result = tostart.evaluate_equation(input_variables=self._input_variables, output_variables=self._output_variables)
                self._output_variables[tostart.variable_name] = result
                self.graph.start(rdjob)
                self.graph.finish(rdjob)
            elif isinstance(tostart, ForEachGraph) or isinstance(tostart, IfGraph) or isinstance(tostart,  WhileGraph):
                if secure_mode:
                    raise WorkflowAbort("Secure Mode WFs must not contain dynamic elements such as If, ForEach or While.")
                new_connections, new_activity_elementlists, new_graphs = tostart.resolve_connect(base_storage=self.storage,
                                                                                                 input_variables = self._input_variables,
                                                                                                 output_variables = self._output_variables)
                for ng in new_graphs:
                    self.graph.merge_other_graph(ng)
                for new_elementlist in new_activity_elementlists:
                    self.elements.merge_other_list(new_elementlist)
                for connection in new_connections:
                    self.graph.add_new_unstarted_connection(connection)
                self.graph.start(rdjob)
                self.graph.finish(rdjob)

        current_time = time.time()
        #if current_time - self._last_dump_time > 2:
        if False:
            self._last_dump_time = time.time()
            outfile1 = join(self.storage, "input_variables.yml")
            with open(outfile1,'w') as outfile:
                yaml.safe_dump(self._input_variables)
            outfile2 = join(self.storage, "output_variables.yml")
            with open(outfile2,'w') as outfile:
                yaml.safe_dump(self._output_variables)
        if self.graph.is_workflow_finished():
            self._field_values["status"] = JobStatus.SUCCESSFUL
            self._logger.info("Workflow %s has been finished." %self.name)
            self.finalize()
            return True
        return False

    def _get_wfem_queueing_system(self, wfem: WorkflowExecModule):
        queueing_system = wfem.resources.queueing_system
        if queueing_system == "unset":
            # In this case nobody set our localqueue and we therefore override with the one we got from the workflow
            queueing_system = self.default_wf_resources.queueing_system
        return queueing_system

    def _prepare_job(self, wfem : WorkflowExecModule):
        queueing_system = wfem.resources.queueing_system
        secure_mode = SecureModeGlobal.get_secure_mode()
        jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem)
        counter = 0
        while os.path.isdir(jobdirectory):
            jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem) + "%d"%counter
            counter += 1
            if counter == 10:
                time.sleep(0.1)
            if counter == 20:
                raise WorkflowAbort("Job directory could not be generated even after 20 attempts.")
        wfem.set_runtime_directory(jobdirectory)
        mkdir_p(jobdirectory)

        explicit_wfxml = join(self.storage, "workflow_data",wfem.path,"inputs",wfem.wano_xml)
        wano_dir_root = Path(join(self.storage, "workflow_data",wfem.path,"inputs"))
        from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
        #with open(wfxml, 'rt') as infile:
        #    xml = etree.parse(infile)
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
        #MODELROOTDIRECT
        # Split zwischen TrustedExecutionWaNoModelRoot
        #  TEWaNoModelRoot(...) # kein custom exec command

        wmr = WaNoModelRoot(wano_dir_root = wano_dir_root, model_only = True, explicit_xml=explicit_wfxml)
        try:
            wmr.read(wano_dir_root)
        except FileNotFoundError as e:
            self._logger.info("Did not find wano_configuration.json. This is ok, if this was an old client using the V1 workflow format.")
        wmr = wano_without_view_constructor_helper(wmr)
        wmr.datachanged_force()
        wmr.datachanged_force()
        
        rendered_wano = wmr.wano_walker()
        # We do two render passes, in case the rendering reset some values:
        fvl = []
        rendered_wano = wmr.wano_walker_render_pass(rendered_wano,submitdir=None,flat_variable_list=None,
                                                    input_var_db = self._input_variables,
                                                    output_var_db = self._output_variables,
                                                    runtime_variables = wfem.get_runtime_variables()
                                                    )
        render_substitutions = wmr.get_render_substitutions()
        if queueing_system == "AiiDA":
            do_aiida = True
            from aiida.orm import load_node, SinglefileData
            import aiida.orm as orm
        else:
            do_aiida = False
        input_vars = wmr.get_paths_and_data_dict()
        topath = wfem.outputpath.replace('/','.')
        rendered_exec_command = wmr.render_exec_command(rendered_wano)
        wfem.set_exec_command(rendered_exec_command)
        self._logger.info("Preparing job with exec command: %s"%wfem.exec_command)
        for key,value in input_vars.items():
            self._input_variables["%s.%s"%(topath,key)] = value

        with open(join(jobdirectory, "rendered_wano.yml"), 'wt') as outfile:
            yaml.safe_dump(rendered_wano, outfile)

        if secure_mode:
            sws = SecureWaNos.get_instance()
            try:
                approved_wano = sws.get_wano_by_name(wmr.name)
                approved_wano.verify_against_secure_schema(rendered_wano)
            except jsonschema.exceptions.ValidationError as e:
                message = "Submitted WaNo could not be verified against input schema."
                with (Path(jobdirectory) / 'security_error.log').open('w') as outfile:
                    outfile.write(message)
                raise e
            except KeyError:
                message = f"Could not find WaNo in secure_wanos folder. WaNo name was: {wmr.name}"
                with (Path(jobdirectory) / 'security_error.log').open('w') as outfile:
                    outfile.write(message)
                raise SecurityError(message)
            if approved_wano.exec_command.strip() != rendered_exec_command.strip():
                message = f"The exec command of the approved WaNo {approved_wano.exec_command} was different from the rendered_version {rendered_exec_command}. Secure WaNos must not contain dynamic fields. Aborting."
                with (Path(jobdirectory) / 'security_error.log').open('w') as outfile:
                    outfile.write(message)
                raise SecurityError(message)


        # Debug dump
        if False:
            #Plan:
            """
                1.) Take care of fi1es. Check provenance graph of running simulation for their namespaces
                 # Record dict mapping stageout filename to AiiDA uuid.
                 # When staging in files, overwrite
                 # Stagein Filename has to be considered in WaNoCalcJob still. Right now we use filename
                2.) Write translation layer: FILESYSTEM Path -> AiiDA output variable name
                3.) Input variables are still missing in the aiida path to uuid dict
            
            """
            with open(join(jobdirectory, "inputvardb.yml"), 'wt') as outfile:
                yaml.safe_dump(self._input_variables,outfile)

            with open(join(jobdirectory, "outputvardb.yml"), 'wt') as outfile:
                yaml.safe_dump(self._output_variables,outfile)

        """ Sanity check to check if all files are there """
        for myinput in wfem.inputs:
            tofile = myinput[0]
            source = myinput[1]
            absfile = self.storage + '/' + source
            print(source)
            allfiles = []
            if "*" in absfile:
                allfiles = glob(absfile)
            else:
                allfiles = [absfile]

            for myfile in allfiles:
                if not path.isfile(myfile):
                    self._logger.error("Could not find file %s (expected at %s) for wanoid %s on disk. Canceling workflow. Target was: %s"%(source,absfile, wfem.uid, tofile))
                    return False

        aiida_files = []
        aiida_files_by_relpath = {}

        """ Same loop again this time copying files """
        for myinput in wfem.inputs:
            tofile = jobdirectory + '/' + myinput[0]
            source = myinput[1]
            myabsfile = self.storage + '/' + source

            allfiles = []
            already_copied = []
            globmode = False # In this case we need to rewrite something
            if "*" in myabsfile:
                allfiles = glob(myabsfile)
            else:
                allfiles = [myabsfile]
            if len(allfiles) > 1:
                globmode = True

            for absfilenum, absfile in enumerate(allfiles):
                if not path.isfile(absfile):
                    self._logger.error("Could not find file %s (expected at %s) on disk. Canceling workflow. Target was: %s"%(source,absfile, tofile))
                    return False
                absfile = os.path.abspath(absfile)
                actual_tofile = tofile
                actual_tofile_rel = myinput[0]
                if globmode:
                    actual_tofile = "%s/%d_%s"%(jobdirectory, absfilenum, myinput[0])
                    actual_tofile_rel = "%d_%s"%(absfilenum, myinput[0])
                try:
                    if absfile.endswith("output_dict.yml") or absfile.endswith("output_config.ini") or absfile.endswith("report_template.body"):
                        raise JustCopyException()
                    with open(absfile, 'r') as infile:
                        absfile_content = infile.read()
                    rendered_content = Template(absfile_content).render(wano = rendered_wano,
                                                     input_variables = self._input_variables,
                                                     output_variables = self._output_variables
                    )
                    with open(actual_tofile, 'w') as outfile:
                        outfile.write(rendered_content)
                except JustCopyException as e:
                    shutil.copyfile(absfile, tofile)
                except Exception as e:
                    self._logger.warning("Unable to render input file %s. Copying instead. Exception was: %s"%(absfile,e))
                    shutil.copyfile(absfile, tofile)
                if do_aiida:
                    if absfile in self._filepath_to_aiida_uuid:
                        myuuid = self._filepath_to_aiida_uuid[absfile]
                        afile = load_node(myuuid)
                    else:
                        afile = SinglefileData(actual_tofile, filename=actual_tofile_rel)
                    aiida_files.append(afile)
                    aiida_files_by_relpath[actual_tofile_rel] = afile
        if do_aiida:
            # Here we prep the aiida value dict:
            from wano_calcjob.WaNoCalcJobBase import clean_dict_for_aiida
            from wano_calcjob.WaNoCalcJobBase import WaNoCalcJob as WCJ
            from aiida.orm import load_node

            aiida_rw = wmr.get_valuedict_with_aiida_types(aiida_files_by_relpath = aiida_files_by_relpath)
            aiida_rw_tw = NestDictMod(aiida_rw)
            topath = wfem.outputpath.replace('/','.')
            for mypath in render_substitutions.keys():
                #print("I would try to replace",mypath)
                cleaned_path = subdict_skiplevel_path_version(mypath)
                substituted_to = render_substitutions[mypath]
                if substituted_to in self._path_to_aiida_uuid:
                    splitpath = cleaned_path.split(".")
                    myuuid = self._path_to_aiida_uuid[substituted_to]
                    datanode = load_node(uuid=myuuid)
                    aiida_rw_tw[splitpath] = datanode
                else:
                    print("Did not find", substituted_to)
                    print("Keys were", self._path_to_aiida_uuid.keys())


            aiida_rw["static_extra_files"] = {}
            aiida_files.append(SinglefileData("%s/rendered_wano.yml"%jobdirectory, filename="rendered_wano.yml"))
            for myfile in aiida_files:
                cleaned_filename = WCJ.dot_to_none(myfile.filename)
                aiida_rw["static_extra_files"][cleaned_filename] = myfile
            aiida_rw["filename_locations"] = {}
            for logical_path, fileobj in aiida_files_by_relpath.items():
                aiida_rw["filename_locations"]["a%s"%fileobj.uuid] = orm.Str(logical_path)

            flat_dict = flatten_dict(aiida_rw)
            # Here we make the aiida objects known to the server:
            for key, aiida_obj in flat_dict.items():
                fullpath = "%s.%s"%(topath,key)
                self._path_to_aiida_uuid[fullpath] = aiida_obj.uuid

            aiida_rw = clean_dict_for_aiida(aiida_rw)
            aiida_rw["wano_name"] = wmr.name
            wfem.set_aiida_valuedict(aiida_rw)

        return True

    def _postjob_care(self, wfem : WorkflowExecModule):
        jobdirectory = wfem.runtime_directory
        queueing_system = wfem.resources.queueing_system
        myjobid = wfem.jobid
        secure_mode = SecureModeGlobal.get_secure_mode()

        if not wfem.check_if_job_is_local():

            from SimStackServer.ClusterManager import ClusterManager
            mycm : ClusterManager = self._get_clustermanager_from_job(wfem)
            runtime_dir = wfem.runtime_directory
            ext_runtime_dir = wfem.external_runtime_directory
            self._logger.info(f"Retrieving runtime directory of non-local job from {ext_runtime_dir} to {runtime_dir}.")
            with mycm.connection_context():
                mycm.get_directory(ext_runtime_dir, runtime_dir)


        staging_filename_to_aiida_obj = {}
        if queueing_system == "AiiDA":
            from SimStackServer.SimAiiDA.AiiDAJob import AiiDAJob
            myjob = AiiDAJob(myjobid)
            process_class = myjob.get_process_class()
            aiida_to_simstack_pathmap = process_class.get_aiida_to_simstack_pathmap()
            simstack_path_to_aiida_uuid = {}


        if queueing_system == "AiiDA":
            #from aiida.plugins import CalculationFactory
            #calcjob_class = CalculationFactory(wfem.name)
            pc = myjob.get_process_class()
            self._logger.info(f"Staging out {pc.__name__}")

            outputs = myjob.get_outputs()
            for myoutput in outputs:
                mynode = outputs[myoutput]


                if mynode.class_node_type == 'data.singlefile.SinglefileData.':
                    stagingfilename = mynode.filename

                    with mynode.open(mode="rb") as infile:
                        myfolder = jobdirectory
                        os.makedirs(myfolder, exist_ok=True)
                        absfile = join(myfolder, stagingfilename)
                        staging_filename_to_aiida_obj[absfile] = mynode
                        with open(absfile, 'wb') as outfile:
                            outfile.write(infile.read())
                try:
                    simstack_path = aiida_to_simstack_pathmap[myoutput]
                except KeyError as e:
                    if myoutput not in ["retrieved","remote_folder"]:
                        self._logger.exception("Expected Exception here trying to stage out %s"%myoutput)
                        self._logger.error("keys were: %s"%( ",".join([str(key) for key in aiida_to_simstack_pathmap]) ))
                    #If it does not have a simstack_path, we don't need it for further things.
                    continue
                simstack_path_to_aiida_uuid[simstack_path] = mynode.uuid

        found_output_dict = False
        """ Sanity check to check if all files are there """
        for myoutput in wfem.outputs:
            # tofile = myinput[0]
            output = myoutput[0]
            absfile = jobdirectory + '/' + output

            # The next step after this one will render the output variables. We need to crosscheck these against the output schema
            if secure_mode:
                if output != "output_dict.yml":
                    message = f"No other file allowed in secure mode except for output_dict.yml. File was {output}"
                    with (Path(jobdirectory) / 'security_error.log').open('w') as outfile:
                        outfile.write(message)
                    raise SecurityError(message)
                found_output_dict = True
                sws = SecureWaNos.get_instance()



                explicit_wfxml = join(self.storage, "workflow_data", wfem.path, "inputs", wfem.wano_xml)
                wano_dir_root = Path(join(self.storage, "workflow_data", wfem.path, "inputs"))
                from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
                from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
                wmr = WaNoModelRoot(wano_dir_root=wano_dir_root, model_only=True, explicit_xml=explicit_wfxml)


                secure_wano = sws.get_wano_by_name(wmr.name)

                with Path(absfile).open() as content_file:
                    content = yaml.safe_load(content_file.read())
                secure_wano.verify_output_against_schema(content)

            # In case of a glob pattern, we need special care
            if "*" in absfile:
                allfiles = glob(absfile)
                if len(allfiles) == 0:
                    mystdout = "Tried staging out multiple files matching %s, but did not find a single file." % absfile
                    self._logger.error(mystdout)
                    raise WorkflowAbort(mystdout)
            else:
                if not path.isfile(absfile):
                    mystdout = "Could not find outputfile %s on disk (requested at %s). Canceling workflow." % (output,absfile)
                    self._logger.error(mystdout)
                    raise WorkflowAbort(mystdout)

        if secure_mode and not found_output_dict:
            message = "Secure Mode WaNos require an output_dict.yml"
            with (Path(jobdirectory) / 'security_error.log').open('w') as outfile:
                outfile.write(message)
            raise SecurityError(message)

        myvars = wfem.get_output_variables(render_report = True)
        # REPORT We need to collect the body files here -
        if isinstance(myvars, dict):
            flattened_output_variables = flatten_dict(myvars)
            topath = wfem.outputpath.replace('/','.')
            for key,value in flattened_output_variables.items():
                self._output_variables["%s.%s"%(topath,key)] = value
            if queueing_system == "AiiDA":
                for sims_path, uuid in simstack_path_to_aiida_uuid.items():
                    self._path_to_aiida_uuid["%s.%s"%(topath, sims_path)] = uuid

        """ Same loop again this time copying files """
        for myoutput in wfem.outputs:
            # Outputs already checked for secure mode above
            if wfem.outputpath == 'unset':
                # Legacy behaviour in case of wfem missing outputpath
                tofile = self.storage + '/' + myoutput[1]
            else:
                tofile = join(self.storage, "workflow_data", wfem.outputpath,"outputs", myoutput[1])

            output = myoutput[0]
            absfile = jobdirectory + '/' + output



            tofiledir = path.dirname(tofile)
            self._logger.info("Staging %s to %s" % (absfile, tofiledir))
            mkdir_p(tofiledir)

            doglob = "*" in absfile
            if doglob:
                allfiles = glob(absfile)
            else:
                allfiles = [absfile]

            for tocopy in allfiles:
                if not path.isfile(tocopy):
                    mystdout = "Could not find outputfile %s on disk. Canceling workflow." % output
                    self._logger.error(mystdout)
                    raise WorkflowAbort(mystdout)
                if doglob:
                    basename = os.path.basename(tocopy)
                    tofile = join(tofiledir,basename)
                shutil.copyfile(tocopy, tofile)
                if tocopy in staging_filename_to_aiida_obj:
                    self._filepath_to_aiida_uuid[tofile] = staging_filename_to_aiida_obj[tocopy].uuid


        return myvars

    def get_jobs(self):
        success, failed, running = self.graph.get_success_failed_running_jobs()
        alljobs =  success + failed + running

        alljobobjs = [ self.elements.get_element_by_uid(job) for job in alljobs if job != "0"]
        return alljobobjs

    def get_running_finished_job_list_formatted(self):
        files = []
        success, failed, running = self.graph.get_success_failed_running_jobs()
        for joblist, status in zip([running,failed,success],[JobStatus.RUNNING,JobStatus.FAILED, JobStatus.SUCCESSFUL]):
            for job in joblist:
                if job == '0':
                    # 0 is start node, skip over it.
                    continue
                jobobj = self.elements.get_element_by_uid(job)
                if not isinstance(jobobj, WorkflowExecModule):
                    continue
                jobobj : WorkflowExecModule
                self._logger.debug("Looking for commonpath between %s and %s"%(jobobj.runtime_directory,self.storage))
                if jobobj.runtime_directory == "unstarted":
                    continue
                print(jobobj.runtime_directory, self.storage)
                if jobobj.runtime_directory.startswith("/"):
                    commonpathlen = len(path.commonpath([jobobj.runtime_directory, self.storage]))
                else:
                    commonpathlen = 0
                jobdir = jobobj.runtime_directory[commonpathlen:]
                if jobdir.startswith('/'):
                    jobdir = jobdir[1:]
                jobdir = self.submit_name + '/' + jobdir
                jobdict = {
                    'id': jobobj.given_name,
                    'name': jobobj.given_name,
                    'type': 'j',
                    'path': jobdir,
                    'status': status,
                    'original_result_directory': jobobj.original_result_directory if jobobj.original_result_directory != "" else None
                }
                files.append(jobdict)
        return files
