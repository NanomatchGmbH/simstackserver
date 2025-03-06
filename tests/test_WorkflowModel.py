from unittest.mock import ANY, patch, MagicMock

from unittest import mock

import pytest

from SimStackServer.WorkflowModel import (
    _is_basetype,
    _str_to_bool,
    WFPass,
    ForEachGraph,
    IfGraph,
    VariableElement,
    WhileGraph,
    SubGraph,
    workflow_element_factory,
)

import copy
import os
import pathlib
import shutil
import tempfile
import numpy as np
from os.path import join

from io import StringIO

from lxml import etree

from SimStackServer.Util import ClusterSettings
from SimStackServer.Util.FileUtilities import file_to_xml
from SimStackServer.WorkflowModel import (
    Resources,
    WorkflowExecModule,
    WorkflowElementList,
    DirectedGraph,
    Workflow,
    StringList,
)

from SimStackServer.WorkflowModel import XMLYMLInstantiationBase


@pytest.fixture(autouse=True)
def conda_prefix_tmpdir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        prefix = pathlib.Path(tmpdirname) / "envs" / "simstack_server_v6"
        with mock.patch.dict(os.environ, {"CONDA_PREFIX": str(prefix)}):
            os.makedirs(os.path.join(tmpdirname, "envs"), exist_ok=True)
            yield tmpdirname


@pytest.fixture
def temp_xml_file():
    with tempfile.TemporaryDirectory() as tmpdirname:
        xml_str = "<Parent><test_field>test_value</test_field></Parent>"
        xml_file_path = os.path.join(tmpdirname, "test.xml")
        with open(xml_file_path, "w") as xml_file:
            xml_file.write(xml_str)
        yield xml_file_path


@pytest.fixture
def wfem_exec_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        mydir = pathlib.Path(__file__).parent / "exec_dirs" / "WFEMExecDir"
        shutil.copytree(mydir, tmpdirname, dirs_exist_ok=True)
        yield tmpdirname


def SampleWFEM(wfem_exec_dir):
    xml = (
        """    <WorkflowExecModule id="0" type="WorkflowExecModule" uid="653895b9-4a4b-4a14-b2ca-ba7aaf12e8f6" given_name="EmployeeRecord" path="EmployeeRecord" wano_xml="EmployeeRecord.xml" outputpath="EmployeeRecord${var}">
  <inputs>
    <Ele_2 id="2" type="StringList">
      <Ele_0 id="0" type="str">test.png</Ele_0>
      <Ele_1 id="1" type="str">workflow_data/EmployeeRecord/inputs/test.png</Ele_1>
    </Ele_2>
  </inputs>
  <outputs>
    <Ele_0 id="0" type="StringList">
      <Ele_0 id="0" type="str">test</Ele_0>
      <Ele_1 id="1" type="str">${var}</Ele_1>
    </Ele_0>
  </outputs>
  <exec_command>touch test</exec_command>
  <resources walltime="86399" cpus_per_node="1" nodes="1" memory="4096">
    <queue>None</queue>
    <host>localhost</host>
    <custom_requests>None</custom_requests>
  </resources>
  <runtime_directory>%s</runtime_directory>
  <jobid>0</jobid>
  <queueing_system>Internal</queueing_system>
</WorkflowExecModule>
"""
        % wfem_exec_dir
    )
    test_xml = etree.parse(StringIO(xml)).getroot()
    wfem = WorkflowExecModule()
    wfem.from_xml(test_xml)
    return wfem


@pytest.fixture
def sample_wfem(wfem_exec_dir):
    return SampleWFEM(wfem_exec_dir)


# Test for _is_basetype function
def test_is_basetype():
    class MockType:
        def to_xml(self):
            pass

    assert _is_basetype(int) is True
    assert _is_basetype(str) is True
    assert _is_basetype(MockType) is False


# Test for _str_to_bool function
def test_str_to_bool():
    assert _str_to_bool("true") is True
    assert _str_to_bool("false") is False
    with pytest.raises(ValueError):
        _str_to_bool("unknown")


class ExampleClass(XMLYMLInstantiationBase):
    _fields = [("test_field", str, "unset_at_start", "A test field", "m")]
    _name = "ExampleClass"

    @property
    def test_field(self):
        return self.get_field_value("test_field")


class TestXMLYMLInstantiationBase:
    def test_initialization(self):
        instance = XMLYMLInstantiationBase()
        assert instance._field_values == {}
        assert instance._field_types == {}
        assert instance._field_explanations == {}
        assert instance._field_defaults == {}
        assert instance._field_attribute_or_member == {}
        assert instance._field_names == set()
        assert isinstance(instance._last_dump_time, float)

    def test_contains(self):
        instance = ExampleClass()
        assert instance.contains("test_field") is True
        assert instance.contains("non_existent_field") is False

    def test_set_field_value(self):
        instance = ExampleClass()
        instance.set_field_value("test_field", "test_value")
        assert instance._field_values["test_field"] == "test_value"

    def test_get_field_value(self):
        instance = XMLYMLInstantiationBase()
        instance._field_values["test_field"] = "test_value"
        assert instance.get_field_value("test_field") == "test_value"
        with pytest.raises(KeyError):
            instance.get_field_value("non_existent_field")

    def test_setup_empty_field_values(self):
        instance = ExampleClass()
        instance._setup_empty_field_values()
        assert instance._field_values["test_field"] == "unset_at_start"

    # Test for to_xml and from_xml functions
    def test_to_xml(self):
        instance = ExampleClass()
        instance.set_field_value("test_field", "test_value")
        parent = etree.Element("Parent")
        instance.to_xml(parent_element=parent)

        assert (
            etree.tounicode(parent)
            == "<Parent><test_field>test_value</test_field></Parent>"
        )

    def test_from_xml(self):
        xml_str = "<Parent><test_field>test_value</test_field></Parent>"
        xml = etree.fromstring(xml_str)
        instance = ExampleClass()
        instance.from_xml(xml)
        assert instance.get_field_value("test_field") == "test_value"

    def test_to_dict(self):
        instance = ExampleClass()
        instance.set_field_value("test_field", "test_value")
        out_dict = {}
        instance.to_dict(out_dict)
        assert out_dict == {"test_field": "test_value"}

    def test_from_dict(self):
        in_dict = {"test_field": "test_value"}
        instance = ExampleClass()
        instance.from_dict(in_dict)
        assert instance.get_field_value("test_field") == "test_value"

    def test_dump_xml_to_file(self):
        instance = ExampleClass()
        instance.set_field_value("test_field", "test_value")
        with tempfile.NamedTemporaryFile("wt") as outfile:
            instance.dump_xml_to_file(pathlib.Path(outfile.name))
            with open(outfile.name, "r") as f:
                result = f.read()
                expected = '<Workflow wfname="ExampleClass">\n  <test_field>test_value</test_field>\n</Workflow>\n\n'
                assert result == expected

    def test_to_json(self):
        instance = ExampleClass()
        instance.set_field_value("test_field", "test_value")
        with tempfile.NamedTemporaryFile("wt") as outfile:
            instance.to_json(pathlib.Path(outfile.name))
            with open(outfile.name, "r") as f:
                result = f.read()
                expected = '{"test_field": "test_value"}'
                assert result == expected

    def test_from_json(self):
        json_str = '{"test_field": "test_value"}'
        with tempfile.NamedTemporaryFile("wt") as infile:
            infile.write(json_str)
            infile.flush()
            instance = ExampleClass()
            instance.from_json(pathlib.Path(infile.name))
            assert instance.get_field_value("test_field") == "test_value"

    def test_new_instance_from_xml(self, temp_xml_file):
        instance = ExampleClass.new_instance_from_xml(temp_xml_file)
        assert instance.get_field_value("test_field") == "test_value"


def test_wfem_fill_in_variables(sample_wfem):
    sample_wfem.fill_in_variables({"${var}": "teststr2"})
    assert sample_wfem.outputs[0][1] == "teststr2"
    assert sample_wfem.outputpath == "EmployeeRecordteststr2"


@pytest.fixture
def exec_directory():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def input_directory():
    mydir = pathlib.Path(__file__).parent
    return f"{mydir}/input_dirs/WorkflowModel"


@pytest.fixture
def cluster_settings_test_dir():
    return pathlib.Path(__file__).parent / "exec_dirs" / "ClusterSettingsTestDir"


@pytest.fixture
def cluster_settings_test_dir_to():
    return pathlib.Path(__file__).parent / "exec_dirs" / "ClusterSettingsTestDirTo"


@pytest.fixture
def sample_resource_model(input_directory):
    example_resource_xml_fn = join(input_directory, "resources.xml")
    myxml = file_to_xml(example_resource_xml_fn)
    resources = Resources()
    resources.from_xml(myxml)
    return resources


def test_sample_wfem_roundtrip(sample_wfem):
    wfem = sample_wfem
    wfem_dict = {}
    wfem.to_dict(wfem_dict)
    wfem2 = WorkflowExecModule()
    wfem2.from_dict(wfem_dict)
    assert wfem.inputs.compare_with_other_list(wfem2.inputs)


def assert_resource_equal(rs1, rs2):
    assert rs1.walltime == rs2.walltime
    assert rs1.cpus_per_node == rs2.cpus_per_node
    assert rs1.nodes == rs2.nodes
    assert rs1.memory == rs2.memory
    assert rs1.base_URI == rs2.base_URI
    assert rs1.queue == rs2.queue


def test_ResourceModel(input_directory):
    """
    This is the test xml:
        <Resources walltime="3600" cpus_per_node="32" nodes="4" memory="65536">
            <queue>not-default</queue>
            <host>superhost</host>
        </Resources>
    """

    example_resource_xml_fn = join(input_directory, "resources.xml")
    myxml = file_to_xml(example_resource_xml_fn)

    resources = Resources()
    resources.from_xml(myxml)

    assert resources.walltime == 3600
    assert resources.cpus_per_node == 32
    assert resources.nodes == 4
    assert resources.memory == 65536
    assert resources.queue == "not-default"
    assert resources.custom_requests == "GPU=3"
    assert resources.username == "MaxPower"

    res = etree.Element("Resources")
    resources.to_xml(res)

    outstring = '<Resources resource_name="&lt;Connected Server&gt;" walltime="3600" cpus_per_node="32" nodes="4" memory="65536" reuse_results="False"><queue>not-default</queue><custom_requests>GPU=3</custom_requests><base_URI></base_URI><port>22</port><username>MaxPower</username><basepath>simstack_workspace</basepath><queueing_system>pbs</queueing_system><sw_dir_on_resource>/home/nanomatch/nanomatch</sw_dir_on_resource><extra_config>None Required (default)</extra_config><ssh_private_key>UseSystemDefault</ssh_private_key><sge_pe></sge_pe></Resources>'
    otheroutstring = etree.tostring(res).decode()

    assert outstring == otheroutstring

    resdict = {}
    resources.to_dict(resdict)

    other_resource = Resources()
    other_resource.from_dict(resdict)

    other_resource_2 = Resources()
    with tempfile.NamedTemporaryFile("wt") as outfile:
        resources.to_json(pathlib.Path(outfile.name))
        other_resource_2.from_json(pathlib.Path(outfile.name))

    for oo in [other_resource_2, other_resource]:
        assert resources.walltime == oo.walltime
        assert resources.cpus_per_node == oo.cpus_per_node
        assert resources.nodes == oo.nodes
        assert resources.memory == oo.memory
        assert resources.queue == oo.queue


def test_ClusterSettings(
    input_directory, cluster_settings_test_dir, cluster_settings_test_dir_to
):
    example_resource_xml_fn = join(input_directory, "resources.xml")
    myxml = file_to_xml(example_resource_xml_fn)

    resources = Resources()
    resources.from_xml(myxml)

    resource2 = copy.deepcopy(resources)

    resource3 = copy.deepcopy(resources)

    outdict = {"hank": resources, "frank": resource2, "tank": resource3}
    from_folder = pathlib.Path(cluster_settings_test_dir)
    myset = ClusterSettings.get_cluster_settings_from_folder(from_folder)

    for name in outdict.keys():
        assert_resource_equal(myset[name], outdict[name])

    to_folder = pathlib.Path(cluster_settings_test_dir_to)
    if to_folder.is_dir():
        shutil.rmtree(to_folder)
    os.makedirs(to_folder, exist_ok=False)
    ClusterSettings.save_cluster_settings_to_folder(to_folder, myset)

    last_dict = ClusterSettings.get_cluster_settings_from_folder(to_folder)
    for name in outdict.keys():
        assert_resource_equal(last_dict[name], outdict[name])


def test_DigraphTravseral():
    ooommmm = DirectedGraph([("0", 3), (3, [4444, 983]), (983, 12)])
    ooommmm.traverse()
    outnodes = ooommmm.get_next_ready()
    ooommmm.start(outnodes[0])
    started = outnodes[0]
    outnodes = ooommmm.get_next_ready()
    assert len(outnodes) == 0
    ooommmm.finish(started)
    outnodes = ooommmm.get_next_ready()
    assert outnodes == [4444, 983]

    ooommmm.start(4444)
    ooommmm.finish(4444)

    outnodes = ooommmm.get_next_ready()
    assert outnodes[0] == 983

    ooommmm.start(983)

    outnodes = ooommmm.get_next_ready()
    assert len(outnodes) == 0
    ooommmm.finish(983)

    outnodes = ooommmm.get_next_ready()
    assert outnodes == [12]

    ooommmm.start(12)

    outnodes = ooommmm.get_next_ready()
    assert len(outnodes) == 0

    ooommmm.finish(12)
    outnodes = ooommmm.get_next_ready()
    assert len(outnodes) == 0

    report_order = [*ooommmm.report_order_generator()]
    expected = ["0", 3, 4444, 983, 12]
    assert report_order == expected


def test_time_from_seconds_to_clusterjob_timestring():
    mytime = 5 * 86400 + 3 * 3600 + 12 * 60 + 14
    outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(mytime)
    assert outstring == "5-3:12:14"
    mytime = 5
    outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(mytime)
    assert outstring == "05"
    mytime = 2 * 60 + 4
    outstring = WorkflowExecModule._time_from_seconds_to_clusterjob_timestring(mytime)
    assert outstring == "02:04"


@pytest.fixture
def workflow_exec_module():
    fromdict = {
        "exec_command": "date",
        "external_runtime_directory": "testdir",
        "given_name": "WFEM",
        "inputs": {},
        "jobid": "unstarted",
        "original_result_directory": "",
        "outputpath": "unset",
        "outputs": {},
        "path": "unset",
        "resources": {
            "base_URI": "",
            "basepath": "simstack_workspace",
            "cpus_per_node": "1",
            "custom_requests": "",
            "extra_config": "None Required (default)",
            "memory": "4096",
            "nodes": "1",
            "port": "22",
            "queue": "default",
            "queueing_system": "unset",
            "resource_name": "<Connected Server>",
            "reuse_results": "False",
            "sge_pe": "",
            "ssh_private_key": "UseSystemDefault",
            "sw_dir_on_resource": "/home/nanomatch/nanomatch",
            "username": "",
            "walltime": "86399",
        },
        "runtime_directory": "unstarted",
        "uid": ANY,
        "wano_xml": "unset",
    }
    return fromdict


def test_WorkflowExecModule():
    a = WorkflowExecModule()
    test_xml_str = """
    <TestWFE>
        <resources walltime="5" cpus_per_node="3" nodes="12" memory="1644">
            <queue>ault</queue>
            <host>host</host>
        </resources>
    </TestWFE>
    """
    test_xml = etree.parse(StringIO(test_xml_str)).getroot()
    parent_dict = {}

    a.to_dict(parent_dict)
    expected = {
        "exec_command": "None",
        "external_runtime_directory": "",
        "given_name": "WFEM",
        "inputs": {},
        "jobid": "unstarted",
        "original_result_directory": "",
        "outputpath": "unset",
        "outputs": {},
        "path": "unset",
        "resources": {
            "base_URI": "",
            "basepath": "simstack_workspace",
            "cpus_per_node": "1",
            "custom_requests": "",
            "extra_config": "None Required (default)",
            "memory": "4096",
            "nodes": "1",
            "port": "22",
            "queue": "default",
            "queueing_system": "unset",
            "resource_name": "<Connected Server>",
            "reuse_results": "False",
            "sge_pe": "",
            "ssh_private_key": "UseSystemDefault",
            "sw_dir_on_resource": "/home/nanomatch/nanomatch",
            "username": "",
            "walltime": "86399",
        },
        "runtime_directory": "unstarted",
        "uid": ANY,
        "wano_xml": "unset",
    }
    assert parent_dict == expected

    myxml = etree.Element("TestWFE")
    a.set_field_value("uid", "1234")
    a.to_xml(myxml)
    xml_str = etree.tounicode(myxml)
    expected = '<TestWFE uid="1234" given_name="WFEM" path="unset" wano_xml="unset" outputpath="unset" original_result_directory=""><inputs/><outputs/><exec_command>None</exec_command><resources resource_name="&lt;Connected Server&gt;" walltime="86399" cpus_per_node="1" nodes="1" memory="4096" reuse_results="False"><queue>default</queue><custom_requests></custom_requests><base_URI></base_URI><port>22</port><username></username><basepath>simstack_workspace</basepath><queueing_system>unset</queueing_system><sw_dir_on_resource>/home/nanomatch/nanomatch</sw_dir_on_resource><extra_config>None Required (default)</extra_config><ssh_private_key>UseSystemDefault</ssh_private_key><sge_pe></sge_pe></resources><runtime_directory>unstarted</runtime_directory><jobid>unstarted</jobid><external_runtime_directory></external_runtime_directory></TestWFE>'
    assert xml_str == expected
    b = WorkflowExecModule()
    b.from_xml(test_xml)
    otherdict = {}
    b.to_dict(otherdict)
    c = WorkflowExecModule()
    c.from_dict(otherdict)
    for val1, val2, val3 in zip(c._field_values, b._field_values, a._field_values):
        assert val1 == val2


def test_WorkflowElementList():
    d = WorkflowElementList()
    d._add_to_list("np.int64", np.int64(4.0))
    assert d._typelist == ["np.int64"]
    assert d._storage == [np.int64(4.0)]

    myxml = etree.Element("TestWFEL")
    d.to_xml(myxml)
    testdict = {}
    d.to_dict(testdict)

    e = WorkflowElementList()
    e.from_xml(myxml)
    assert e.compare_with_other_list(d)

    f = WorkflowElementList()
    assert not e.compare_with_other_list(f)

    f.from_dict(testdict)
    assert e.compare_with_other_list(f)

    e.merge_other_list(d)
    assert len(e._storage) == 2

    g = WorkflowElementList()
    other_xml = '<TestWFEL><Ele_0 id="0" type="np.int64">not_an_int</Ele_0></TestWFEL>'
    broken_xml = etree.fromstring(other_xml)
    with pytest.raises(ValueError):
        g.from_xml(broken_xml)

    other_xml = '<TestWFEL><Ele_0 id="0" uid="4" type="np.int64">5</Ele_0></TestWFEL>'
    other_xml = etree.fromstring(other_xml)
    g.from_xml(other_xml)
    assert g._uid_to_seqnum["4"] == 0


def test_WFE_fill_in_variables():
    g = WorkflowElementList()
    g._add_to_list("np.int64", np.int64(4.0))
    g._add_to_list("str", "teststr")
    g._add_to_list("str", "${var}")
    g.fill_in_variables({"${var}": "teststr2"})
    assert g._storage == [np.int64(4.0), "teststr", "teststr2"]


def test_WFE_getitem_and_iter():
    g = WorkflowElementList()
    g._add_to_list("np.int64", np.int64(4.0))
    g._add_to_list("str", "teststr")
    assert g[0] == np.int64(4.0)
    assert g[1] == "teststr"

    for item in zip(g, [np.int64(4.0), "teststr"]):
        assert item[0] == item[1]


def test_resources():
    ooooo = Resources(walltime=101)
    assert ooooo.walltime == 101
    h = WorkflowExecModule(resources=Resources(walltime=201))
    print(h.resources.walltime)
    assert h.resources.walltime == 201

    outor = {}
    oik = WorkflowElementList([("WorkflowExecModule", h), ("WorkflowExecModule", h)])
    oik.to_dict(outor)

    oik_xml = etree.Element("WFEM")
    oik.to_xml(oik_xml)
    print(outor)
    print(etree.tostring(oik_xml, encoding="utf8", pretty_print=True).decode())

    ooommmm = DirectedGraph([(3, [4444, 983]), (983, 12)])

    test_xml = etree.Element("DiGraph")
    print(ooommmm.to_xml(test_xml))
    print(etree.tostring(test_xml, pretty_print=True).decode())
    for hild in test_xml:
        assert hild.tag == "{http://graphml.graphdrawing.org/xmlns}graphml"
    ooommmm.from_xml(test_xml)
    outtest = {}
    ooommmm.to_dict(outtest)
    ooommmm.from_dict(outtest)

    test_xml = etree.Element("Workflow")
    ab = Workflow(elements=oik, graph=ooommmm)
    print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())
    ab.to_xml(test_xml)


def test_overwrite_unset_fields_from_default_resources_sets_basepath():
    default_resources = Resources(basepath="/default/path")
    resources = Resources(resource_name="<Connected Server>")
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.basepath == "/default/path"


def test_overwrite_unset_fields_from_default_resources_sets_base_URI():
    default_resources = Resources(base_URI="http://default.uri")
    resources = Resources(base_URI="http://default.uri")
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.base_URI == "None"
    assert resources.resource_name == "<Connected Server>"


def test_overwrite_unset_fields_from_default_resources_sets_queue():
    default_resources = Resources(queue="default_queue")
    resources = Resources(queue="default")
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.queue == "default_queue"


def test_overwrite_unset_fields_from_default_resources_sets_queueing_system():
    default_resources = Resources(queueing_system="slurm")
    resources = Resources(queueing_system="unset")
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.queueing_system == "slurm"


def test_overwrite_unset_fields_from_default_resources_sets_sge_pe():
    default_resources = Resources(sge_pe="default_pe")
    resources = Resources(sge_pe="unset")
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.sge_pe == "default_pe"


def test_overwrite_unset_fields_from_default_resources_does_not_overwrite_set_fields():
    default_resources = Resources(
        queue="default_queue", queueing_system="slurm", sge_pe="default_pe"
    )
    resources = Resources(
        queue="custom_queue", queueing_system="custom_system", sge_pe="custom_pe"
    )
    resources.overwrite_unset_fields_from_default_resources(default_resources)
    assert resources.queue == "custom_queue"
    assert resources.queueing_system == "custom_system"
    assert resources.sge_pe == "custom_pe"


def test_StringList():
    test_xml = etree.Element("StringList")
    ab = StringList(["aaa", "abbb"])
    ab.to_xml(test_xml)
    print(etree.tostring(test_xml, encoding="utf8", pretty_print=True).decode())


@pytest.mark.parametrize(
    "name, expected_class",
    [
        ("WorkflowExecModule", WorkflowExecModule),
        ("StringList", StringList),
        ("WorkflowElementList", WorkflowElementList),
        ("WFPass", WFPass),
        ("ForEachGraph", ForEachGraph),
        ("IfGraph", IfGraph),
        ("VariableElement", VariableElement),
        ("WhileGraph", WhileGraph),
        ("SubGraph", SubGraph),
        ("int", int),
        ("str", str),
        ("bool", bool),
        ("np.int32", getattr(globals()["np"], "int32")),
        ("np.float64", getattr(globals()["np"], "float64")),
    ],
)
def test_workflow_element_factory(name, expected_class):
    assert workflow_element_factory(name) == expected_class


def test_workflow_element_factory_raises():
    with pytest.raises(NotImplementedError):
        workflow_element_factory("UnknownClass")


def test_check_if_job_is_local(monkeypatch):
    # Create a mock WorkflowExecModule instance
    resources = Resources(resource_name="localhost")
    wfem = WorkflowExecModule(resources=resources)

    # Mock the os.getlogin function to return a specific username
    monkeypatch.setattr(os, "getlogin", lambda: "testuser")

    # Test case 1: resource_name is None
    wfem.resources.set_field_value("resource_name", None)
    assert wfem.check_if_job_is_local() is True

    # Test case 2: resource_name is <Connected Server>
    wfem.resources.set_field_value("resource_name", Resources._connected_server_text)
    assert wfem.check_if_job_is_local() is True

    # Test case 3: resource_name is not None or <Connected Server> and username matches
    wfem.resources.set_field_value("resource_name", "remote_server")
    wfem.resources.set_field_value("username", "testuser")
    monkeypatch.setattr(os, "getlogin", lambda: "testuser")
    monkeypatch.setattr("SimStackServer.WorkflowModel.is_localhost", lambda x: True)
    assert wfem.check_if_job_is_local() is True

    # Test case 4: resource_name is not None or <Connected Server> and username does not match
    wfem.resources.set_field_value("username", "otheruser")
    assert wfem.check_if_job_is_local() is False

    # Test case 5: resource_name is not None or <Connected Server> and base_URI is not localhost
    wfem.resources.set_field_value("username", "testuser")
    monkeypatch.setattr("SimStackServer.WorkflowModel.is_localhost", lambda x: False)
    assert wfem.check_if_job_is_local() is False


def test_wfem_rename(sample_wfem):
    rename_dict = {sample_wfem.uid: "replacement_for_testing"}
    sample_wfem.rename(rename_dict)
    assert sample_wfem.uid == "replacement_for_testing"

    with pytest.raises(KeyError):
        sample_wfem.rename(rename_dict)


def test_wfem__get_clustermanager_from_job(sample_wfem):
    sample_wfem._field_values["resources"] = Resources(
        resource_name="localhost", base_URI="localhost"
    )
    assert sample_wfem._get_clustermanager_from_job()._url == "localhost"


def test_get_prolog_unicore_compatibility(sample_wfem, conda_prefix_tmpdir):
    resources = Resources()
    result = sample_wfem._get_prolog_unicore_compatibility(resources)
    expected = (
        """
UC_NODES=1; export UC_NODES;
UC_PROCESSORS_PER_NODE=1; export UC_PROCESSORS_PER_NODE;
UC_TOTAL_PROCESSORS=1; export UC_TOTAL_PROCESSORS;
UC_MEMORY_PER_NODE=4096; export UC_MEMORY_PER_NODE;
BASEFOLDER="%s"

# The following are exports to resolve previous and future
# versions of the SimStackServer conda / python interpreters
###########################################################

simstack_server_mamba_source () {{
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
}}

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
        % conda_prefix_tmpdir
    )
    assert result == expected


def test_wfem_run_jobfile(sample_wfem):
    sample_wfem.do_internal = False
    sample_wfem.do_aiida = False
    resource = Resources(
        resource_name="test_cluster",
        base_URI="test_host.example.com",
        username="test_user",
        queue="test_queue",
        queueing_system="slurm",
        port=2222,
    )
    sample_wfem._field_values["resources"] = resource
    with patch("SimStackServer.WorkflowModel.JobScript") as mock:
        sample_wfem.run_jobfile()
        calls = mock.call_args_list
        assert calls[0].kwargs == {
            "backend": "slurm",
            "jobname": "EmployeeRecord",
            "mem": 4096,
            "nodes": 1,
            "ppn": 1,
            "queue": "test_queue",
            "stderr": "EmployeeRecord.stderr",
            "stdout": "EmployeeRecord.stdout",
            "time": "23:59:59",
            "workdir": ANY,
        }


def test_wfem_run_jobfile_external_clustermanager(sample_wfem):
    sample_wfem.do_internal = False
    sample_wfem.do_aiida = False
    resource = Resources(
        resource_name="test_cluster",
        base_URI="test_host.example.com",
        username="test_user",
        queue="test_queue",
        queueing_system="slurm",
        port=2222,
    )
    sample_wfem._field_values["resources"] = resource
    external_cluster_manager_mock = MagicMock()
    sample_wfem.run_jobfile(external_cluster_manager=external_cluster_manager_mock)
    assert external_cluster_manager_mock.put_directory.call_count == 1
    assert (
        external_cluster_manager_mock.mkdir_random_singlejob_exec_directory.call_count
        == 1
    )
    assert external_cluster_manager_mock.submit_single_job.call_count == 1
    localhost_wfem = external_cluster_manager_mock.submit_single_job.call_args[0][0]
    # Check that the wfem sent to the other clustermanager runs on localhost then:
    assert localhost_wfem.resources._field_values["base_URI"] == "localhost"


def test_wefem_run_jobfile_internalbatch(sample_wfem):
    sample_wfem.do_internal = False
    sample_wfem.do_aiida = False
    resource = Resources(
        resource_name="test_cluster",
        base_URI="test_host.example.com",
        username="test_user",
        queue="test_queue",
        queueing_system="Internal",
        port=2222,
    )
    sample_wfem._field_values["resources"] = resource
    with patch("SimStackServer.WorkflowModel.InternalBatchSystem") as mock:
        batchsys_instance_mock = MagicMock()
        mock.get_instance.return_value = batchsys_instance_mock, MagicMock()
        sample_wfem.run_jobfile()

        call_args = batchsys_instance_mock.add_work_to_current_bracket.call_args[0]
        assert call_args[0] == 1
        assert call_args[1] == "smp"
        assert call_args[2].endswith("jobscript.sh")


def test_wefem_run_jobfile_onlyscript(sample_wfem):
    sample_wfem.do_internal = False
    sample_wfem.do_aiida = False
    resource = Resources(
        resource_name="test_cluster",
        base_URI="test_host.example.com",
        username="test_user",
        queue="test_queue",
        queueing_system="OnlyScript",
        port=2222,
    )
    sample_wfem._field_values["resources"] = resource
    sample_wfem.run_jobfile()
    assert sample_wfem.jobid == 1


def test_wefem_run_jobfile_error_write_stderr(sample_wfem, wfem_exec_dir):
    sample_wfem.do_internal = False
    sample_wfem.do_aiida = False
    resource = Resources(
        resource_name="test_cluster",
        base_URI="test_host.example.com",
        username="test_user",
        queue="test_queue",
        queueing_system="I DO NOT EXIST",
        port=2222,
    )
    sample_wfem._field_values["resources"] = resource
    with pytest.raises(ValueError):
        sample_wfem.run_jobfile()
    assert (pathlib.Path(wfem_exec_dir) / "submission_failed.stderr").is_file()



def test_abort_job_internal():
    wfem = WorkflowExecModule()
    wfem._field_values["jobid"] = "1234"
    wfem._field_values["resources"] = Resources(
        resource_name="<Connected Server>",
        base_URI="localhost",
        username="test_user",
        queue="test_queue",
        queueing_system="Internal",
        port=2222,
    )
    with patch("SimStackServer.WorkflowModel.InternalBatchSystem") as mock:
        batchsys_instance_mock = MagicMock()
        mock.get_instance.return_value = batchsys_instance_mock, MagicMock()
        wfem.abort_job()
        assert batchsys_instance_mock.abort_job.call_count == 1

def test_abort_job_internal_slurm():
    wfem = WorkflowExecModule()
    wfem._field_values["jobid"] = "1234"
    wfem._field_values["resources"] = Resources(
        resource_name="<Connected Server>",
        base_URI="localhost",
        username="test_user",
        queue="test_queue",
        queueing_system="slurm",
        port=2222,
    )
    with patch("SimStackServer.WorkflowModel.AsyncResult") as asyncmock:
        with patch("SimStackServer.WorkflowModel.JobScript") as clusterjobmock:
            clusterjobmock._backends = {"slurm": MagicMock()}
            wfem.abort_job()
            assert asyncmock.mock_calls[1][0] == '().cancel'

def test_abort_job_external_cm():
    wfem = WorkflowExecModule()
    wfem._field_values["jobid"] = "1234"
    wfem._field_values["resources"] = Resources(
        resource_name="other_cluster",
        base_URI="somewhere_else",
        username="test_user",
        queue="test_queue",
        queueing_system="slurm",
        port=2222,
    )
    with patch("SimStackServer.WorkflowModel.RemoteServerManager") as asyncmock:
        wfem.abort_job()
        assert str(asyncmock.get_instance.return_value.server_from_resource.mock_calls[3]).startswith("call().send_abortsinglejob_message('")


