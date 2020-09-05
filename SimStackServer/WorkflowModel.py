import abc
import copy
import datetime
import time
import logging
import os
import shutil
import sys
import traceback
import uuid
from abc import abstractmethod, abstractclassmethod
from enum import Flag, auto
from glob import glob
from io import StringIO
from os.path import join

from pathlib import Path

from os import path

import yaml
from lxml import etree

import numpy as np
import networkx as nx

from SimStackServer.MessageTypes import JobStatus
from SimStackServer.Reporting.ReportRenderer import ReportRenderer
from SimStackServer.Util.FileUtilities import mkdir_p, StringLoggingHandler
from external.clusterjob.clusterjob import FAILED


class ParserError(Exception):
    pass

class JobSubmitException(Exception):
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
                for key,item in vardict.items():
                    self._storage[myid] = my_str.replace(key,item)
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
                    myfo.from_dict(child)
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

class Resources(XMLYMLInstantiationBase):
    """
    Class to store computational resources. Used to create jobs. Host refers to the HPC master this is running on.
    """
    _fields = [
        ("walltime", np.uint64, 86399, "Walltime in seconds", "a"),
        ("cpus_per_node", np.uint64, 1, "Number of CPUs per Node", "a"),
        ("nodes",np.uint64, 1, "Number of Nodes", "a"),
        ("queue", str, "default", "String representation of queue", "m"),
        ("host", str, "localhost", "String representation of host, might include port with :, might be ipv4 or ipv6","m"),
        ("memory", np.uint64, 4096,  "Memory in Megabytes", "a")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def fields(cls):
        return cls._fields

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
    def host(self):
        return self._field_values["host"]

    @property
    def memory(self):
        return self._field_values["memory"]

class CurrentTrash(object):
    otherfields = ["template_directory",
            "instantiated_directory",
            "input_files",
            "output_files"]

    def template_directory(self):
        return self._template_directory

    @property
    def instantiated_directory(self):
        return self._instantiated_directory


class WorkflowExecModule(XMLYMLInstantiationBase):
    _fields = [
        ("uid", str, None, "uid of this WorkflowExecModule.", "a"),
        ("given_name", str, "WFEM", "Name of this WorkflowExecModule.", "a"),
        ("path", str, "unset", "Path to this WFEM in the workflow.", "a"),
        ("wano_xml", str, "unset", "Name of the WaNo XML.", "a"),
        ("outputpath", str, "unset", "Path to the output directory of this wfem in the workflow.", "a"),
        ("inputs",       WorkflowElementList, None, "List of Input URLs", "m"),
        ("outputs",      WorkflowElementList, None, "List of Outputs URLs", "m"),
        ("exec_command", str,                 None, "Command to be executed as part of BSS. Example: 'date'", "m"),
        ("resources", Resources, None, "Computational resources", "m"),

        ("runtime_directory",str, "unstarted", "The directory this wfem was started in","m"),
        ("jobid", str, "unstarted", "The id of the job this wfem was started with.", "m"),
        ("queueing_system", str, "unset", "The queueing system this job is submitted with. Kind of redundant currently.", "m")
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "WorkflowExecModule"
        self._nmdir = self._init_nanomatch_directory()
        self._logger = logging.getLogger(self.uid)

    @classmethod
    def fields(cls):
        return cls._fields

    def fill_in_variables(self, vardict):
        self._field_values["inputs"].fill_in_variables(vardict)
        self._field_values["outputs"].fill_in_variables(vardict)

    def rename(self, renamedict):
        myuid = self.uid
        if not myuid in renamedict:
            raise KeyError("%s not found in renamedict. Dict contained: %s"%(myuid, ",".join(renamedict.keys())))
        newuid = renamedict[myuid]
        self._field_values["uid"] = newuid

    def _init_nanomatch_directory(self):
        # The file we are in might be compiled. We need a definitely uncompiled module.
        import SimStackServer.Data as data

        datadir = path.realpath(data.__path__[0])
        #datadir is:
        # '/home/nanomatch/nanomatch/V2/SimStackServer/SimStackServer/Data'
        # we want: /home/nanomatch/nanomatch
        datadirpath = Path(datadir)
        nmdir = str(datadirpath.parent.parent.parent.parent)
        return nmdir

    def _get_prolog_unicore_compatibility(self, resources):
        """

        :param resources:
        :return:
        """
        return """
UC_NODES=%d; export UC_NODES;
UC_PROCESSORS_PER_NODE=%d; export UC_PROCESSORS_PER_NODE;
UC_TOTAL_PROCESSORS=%d; export UC_TOTAL_PROCESSORS;
UC_MEMORY_PER_NODE=%d; export UC_MEMORY_PER_NODE;
export NANOMATCH=%s
"""%(resources.nodes,resources.cpus_per_node,resources.cpus_per_node*resources.nodes,self.resources.memory, self._nmdir)

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
        if hours > 0:
            timestring += "%d:"%hours
        if minutes > 0:
            timestring += "%02d:"%minutes
        timestring += "%02d"%seconds
        return timestring


    def run_jobfile(self, queueing_system):
        temphandler = StringLoggingHandler()
        self._logger.addHandler(temphandler)
        if queueing_system == "Internal":
            queueing_system = "slurm"
            do_internal = True
        else:
            do_internal = False
        try:
            import clusterjob
            #Sanity checks
            # check if runtime directory is not unset
            queue = self.resources.queue
            kwargs = {}
            kwargs["queue"] = self.resources.queue
            if queue == "default" and queueing_system in ["pbs","slurm"]:
                del kwargs["queue"]

            mytime = self.resources.walltime
            if mytime < 61:
                # We have to allocate at least 61 seconds
                # to work around the specificities of clusterjob.
                mytime = 61
            mytimestring = self._time_from_seconds_to_clusterjob_timestring(mytime)

            toexec = """%s
    cd $CLUSTERJOB_WORKDIR
    %s
"""%(self._get_prolog_unicore_compatibility(self.resources), self.exec_command)
            try:
                jobscript = clusterjob.JobScript(toexec, backend=queueing_system, jobname = self.given_name,
                                                 time = self.resources.walltime, nodes = self.resources.nodes,
                                                 ppn = self.resources.cpus_per_node, mem = self.resources.memory,
                                                 stdout = self.given_name + ".stdout", stderr = self.given_name + ".stderr",
                                                 workdir = self.runtime_directory, **kwargs
                )


                #with open(self.runtime_directory + "/" + "jobscript.sh", 'wt') as outfile:
                #    outfile.write(str(jobscript)+ '\n')
                if not do_internal:
                    asyncresult = jobscript.submit()
                    if asyncresult.status == FAILED:
                        raise JobSubmitException("Job failed immediately after submission.")
                    #self._async_result_workaround = asyncresult
                    self.set_jobid(asyncresult.job_id)
                else:
                    from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
                    batchsys, _ = InternalBatchSystem.get_instance()
                    runscript = self.runtime_directory + "/" + "jobscript.sh"
                    with open(runscript, 'wt') as outfile:
                        outfile.write(str(jobscript).replace("$SLURM_SUBMIT_DIR",self.runtime_directory)+ '\n')
                    hostfile = self.runtime_directory + "/" + "HOSTFILE"
                    with open(hostfile, 'wt') as hoststream:
                        for i in range(0, self.resources.cpus_per_node):
                            hoststream.write("localhost\n")
                    jobid = batchsys.add_work_to_current_bracket(self.resources.cpus_per_node,"smp",runscript)
                    self._logger.debug("Submitted as internal job %d"%jobid)
                    self.set_jobid(jobid)
                    ## In this case we need to grab jobid after submission and
            except Exception as e:
                server_submit_stderr = join(self.runtime_directory, "submission_failed.stderr")
                self._logger.error("Exception: %s. Writing traceback to: %s"%(e, server_submit_stderr))
                with open(server_submit_stderr,'wt') as outfile:
                    traceback.print_exc(file=outfile)
                    outfile.write(temphandler.getvalue())
                raise e from e
        finally:
            # We remove the handler
            self._logger.removeHandler(temphandler)


    def abort_job(self):
        if self.queueing_system != "Internal":
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
        else:
            from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
            batchsys, _ = InternalBatchSystem.get_instance()
            batchsys.abort_job(self.jobid)

    def _recreate_asyncresult_from_jobid(self, jobid):
        assert not self.queueing_system == "Internal", "Recreating asyncresult from jobid not supported for Internal queueing system"
        # This function is a placeholder still. We need to generate the asyncresult just from the jobid.
        # It will require a modified clusterjob
        from clusterjob import AsyncResult, JobScript
        if len(JobScript._backends) == 0:
            a = JobScript("DummyJob")
            assert len(JobScript._backends) > 0

        ar = AsyncResult(JobScript._backends[self.queueing_system])
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

    @property
    def queueing_system(self):
        return self._field_values["queueing_system"]

    def completed_or_aborted(self):
        if self.queueing_system != "Internal":
            try:
                asyncresult = self._recreate_asyncresult_from_jobid(self.jobid)
                return asyncresult.status >= 0
            except ValueError as e:
                # In this case the queueing system did not know about our job anymore. Return True
                return True # The job will be checked for actual completion anyways
        else:
            from SimStackServer.Util.InternalBatchSystem import InternalBatchSystem
            batchsys, _ = InternalBatchSystem.get_instance()
            status = batchsys.jobstatus(self.jobid)
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
        return report_renderer.consolidate_export_dictionaries()

    @property
    def uid(self):
        return self._field_values["uid"]

    def set_runtime_directory(self, runtime_directory):
        self._field_values["runtime_directory"] = runtime_directory

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

class DirectedGraph(object):
    def __init__(self, *args, **kwargs):
        self._graph = nx.DiGraph()
        self._default_node_attributes = { "status" : "waiting" }

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

    def get_next_ready(self):
        nodes = self._graph.nodes

        for a in nx.dfs_tree(self._graph):
            if a == "0":
                nodes[a]["status"] = "success"
            if nodes[a]["status"] == "unstarted":
                candidate = True
                for pred in self._graph.predecessors(a):
                    if nodes[pred]["status"] != "success":
                        candidate = False
                        break
                    #print("%d was preceeded by %d"%(a,pred))
                if candidate:
                    nodes[a]["status"] = "ready"

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


class ForEachGraph(XMLYMLInstantiationBase):
    _fields = [
        ("subgraph", SubGraph, None, "Graph to instantiate For Each Element","m"),
        ("iterator_files", StringList, [], "Files and globpatterns to iterate over", "m"),
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

    def fill_in_variables(self, vardict):
        self._field_values["subgraph"].fill_in_variables(vardict)

    @property
    def subgraph_final_ids(self) -> StringList:
        return self._field_values["subgraph_final_ids"]

    def resolve_connect(self, base_storage):
        allfiles = self._resolve_iterator(base_storage)
        return self._multiply_connect_subgraph(allfiles)

    def _resolve_iterator(self, base_storage):
        relfiles = self.iterator_files
        allfiles = []
        for myfile_rel in relfiles:
            myfile = join(base_storage,myfile_rel)
            isglob = "*" in myfile
            if isglob:
                allfiles += glob(myfile)
            else:
                allfiles += [myfile]
        base_store_len = len(base_storage)
        # We want to resolve this iterator relative to base_storage:
        allfiles = [myfile[base_store_len:] for myfile in allfiles]
        return allfiles

    def _multiply_connect_subgraph(self, resolved_files):
        new_connections = []
        new_activity_elementlists = []
        new_graphs = []
        for myfile in resolved_files:
            mygraph = copy.deepcopy(self.subgraph)
            replacedict = {
                "${%s_VALUE}"%self.iterator_name :myfile
            }
            mygraph.fill_in_variables(replacedict)
            # We rename temporary connector to us. Like this we don't have to remove temporary connector in the end.
            override = {"temporary_connector": self.uid}
            rename_dict = mygraph.rename_all_nodes(explicit_overrides=override)
            if not "temporary_connector" in rename_dict:
                raise WorkflowAbort("mygraph did not contain start id temporary_connector. Renamed keys were: %s"%(",".join(rename_dict.keys())))

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

    @property
    def uid(self):
        return self._field_values["uid"]

    @property
    def subgraph(self) -> SubGraph:
        return self._field_values["subgraph"]

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
        ("queueing_system",str, "unset", "Name of the queueing system. Might move into WFEM in case of split jobs.", "a")
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

    def from_xml(self, in_xml):
        super().from_xml(in_xml)

    def from_dict(self, in_dict):
        super().from_dict(in_dict)

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
    def queueing_system(self) -> str:
        return self._field_values["queueing_system"]

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

class Workflow(WorkflowBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "Workflow"
        self._logger = logging.getLogger("Workflow")
        self._input_variables = {}
        self._output_variables = {}

    def all_job_abort(self):
        for job in self.graph.get_running_jobs():
            myjob = self.elements.get_element_by_uid(job)
            myjob: WorkflowExecModule
            myjob.abort_job()
            self.graph.fail(job)

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
        shutil.rmtree(exec_dir_path,ignore_errors=True)
        shutil.rmtree(workflow_data_path, ignore_errors=True)
        try:
            os.remove(rendered_workflow_path)
        except FileNotFoundError as e:
            pass
        try:
            os.rmdir(self.storage)
        except FileNotFoundError as e:
            pass

    def jobloop(self):
        running_jobs = self.graph.get_running_jobs()

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
                except WorkflowAbort as e:
                    self.graph.fail(running_job)
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
                tostart.set_queueing_system(self.queueing_system)
                try:
                    if not self._prepare_job(tostart):
                        self._logger.error("Error during job preparation. Aborting workflow %s"%self.submit_name)
                        self.abort()
                        return True
                    else:
                        self._field_values["status"] = JobStatus.RUNNING
                        self.graph.start(rdjob)
                        tostart.run_jobfile(self.queueing_system)
                        self._logger.info("Started job >%s< in directory <%s> ."%(rdjob, tostart.runtime_directory))
                except Exception as e:
                    self.graph.fail(rdjob)
                    self._logger.exception("Uncaught exception during job preparation. Aborting workflow %s"%self.submit_name)
                    self.abort()
                    return True
            elif isinstance(tostart, WFPass):
                # If this is encountered it is just passed on. These can be used as anchors inside the workflow.
                self.graph.start(rdjob)
                self.graph.finish(rdjob)
            elif isinstance(tostart, ForEachGraph):
                print("Reached ForEachGraph")
                new_connections, new_activity_elementlists, new_graphs = tostart.resolve_connect(base_storage=self.storage)
                for ng in new_graphs:
                    self.graph.merge_other_graph(ng)
                for new_elementlist in new_activity_elementlists:
                    self.elements.merge_other_list(new_elementlist)
                for connection in new_connections:
                    self.graph.add_new_unstarted_connection(connection)
                self.graph.start(rdjob)
                self.graph.finish(rdjob)
                # What do we need to do here? We need to extend the graph, because it should be disjunct at the moment.
                # ForEach has to integrate itself into the main graph, i.e.
                # ForEach knows its parent id,
                #    Stage 1:
                #          For Each has to actually resolve the iterator and make the actual list
                #    Stage 2:
                #          For Each iterator value, we need to copy the digraph and connect it to all parent ids
                #    Stage 3:
                #          We have to replace all occurences of the iterator name with the actual iterator, this is hard
                #    Stage 4:
                #          We have to rename all Elements and all id occurences in the graph. DiGraph has a function for this.
                #    Stage :
                #          We need to attach this graph to the WFPass uid. It has to be different from the starter id
                #    Stage :
                #          We set the ForEachElement starter id as finished immediately so that the new jobs will be run.
        if self.graph.is_workflow_finished():
            self._field_values["status"] = JobStatus.SUCCESSFUL
            self._logger.info("Workflow %s has been finished." %self.name)
            return True
        current_time = time.time()
        if current_time - self._last_dump_time > 20:
            self._last_dump_time = time.time()
            outfile1 = join(self.storage, "input_variables.yml")
            with open(outfile1,'w') as outfile:
                yaml.safe_dump(self._input_variables)
            outfile2 = join(self.storage, "input_variables.yml")
            with open(outfile2,'w') as outfile:
                yaml.safe_dump(self._output_variables)
        return False

    def _prepare_job(self, wfem : WorkflowExecModule):

        jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem)
        counter = 0
        while path.isdir(jobdirectory):
            jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem) + "%d"%counter
            counter += 1
            if counter == 20:
                raise WorkflowAbort("Job directory could not be generated even after 20 attempts.")
        mkdir_p(jobdirectory)


        wfxml = join(self.storage, "workflow_data",wfem.path,"inputs",wfem.wano_xml)
        from SimStackServer.WaNo.WaNoFactory import wano_without_view_constructor_helper
        with open(wfxml, 'rt') as infile:
            xml = etree.parse(infile)
        wano_dir_root = os.path.dirname(wfem.path)
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot
        wmr = WaNoModelRoot(wano_dir_root = wano_dir_root, model_only = True)
        wmr.parse_from_xml(xml)
        wmr = wano_without_view_constructor_helper(wmr)
        rendered_wano = wmr.wano_walker()
        # We do two render passes, in case the rendering reset some values:
        fvl = []
        rendered_wano = wmr.wano_walker_render_pass(rendered_wano,submitdir=None,flat_variable_list=None)
        input_vars = wmr.get_paths_and_data_dict()
        topath = wfem.path.replace('/','.')
        rendered_exec_command = wmr.render_exec_command(rendered_wano)
        wfem.set_exec_command(rendered_exec_command)
        self._logger.info("Preparing job with exec command: %s"%wfem.exec_command)
        for key,value in input_vars.items():
            self._input_variables["%s.%s"%(topath,key)] = value

        with open(join(jobdirectory, "rendered_wano.yml"), 'wt') as outfile:
            yaml.safe_dump(rendered_wano, outfile)

        # Debug dump
        #with open(join(jobdirectory, "inputvardb.yml"), 'wt') as outfile:
        #    #yaml.safe_dump(rendered_wano, outfile)
        #    yaml.safe_dump(self._input_variables,outfile)

        """ Sanity check to check if all files are there """
        for myinput in wfem.inputs:
            #tofile = myinput[0]
            source = myinput[1]
            absfile = self.storage + '/' + source

            if not path.isfile(absfile):
                self._logger.error("Could not find file %s on disk. Canceling workflow."%source)
                return False



        """ Same loop again this time copying files """
        for myinput in wfem.inputs:
            tofile = jobdirectory + '/' + myinput[0]
            source = myinput[1]
            absfile = self.storage + '/' + source

            if not path.isfile(absfile):
                self._logger.error("Could not find file %s on disk. Canceling workflow."%source)
                return False
            shutil.copyfile(absfile, tofile)

        wfem.set_runtime_directory(jobdirectory)
        return True

    def _postjob_care(self, wfem : WorkflowExecModule):
        jobdirectory = wfem.runtime_directory

        """ Sanity check to check if all files are there """
        for myoutput in wfem.outputs:
            # tofile = myinput[0]
            output = myoutput[0]
            absfile = jobdirectory + '/' + output

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

        myvars = wfem.get_output_variables()
        """ Same loop again this time copying files """

        for myoutput in wfem.outputs:
            if wfem.outputpath == 'unset':
                # Legacy behaviour in case of wfem missing outputpath
                tofile = self.storage + '/' + myoutput[1]
            else:
                tofile = join(self.storage, "workflow_data", wfem.outputpath,"outputs", myoutput[1])

            output = myoutput[0]
            absfile = jobdirectory + '/' + output

            tofiledir = path.dirname(tofile)
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

        return myvars

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
                commonpath = path.commonpath([jobobj.runtime_directory, self.storage])
                jobdir = jobobj.runtime_directory[len(commonpath):]
                if jobdir.startswith('/'):
                    jobdir = jobdir[1:]
                jobdir = self.submit_name + '/' + jobdir
                jobdict = {
                    'id': jobobj.given_name,
                    'name': jobobj.given_name,
                    'type': 'j',
                    'path': jobdir,
                    'status': status
                }
                files.append(jobdict)
        return files
