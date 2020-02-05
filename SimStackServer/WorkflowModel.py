import abc
import datetime
import logging
import os
import shutil
import sys
import uuid
from abc import abstractmethod, abstractclassmethod
from enum import Flag, auto
from io import StringIO
from os.path import join

from pathlib import Path

from os import path

from lxml import etree

import numpy as np
import networkx as nx

from SimStackServer.MessageTypes import JobStatus
from SimStackServer.Util.FileUtilities import mkdir_p


class ParserError(Exception):
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


class UnknownWFEError(Exception):
    pass


class WorkflowElementList(object):
    def __init__(self, *args, **kwargs):
        self._clear()
        for inputvar in args:
            if isinstance(inputvar,list):
                #print(inputvar)
                for fieldtype, myobj in inputvar:
                    self.add_to_list(fieldtype, myobj)

    def _clear(self):
        self._storage = []
        self._typelist = []
        self._uid_to_seqnum = {}

    def add_to_list(self, mytype, actual_object):
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
                    myfo = fieldobject(child.text)
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
        self._logger = logging.getLogger("WorkflowExecModule")

        # This one has to be hacked out again. It is currently clusterjob dependent and we really don't want that.
        #self._async_result_workaround = None

    @classmethod
    def fields(cls):
        return cls._fields

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
        #In case somebody uploaded report_template.html, we render it:

        report_template = join(self.runtime_directory,"report_template.body")
        if os.path.isfile(report_template):
            self._logger.debug("Looking for %s" % report_template)
            import SimStackServer.Reporting as Reporting
            reporting_path = os.path.dirname(os.path.realpath(Reporting.__file__))
            toexec += "%s %s\n"%(sys.executable, join(reporting_path,"ReportRenderer.py"))

        jobscript = clusterjob.JobScript(toexec, backend=queueing_system, jobname = self.given_name,
                                         time = self.resources.walltime, nodes = self.resources.nodes,
                                         ppn = self.resources.cpus_per_node, mem = self.resources.memory,
                                         stdout = self.given_name + ".stdout", stderr = self.given_name + ".stderr",
                                         workdir = self.runtime_directory, **kwargs
        )


        #with open(self.runtime_directory + "/" + "jobscript.sh", 'wt') as outfile:
        #    outfile.write(str(jobscript)+ '\n')

        asyncresult = jobscript.submit()
        #self._async_result_workaround = asyncresult
        self.set_jobid(asyncresult.job_id)

    def abort_job(self):
        asyncresult = self._recreate_asyncresult_from_jobid(self.jobid)
        try:
            asyncresult.status
            asyncresult.cancel()
        except ValueError as e:
            # In this case the job was most probably not known by the queueing system anymore.
            pass

    def _recreate_asyncresult_from_jobid(self, jobid):
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

    @property
    def queueing_system(self):
        return self._field_values["queueing_system"]

    def completed_or_aborted(self):
        try:
            asyncresult = self._recreate_asyncresult_from_jobid(self.jobid)
            return asyncresult.status >= 0
        except ValueError as e:
            # In this case the queueing system did not know about our job anymore. Return True
            return True # The job will be checked for actual completion anyways

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

        for node in nx.dfs_tree(self._graph):
            all_node_ids.remove(node)
            # All nodes have to be reached via a DFS

        assert len(all_node_ids) == 0
        self._init_graph_to_unstarted()

    def _init_graph_to_unstarted(self):
        for node in self._graph:
            self._graph.nodes[node]["status"] = "unstarted"

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
                    self._postjob_care(running)
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
            tostart : WorkflowExecModule
            tostart.set_queueing_system(self.queueing_system)
            try:
                if not self._prepare_job(tostart):
                    self._logger.error("Error during job preparation. Aborting workflow %s"%self.submit_name)
                    self.abort()
                    return True
                else:
                    self._field_values["status"] = JobStatus.RUNNING
                    tostart.run_jobfile(self.queueing_system)
                    self.graph.start(rdjob)
                    self._logger.info("Started job >%s< in directory <%s> ."%(rdjob, tostart.runtime_directory))
            except Exception as e:
                self._logger.exception("Uncaught exception during job preparation. Aborting workflow %s"%self.submit_name)
                self.abort()
                return True
        if self.graph.is_workflow_finished():
            self._field_values["status"] = JobStatus.SUCCESSFUL
            self._logger.info("Workflow %s has been finished." %self.name)
            return True
        return False

    def _prepare_job(self, wfem : WorkflowExecModule):
        """ Sanity check to check if all files are there """
        for myinput in wfem.inputs:
            #tofile = myinput[0]
            source = myinput[1]
            absfile = self.storage + '/' + source

            if not path.isfile(absfile):
                self._logger.error("Could not find file %s on disk. Canceling workflow."%source)
                return False

        jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem)

        counter = 0
        while path.isdir(jobdirectory):
            jobdirectory = self.storage + '/exec_directories/' + self._get_job_directory(wfem) + "%d"%counter
            counter += 1
            if counter == 20:
                raise WorkflowAbort("Job directory could not be generated even after 20 attempts.")
        mkdir_p(jobdirectory)


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

            if not path.isfile(absfile):
                mystdout = "Could not find outputfile %s on disk. Canceling workflow." % output
                self._logger.error(mystdout)
                raise WorkflowAbort(mystdout)


        """ Same loop again this time copying files """

        for myoutput in wfem.outputs:
            tofile = self.storage + '/' + myoutput[1]
            output = myoutput[0]
            absfile = jobdirectory + '/' + output

            tofiledir = path.dirname(tofile)
            mkdir_p(tofiledir)
            if not path.isfile(absfile):
                mystdout = "Could not find outputfile %s on disk. Canceling workflow." % output
                self._logger.error(mystdout)
                raise WorkflowAbort(mystdout)
            shutil.copyfile(absfile, tofile)

        return True

    def get_running_finished_job_list_formatted(self):
        files = []
        success, failed, running = self.graph.get_success_failed_running_jobs()
        for joblist, status in zip([running,failed,success],[JobStatus.RUNNING,JobStatus.FAILED, JobStatus.SUCCESSFUL]):
            for job in joblist:
                if job == '0':
                    # 0 is start node, skip over it.
                    continue
                jobobj = self.elements.get_element_by_uid(job)
                jobobj : WorkflowExecModule
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
