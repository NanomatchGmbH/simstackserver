import datetime
import logging
import shutil
import sys
import uuid
from abc import abstractmethod, abstractclassmethod
from enum import Flag, auto
from io import StringIO

from pathlib import Path

from os import path
from lxml import etree

import numpy as np
import networkx as nx

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
                self._field_values[field] = childtype(child.text)
            else:
                insert_element = childtype()
                insert_element.from_xml(child)
                self._field_values[field] = insert_element

        for field, value in in_xml.attrib.items():
            if not field in self._field_values:
                continue
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
        ("walltime", np.uint64, 1, "Walltime in seconds", "a"),
        ("cpus_per_node", np.uint64, 1, "Number of CPUs per Node", "a"),
        ("nodes",np.uint64, 1, "Number of Nodes", "a"),
        ("queue", str, "default", "String representation of queue", "m"),
        ("host", str, "localhost", "String representation of host, might include port with :, might be ipv4 or ipv6","m"),
        ("memory", np.uint64, 1,  "Memory in Megabytes", "a")
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
    ]
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not "uid" in kwargs:
            self._field_values["uid"] = str(uuid.uuid4())
        self._name = "WorkflowExecModule"

    @classmethod
    def fields(cls):
        return cls._fields

    def write_jobfile(self, queueing_system):
        import clusterjob
        #Sanity checks
        # check if runtime directory is not unset
        queue = self.resources.queue
        kwargs = {}
        kwargs["queue"] = self.resources.queue
        if queue == "default" and queueing_system == "pbs":
            del kwargs["queue"]

        toexec = """cd ${CLUSTERJOB_WORKDIR}
%s
"""%self.exec_command
        jobscript = clusterjob.Job(toexec, backend=queueing_system, jobname = self.given_name,
                                         time = self.resources.walltime, nodes = self.resources.nodes,
                                         threads = self.resources.cpus_per_node, mem = self.resources.memory,
                                         stdout = self.given_name + ".stdout", stderr = self.given_name + ".stderr",
                                         workdir = self.runtime_directory, **kwargs
        )

        #with open(self.runtime_directory + "/" + "jobscript.sh", 'wt') as outfile:
        #    outfile.write(str(jobscript)+ '\n')

        asyncresult = jobscript.submit()
        print(asyncresult.status)
        #print(jobid)
        self.set_jobid(asyncresult.job_id)
        return jobscript

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
        self._default_node_attributes = { "Status" : "Waiting" }

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


    def start(self, node):
        assert self._graph.nodes[node]["status"] == "ready"
        self._graph.nodes[node]["status"] = "running"

    def finish(self, node):
        assert self._graph.nodes[node]["status"] == "running"
        self._graph.nodes[node]["status"] = "success"

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

class Workflow(XMLYMLInstantiationBase):
    _fields = [
        ("elements", WorkflowElementList, None, "List of Linear Workflow Elements (this can also be fors or splits)", "m"),
        ("graph", DirectedGraph, None, "Directed Graph of all Elements. All elements in elements have to be referenced here."
                                       "There must not be cycles (we should check this). In case an element is a ForEach or "
                                       "another workflow this workflow does not need to be encoded here." , "m"),
        ("storage", str, "",            "Path to the storage directory assigned by the workflow client.", "a"),
        ("name", str, "Workflow", "Name of this workflow. Something like Hans or Fritz.", "a"),
        ("queueing_system",str, "unset", "Name of the queueing system. Might move into WFEM in case of split jobs.", "a")
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = "Workflow"
        self._logger = logging.getLogger("Workflow")
        self._abs_resolve_storage()

    def _abs_resolve_storage(self):
        if not self.storage.startswith('/'):
            home = str(Path.home())
            self._field_values["storage"] = home + '/' + self._field_values["storage"]

    def fields(cls):
        return cls._fields

    def from_xml(self, in_xml):
        super().from_xml(in_xml)
        self._abs_resolve_storage()

    def from_dict(self, in_dict):
        super().from_dict(in_dict)
        self._abs_resolve_storage()

    def jobloop(self):
        ready_jobs = self.graph.get_next_ready()
        self.graph.traverse()
        print(ready_jobs)
        for rdjob in ready_jobs:
            tostart = self.elements.get_element_by_uid(rdjob)
            tostart : WorkflowExecModule
            if not self._prepare_job(tostart):
                raise WorkflowAbort("Could not prepare job.")
            else:
                tostart.write_jobfile(self.queueing_system)
                self.graph.start(rdjob)
                self._logger.info("Started job >%s< in directory <%s> ."%(rdjob, tostart.runtime_directory))

    def _stage_file(self,fromfile,tofile):
        # At the moment this should only be a cp, but later it can also be a scp
        shutil.copyfile(fromfile, tofile)

    def _get_job_directory(self, wfem: WorkflowExecModule):
        now = datetime.datetime.now()
        nowstr = now.strftime("%Y-%m-%d-%H:%M:%S")
        submitname = "%s-%s" %(nowstr, wfem.given_name)
        return submitname

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





    """
    Liste für morgen
    - Im Client Storage ID setzen und beim Workflow mit angeben.
    - Staging oben weiterschreiben
    Sobald gestaged: 
        write jobfile in WorkflowExecModule rüberziehen
        submitten und ID abgreifen
        Digraph start muss id speichern
        Check auf id mit clusterjob
        Delay Loop, auch mit expo backoff
        Sobald fertig, stageout genau wie stagein machen
        digraph finish aufrufen
        get_next_ready und von vorn
        
    WF API
        zeromq api schreiben
        ssh transport auf zeromq port anheben 
            irgendwie drauf achten, dass nur user mit zmq kommunizieren können
        Server vom client aus starten
    """

    def _start_job(self):
        pass


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
    def queueing_system(self) -> str:
        return self._field_values["queueing_system"]

    def set_queueing_system(self, queueing_system) -> str:
        self._field_values["queueing_system"] = queueing_system